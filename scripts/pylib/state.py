"""Состояние релизов в кластере (ConfigMap mts-api-release-state).

Фактическая маршрутизация — селектор Service mts-api-active (владелец — чарт traffic).
ConfigMap хранит последний подтверждённый здоровый релиз, текущую фазу операции
(для восстановления после прерывания) и короткую историю решений.
"""

from __future__ import annotations

import copy
import json

from .common import iso, utcnow
from .kube import Kube

STATE_CM = "mts-api-release-state"
ACTIVE_SERVICE = "mts-api-active"
TRAFFIC_RELEASE = "mts-api-traffic"
SLOTS = ("blue", "green")
HISTORY_LIMIT = 25

EMPTY_STATE: dict = {
    "schema": 1,
    "phase": "idle",
    "operation": None,
    "active": None,
    "standby": None,
    "candidate": None,
    "previous_slot": None,
    "secret_rotation": None,
    "history": [],
    "updated_at": None,
}


def other_slot(slot: str | None) -> str:
    return "green" if slot == "blue" else "blue"


def slot_release(slot: str) -> str:
    return f"mts-api-{slot}"


class StateStore:
    def __init__(self, kube: Kube) -> None:
        self.kube = kube
        self.resource_version: str | None = None

    def load(self) -> dict:
        cm = self.kube.get_json("configmap", STATE_CM)
        if not cm:
            self.resource_version = None
            return copy.deepcopy(EMPTY_STATE)
        self.resource_version = cm["metadata"]["resourceVersion"]
        state = copy.deepcopy(EMPTY_STATE)
        state.update(json.loads(cm.get("data", {}).get("state.json", "{}")))
        return state

    def save(self, state: dict) -> None:
        state["updated_at"] = iso(utcnow())
        state["history"] = state.get("history", [])[-HISTORY_LIMIT:]
        meta: dict = {
            "name": STATE_CM,
            "namespace": self.kube.namespace,
            "labels": {"app.kubernetes.io/part-of": "mts-devops"},
        }
        if self.resource_version:
            meta["resourceVersion"] = self.resource_version
        body = json.dumps(
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": meta,
                "data": {"state.json": json.dumps(state, ensure_ascii=False, indent=2)},
            }
        )
        verb = "replace" if self.resource_version else "create"
        out = self.kube.kubectl(verb, "-f", "-", "-o", "json", input_text=body)
        self.resource_version = json.loads(out.stdout)["metadata"]["resourceVersion"]


def live_active_slot(kube: Kube) -> str | None:
    svc = kube.get_json("service", ACTIVE_SERVICE)
    if not svc:
        return None
    slot = svc.get("spec", {}).get("selector", {}).get("slot")
    return slot if slot in SLOTS else None


def deployed_slot_info(kube: Kube, slot: str) -> dict | None:
    """Что фактически развёрнуто в слоте (по объекту Deployment, а не по записям)."""
    deploy = kube.get_json("deployment", slot_release(slot))
    if not deploy:
        return None
    tmpl = deploy["spec"]["template"]
    image = tmpl["spec"]["containers"][0]["image"]
    annotations = tmpl.get("metadata", {}).get("annotations", {})
    return {
        "slot": slot,
        "image": image,
        "digest": image.split("@", 1)[1] if "@" in image else "",
        "version": tmpl["metadata"].get("labels", {}).get("app.kubernetes.io/version", ""),
        "release_id": annotations.get("mts-devops/release-id", ""),
        "git_sha": annotations.get("mts-devops/git-sha", ""),
        "replicas": deploy["spec"].get("replicas", 0),
        "ready_replicas": deploy.get("status", {}).get("readyReplicas", 0) or 0,
    }
