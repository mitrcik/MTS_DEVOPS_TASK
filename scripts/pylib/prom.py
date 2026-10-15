"""Клиент HTTP API Prometheus/Alertmanager через ingress loopback."""

from __future__ import annotations

import json
import math
import urllib.parse

from .httpprobe import request


class PromUnavailable(RuntimeError):
    pass


class Prometheus:
    def __init__(self, base_url: str, host: str = "prometheus.localhost") -> None:
        self.base_url = base_url.rstrip("/")
        self.host = host

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        resp = request("GET", url, headers={"Host": self.host}, timeout=10)
        if resp.status != 200:
            raise PromUnavailable(f"{self.host}{path}: HTTP {resp.status} {resp.error or ''}".strip())
        try:
            body = json.loads(resp.body)
        except ValueError as exc:
            raise PromUnavailable(f"{self.host}{path}: ответ не JSON") from exc
        if body.get("status") not in (None, "success"):
            raise PromUnavailable(f"{self.host}{path}: {body.get('error')}")
        return body

    def ready(self) -> bool:
        resp = request("GET", self.base_url + "/-/ready", headers={"Host": self.host}, timeout=5)
        return resp.status == 200

    def query(self, expr: str, at: float | None = None) -> list[tuple[dict[str, str], float]]:
        params = {"query": expr}
        if at is not None:
            params["time"] = f"{at:.3f}"
        data = self._get("/api/v1/query", params)["data"]
        if data["resultType"] == "scalar":
            return [({}, float(data["result"][1]))]
        return [(item["metric"], float(item["value"][1])) for item in data["result"]]

    def scalar(self, expr: str, at: float | None = None) -> float | None:
        """Одно число либо None, если данных нет (пустой вектор или NaN)."""
        result = self.query(expr, at)
        if not result:
            return None
        value = result[0][1]
        return None if math.isnan(value) else value

    def alerts(self) -> list[dict]:
        return self._get("/api/v1/alerts")["data"]["alerts"]

    def rule_names(self) -> set[str]:
        groups = self._get("/api/v1/rules")["data"]["groups"]
        return {rule["name"] for group in groups for rule in group["rules"]}

    def targets(self) -> list[dict]:
        return self._get("/api/v1/targets", {"state": "active"})["data"]["activeTargets"]


class Alertmanager:
    def __init__(self, base_url: str, host: str = "alertmanager.localhost") -> None:
        self.base_url = base_url.rstrip("/")
        self.host = host

    def alerts(self, alertname: str) -> list[dict]:
        params = urllib.parse.urlencode(
            {"filter": f'alertname="{alertname}"', "active": "true", "silenced": "true", "inhibited": "true"}
        )
        resp = request("GET", f"{self.base_url}/api/v2/alerts?{params}", headers={"Host": self.host}, timeout=5)
        if resp.status != 200:
            raise PromUnavailable(f"alertmanager: HTTP {resp.status}")
        return json.loads(resp.body)

    def ready(self) -> bool:
        return request("GET", self.base_url + "/-/ready", headers={"Host": self.host}).status == 200
