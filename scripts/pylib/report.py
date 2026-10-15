"""Отчёт о релизе: JSON (машиночитаемый) и краткий Markdown.

Все значения берутся из фактического выполнения; секретов в отчёте нет
(токены представлены только отпечатком SHA-256).
"""

from __future__ import annotations

import json
from pathlib import Path

from .common import iso, utcnow


class Report:
    def __init__(self, kind: str, report_id: str, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.data: dict = {
            "kind": kind,
            "id": report_id,
            "decision": None,
            "reason": None,
            "started_at": iso(utcnow()),
            "finished_at": None,
            "timeline": [],
            "checks": {},
        }

    def event(self, name: str, **fields) -> None:
        self.data["timeline"].append({"at": iso(utcnow()), "event": name, **fields})

    def check(self, name: str, status: str, **fields) -> None:
        self.data["checks"][name] = {"status": status, "at": iso(utcnow()), **fields}

    def set(self, key: str, value) -> None:
        self.data[key] = value

    def finish(self, decision: str, reason: str | None) -> tuple[Path, Path]:
        self.data["decision"] = decision
        self.data["reason"] = reason
        self.data["finished_at"] = iso(utcnow())
        self.out_dir.mkdir(parents=True, exist_ok=True)
        base = self.out_dir / f"{self.data['kind']}-{self.data['id']}"
        json_path = base.with_suffix(".json")
        md_path = base.with_suffix(".md")
        json_path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(render_markdown(self.data), encoding="utf-8")
        latest = self.out_dir / f"latest-{self.data['kind']}.json"
        latest.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
        return json_path, md_path


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, (dict, list)):
        return "`" + json.dumps(value, ensure_ascii=False) + "`"
    return str(value)


def render_markdown(d: dict) -> str:
    lines = [
        f"# Отчёт: {d['kind']} `{d['id']}`",
        "",
        f"**Решение:** `{d['decision']}`" + (f" — {d['reason']}" if d.get("reason") else ""),
        "",
        f"- Начало: {d['started_at']}",
        f"- Переключение: {_fmt(d.get('switched_at'))}",
        f"- Завершение: {d['finished_at']}",
    ]
    if d.get("durations"):
        lines.append(f"- Длительности, с: {_fmt(d['durations'])}")
    if d.get("artifact"):
        a = d["artifact"]
        lines += [
            "",
            "## Артефакт",
            "",
            f"- Образ: `{a.get('image')}`",
            f"- Версия: `{a.get('version')}`, Git SHA: `{a.get('git_sha')}`",
        ]
        prov = a.get("provenance") or {}
        if prov:
            trivy = prov.get("trivy", {})
            lines.append(
                f"- CI: {_fmt(prov.get('stages'))}; Trivy {trivy.get('version')} "
                f"(DB {trivy.get('db_version')}, обновлена {trivy.get('db_updated_at')}): {trivy.get('result')}"
            )
    if d.get("slots"):
        s = d["slots"]
        lines += ["", "## Слоты", "", "| роль | слот | версия | digest | release id |", "|---|---|---|---|---|"]
        for role in ("previous", "candidate"):
            info = s.get(role) or {}
            digest = (info.get("digest") or "")[:19]
            lines.append(
                f"| {role} | {_fmt(info.get('slot'))} | {_fmt(info.get('version'))} | "
                f"`{digest}` | {_fmt(info.get('release_id'))} |"
            )
    if d.get("checks"):
        lines += ["", "## Проверки", "", "| проверка | статус | детали |", "|---|---|---|"]
        for name, c in d["checks"].items():
            extra = {k: v for k, v in c.items() if k not in ("status", "at")}
            lines.append(f"| {name} | **{c['status']}** | {_fmt(extra)[:400]} |")
    if d.get("rollback"):
        lines += ["", "## Возврат трафика", "", f"{_fmt(d['rollback'])}"]
    if d.get("tools"):
        lines += ["", f"Инструменты: {_fmt(d['tools'])}"]
    lines += ["", "## Хронология", ""]
    for ev in d.get("timeline", []):
        extra = {k: v for k, v in ev.items() if k not in ("at", "event")}
        lines.append(f"- `{ev['at']}` {ev['event']}" + (f" {_fmt(extra)}" if extra else ""))
    return "\n".join(lines) + "\n"
