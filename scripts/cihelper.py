#!/usr/bin/env python3
"""Вспомогательные шаги CI: учёт стадий, политика Trivy, provenance, проверки конфигурации."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml  # PyYAML из .local/venv (зависимость ansible-core)

BLOCKING_SEVERITIES = {"CRITICAL", "HIGH"}
MAX_EXCEPTION_DAYS = 90
FORBIDDEN_TRACKED = [
    re.compile(p)
    for p in (
        r"(^|/)\.env$",
        r"\.kubeconfig$",
        r"(^|/)kubeconfig(\.ya?ml)?$",
        r"age\.key$",
        r"\.pem$",
        r"(^|/)id_(rsa|ed25519|ecdsa)(\.pub)?$",
        r"^\.local/",
    )
]
FORBIDDEN_CONTENT = re.compile(r"AGE-SECRET-KEY-1[0-9A-Z]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----")


def load(path: str | Path) -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def dump(path: str | Path, data: dict) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_stage(path: str, name: str, status: str, seconds: str) -> int:
    data = load(path)
    data[name] = {"status": status, "seconds": int(seconds)}
    dump(path, data)
    return 0


def cmd_build_record(path: str, *pairs: str) -> int:
    dump(path, dict(p.split("=", 1) for p in pairs))
    return 0


def cmd_get(path: str, key: str) -> int:
    print(load(path)[key])
    return 0


def cmd_trivy_policy(report_path: str, version_path: str, out_path: str) -> int:
    report = load(report_path)
    if not report.get("Results") and not report.get("ArtifactName"):
        print("trivy: отчёт пуст или повреждён — сканирование не считается успешным", file=sys.stderr)
        return 1
    version = load(version_path)
    db = version.get("VulnerabilityDB") or {}
    if not db.get("UpdatedAt"):
        print("trivy: нет метаданных базы уязвимостей — результат недостоверен", file=sys.stderr)
        return 1
    counts: dict[str, int] = {}
    blocking, unfixed_high = [], 0
    secrets_found = []
    for result in report.get("Results") or []:
        for v in result.get("Vulnerabilities") or []:
            sev = v.get("Severity", "UNKNOWN")
            counts[sev] = counts.get(sev, 0) + 1
            if sev in BLOCKING_SEVERITIES:
                if v.get("FixedVersion"):
                    blocking.append(
                        f"{v['VulnerabilityID']} {v.get('PkgName')} {v.get('InstalledVersion')}"
                        f" → {v['FixedVersion']} ({sev})"
                    )
                else:
                    unfixed_high += 1
        for s in result.get("Secrets") or []:
            secrets_found.append(f"{result.get('Target')}: {s.get('RuleID')}")
    passed = not blocking and not secrets_found
    summary = {
        "result": "passed" if passed else "failed",
        "policy": "блокируют HIGH/CRITICAL с доступным исправлением и любые секреты; "
        "исключения — только адресно в .trivyignore.yaml со сроком",
        "version": version.get("Version"),
        "db_version": db.get("Version"),
        "db_updated_at": db.get("UpdatedAt"),
        "db_downloaded_at": db.get("DownloadedAt"),
        "counts": counts,
        "blocking": blocking,
        "unfixed_high_critical": unfixed_high,
        "secrets": secrets_found,
        "artifact": report.get("ArtifactName"),
    }
    dump(out_path, summary)
    print(
        f"Trivy {summary['version']} (DB {db.get('UpdatedAt')}): {counts or 'уязвимостей нет'}; "
        f"блокирующих: {len(blocking)}, секретов: {len(secrets_found)}, HIGH/CRITICAL без исправления: "
        f"{unfixed_high}",
        file=sys.stderr,
    )
    for item in blocking + secrets_found:
        print(f"  BLOCK {item}", file=sys.stderr)
    return 0 if passed else 1


def cmd_require_passed(summary_path: str) -> int:
    if load(summary_path).get("result") != "passed":
        print("публикация запрещена: образ не прошёл политику Trivy", file=sys.stderr)
        return 1
    return 0


def cmd_provenance(art_dir: str, image_ref: str, digest: str) -> int:
    art = Path(art_dir)
    build = load(art / "build.json")
    trivy = load(art / "trivy-summary.json")
    stages = {k: v["status"] for k, v in load(art / "stages.json").items()}
    stages["push"] = "passed"
    prov = {
        "schema": 1,
        "generated_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version": build["version"],
        "git_sha": build["git_sha"],
        "fault_mode": build["fault_mode"],
        "build_time": build["build_time"],
        "base_image": build["base_image"],
        "image": {"ref": image_ref, "digest": digest, "tag": build["image_tag"], "local_id": build["local_id"]},
        "builder": {"docker": build.get("docker")},
        "trivy": {
            k: trivy.get(k)
            for k in ("result", "version", "db_version", "db_updated_at", "counts", "blocking", "unfixed_high_critical")
        },
        "stages": stages,
        "ci": {
            "runner": "github-actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "local",
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "workflow": os.environ.get("GITHUB_WORKFLOW"),
            "ref": os.environ.get("GITHUB_REF"),
            # стадии, выполненные отдельными job того же workflow (гарантирует needs:)
            "required_jobs_passed": [j for j in os.environ.get("CI_REQUIRED_JOBS", "").split(",") if j],
        },
    }
    dump(art / "provenance.json", prov)
    return 0


def cmd_extract_configmap(manifest_path: str, name: str, key: str) -> int:
    for doc in yaml.safe_load_all(Path(manifest_path).read_text(encoding="utf-8")):
        if doc and doc.get("kind") == "ConfigMap" and doc["metadata"]["name"] == name:
            sys.stdout.write(doc["data"][key])
            return 0
    print(f"ConfigMap {name} не найден", file=sys.stderr)
    return 1


def cmd_check_dashboards(directory: str) -> int:
    errors = []
    for path in sorted(Path(directory).glob("*.json")):
        dash = json.loads(path.read_text(encoding="utf-8"))
        if not dash.get("uid"):
            errors.append(f"{path.name}: нет uid")
        for panel in dash.get("panels", []):
            if panel.get("type") == "row":
                continue
            ds = (panel.get("datasource") or {}).get("uid")
            if ds != "prometheus":
                errors.append(f"{path.name}: панель '{panel.get('title')}' ссылается на datasource {ds}")
            if not panel.get("targets"):
                errors.append(f"{path.name}: панель '{panel.get('title')}' без запросов")
    for e in errors:
        print(e, file=sys.stderr)
    return 1 if errors else 0


def cmd_check_trivyignore(path: str) -> int:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    errors = []
    today = dt.date.today()
    for section in ("vulnerabilities", "secrets", "misconfigurations"):
        for entry in data.get(section) or []:
            ident = entry.get("id", "?")
            if not entry.get("statement"):
                errors.append(f"{ident}: нет обоснования (statement)")
            exp = entry.get("expired_at")
            if not exp:
                errors.append(f"{ident}: нет срока пересмотра (expired_at)")
                continue
            exp_date = exp if isinstance(exp, dt.date) else dt.date.fromisoformat(str(exp)[:10])
            if exp_date < today:
                errors.append(f"{ident}: исключение просрочено ({exp_date})")
            if (exp_date - today).days > MAX_EXCEPTION_DAYS:
                errors.append(f"{ident}: срок исключения больше {MAX_EXCEPTION_DAYS} дней")
    for e in errors:
        print(f".trivyignore.yaml: {e}", file=sys.stderr)
    return 1 if errors else 0


def cmd_check_tracked_files(root: str) -> int:
    files = subprocess.run(
        ["git", "-C", root, "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    errors = [f for f in files if any(p.search(f) for p in FORBIDDEN_TRACKED) and not f.endswith(".example")]
    for f in files:
        p = Path(root) / f
        if p.is_file() and p.stat().st_size < 2_000_000:
            try:
                if FORBIDDEN_CONTENT.search(p.read_text(encoding="utf-8", errors="ignore")):
                    errors.append(f"{f}: содержит закрытый ключ")
            except OSError:
                pass
    for e in errors:
        print(f"в Git не должно быть: {e}", file=sys.stderr)
    print(f"проверено отслеживаемых файлов: {len(files)}, нарушений: {len(errors)}", file=sys.stderr)
    return 1 if errors else 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    name = "cmd_" + sys.argv[1].replace("-", "_")
    handler = globals().get(name)
    if not handler:
        print(f"неизвестная команда {sys.argv[1]}", file=sys.stderr)
        return 2
    return handler(*sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
