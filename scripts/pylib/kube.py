"""Тонкие обёртки над kubectl/helm с выделенным kubeconfig (никогда не ~/.kube/config)."""

from __future__ import annotations

import contextlib
import json
import queue
import re
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path

from .common import CmdError, run, tool


class Kube:
    def __init__(self, kubeconfig: Path, namespace: str) -> None:
        if not kubeconfig.exists():
            raise SystemExit(f"нет kubeconfig {kubeconfig}; выполните make up (он создаёт выделенные учётные данные)")
        self.kubeconfig = kubeconfig
        self.namespace = namespace

    def _base(self, namespace: str | None) -> list[str]:
        return [
            tool("kubectl"),
            "--kubeconfig",
            str(self.kubeconfig),
            "--namespace",
            namespace or self.namespace,
            "--request-timeout=20s",
        ]

    def kubectl(
        self,
        *args: str,
        input_text: str | None = None,
        timeout: float = 60,
        check: bool = True,
        namespace: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return run([*self._base(namespace), *args], input_text=input_text, timeout=timeout, check=check)

    def get_json(self, *args: str, namespace: str | None = None) -> dict | None:
        proc = self.kubectl("get", *args, "-o", "json", check=False, namespace=namespace)
        if proc.returncode != 0:
            if "NotFound" in proc.stderr or "not found" in proc.stderr:
                return None
            raise CmdError(["kubectl", "get", *args], proc.returncode, proc.stdout, proc.stderr)
        return json.loads(proc.stdout)

    def helm(self, *args: str, timeout: float = 300, check: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = [tool("helm"), "--kubeconfig", str(self.kubeconfig), "--namespace", self.namespace]
        return run([*cmd, *args], timeout=timeout, check=check)

    def server_version(self) -> str:
        proc = self.kubectl("version", "-o", "json", check=False)
        try:
            return json.loads(proc.stdout)["serverVersion"]["gitVersion"]
        except (ValueError, KeyError):
            return "unknown"

    @contextlib.contextmanager
    def port_forward(self, target: str, remote_port: int = 8000, timeout: float = 15) -> Iterator[int]:
        """Открывает kubectl port-forward на случайный локальный порт loopback."""
        cmd = [
            *self._base(None),
            "port-forward",
            "--address",
            "127.0.0.1",
            target,
            f":{remote_port}",
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines: queue.Queue[str] = queue.Queue()

        def pump() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.put(line)

        threading.Thread(target=pump, daemon=True).start()
        port = None
        try:
            try:
                while port is None:
                    line = lines.get(timeout=timeout)
                    m = re.search(r"127\.0\.0\.1:(\d+)", line)
                    if m:
                        port = int(m.group(1))
            except queue.Empty as exc:
                err = proc.stderr.read() if proc.poll() is not None and proc.stderr else ""
                raise RuntimeError(f"port-forward {target} не поднялся за {timeout}s {err}") from exc
            yield port
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def pod_ready(pod: dict) -> bool:
    if pod.get("metadata", {}).get("deletionTimestamp"):
        return False
    for cond in pod.get("status", {}).get("conditions", []):
        if cond.get("type") == "Ready":
            return cond.get("status") == "True"
    return False


def pod_image_digest(pod: dict) -> str:
    for status in pod.get("status", {}).get("containerStatuses", []):
        image_id = status.get("imageID", "")
        if "@sha256:" in image_id:
            return image_id.split("@", 1)[1]
    return ""
