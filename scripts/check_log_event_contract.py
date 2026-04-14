#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".runtime-cache" / "test_output" / "governance" / "log_event_contract_report.json"


def _load_schema() -> dict[str, Any]:
    return json.loads((ROOT / "schemas" / "log_event.v2.json").read_text(encoding="utf-8"))


def _openvibecoding_python() -> str:
    env_python = str(os.environ.get("OPENVIBECODING_PYTHON", "")).strip()
    machine_cache_root = str(os.environ.get("OPENVIBECODING_MACHINE_CACHE_ROOT", "")).strip()
    toolchain_cache_root = str(os.environ.get("OPENVIBECODING_TOOLCHAIN_CACHE_ROOT", "")).strip()
    runner_temp = str(os.environ.get("RUNNER_TEMP", "")).strip()
    xdg_cache_home = str(os.environ.get("XDG_CACHE_HOME", "")).strip()
    home_cache = str((Path.home() / ".cache")).strip()

    if not machine_cache_root:
        if toolchain_cache_root:
            machine_cache_root = str(Path(toolchain_cache_root).expanduser().parent)
        elif runner_temp:
            machine_cache_root = str(Path(runner_temp).expanduser() / "openvibecoding-machine-cache")
        elif xdg_cache_home:
            machine_cache_root = str(Path(xdg_cache_home).expanduser() / "openvibecoding")
        else:
            machine_cache_root = str(Path(home_cache).expanduser() / "openvibecoding")

    if not toolchain_cache_root:
        toolchain_cache_root = str(Path(machine_cache_root).expanduser() / "toolchains")

    candidates = [
        Path(env_python).expanduser() if env_python else None,
        Path(toolchain_cache_root).expanduser() / "python" / "current" / "bin" / "python",
        Path.home() / ".cache" / "openvibecoding" / "toolchains" / "python" / "current" / "bin" / "python",
        ROOT / ".runtime-cache" / "cache" / "toolchains" / "python" / "current" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.exists():
            return str(candidate)
    bootstrap = subprocess.run(
        [
            "bash",
            "-lc",
            "bash scripts/bootstrap.sh python >/dev/null && source scripts/lib/toolchain_env.sh && openvibecoding_python_bin \"$PWD\"",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if bootstrap.returncode == 0:
        resolved = bootstrap.stdout.strip().splitlines()
        if resolved:
            candidate = Path(resolved[-1]).expanduser()
            if candidate.exists():
                return str(candidate)
    return sys.executable


def _validate_payload(name: str, payload: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for field in required:
        if field not in payload:
            errors.append(f"{name}: missing required field `{field}`")

    extra_fields = sorted(set(payload) - set(properties))
    if extra_fields:
        errors.append(f"{name}: unexpected fields present: {', '.join(extra_fields)}")

    for field, definition in properties.items():
        if field not in payload:
            continue
        value = payload[field]
        expected_type = definition.get("type")
        if expected_type == "string":
            if not isinstance(value, str):
                errors.append(f"{name}: `{field}` must be string, got {type(value).__name__}")
            elif field in required and field not in {"artifact_kind", "run_id", "request_id", "trace_id", "session_id", "test_id"} and not value.strip():
                errors.append(f"{name}: `{field}` must be non-empty")
        elif expected_type == "object" and not isinstance(value, dict):
            errors.append(f"{name}: `{field}` must be object, got {type(value).__name__}")

        enum_values = definition.get("enum")
        if enum_values is not None and value not in enum_values:
            errors.append(f"{name}: `{field}` must be one of {enum_values}, got {value!r}")
        const_value = definition.get("const")
        if const_value is not None and value != const_value:
            errors.append(f"{name}: `{field}` must equal {const_value!r}, got {value!r}")

    return errors


def _backend_sample() -> dict[str, Any]:
    script = """
import json
import logging
import sys
from pathlib import Path

root = Path.cwd()
sys.path.insert(0, str(root / "apps" / "orchestrator" / "src"))
from openvibecoding_orch.observability.logger import JsonLineFormatter

formatter = JsonLineFormatter()
record = logging.LogRecord("openvibecoding", logging.INFO, "<log-contract>", 1, "evt", (), None)
record.component = "api"
record.service = "openvibecoding-orchestrator"
record.event = "API_REQUEST_COMPLETED"
record.run_id = "run_backend_sample"
record.request_id = "req_backend_sample"
record.trace_id = "trace_backend_sample"
record.session_id = "session_backend_sample"
record.test_id = "test_backend_sample"
record.source_kind = "app_log"
record.lane = "access"
record.meta = {"status": 200}
print(formatter.format(record))
"""
    result = subprocess.run(
        [_openvibecoding_python(), "-c", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout.strip())


def _node_sample(surface: str, component: str, event: str) -> dict[str, Any]:
    script = f"""
import {{ buildFrontendLogEvent }} from "./packages/frontend-api-client/src/core/observability.js";
const payload = buildFrontendLogEvent({{
  domain: {json.dumps("desktop" if surface == "desktop" else "ui")},
  surface: {json.dumps(surface)},
  component: {json.dumps(component)},
  event: {json.dumps(event)},
  run_id: "run_{surface}_sample",
  request_id: "req_{surface}_sample",
  trace_id: "trace_{surface}_sample",
  session_id: "session_{surface}_sample",
  test_id: "test_{surface}_sample",
  source_kind: "app_log",
  lane: "runtime",
  meta: {{ sample: true }}
}});
console.log(JSON.stringify(payload));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout.strip())


def _machine_sample(name: str, *, domain: str, surface: str, service: str, lane: str, source_kind: str = "ci_log") -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_path = Path(tmp_dir) / f"{name}.jsonl"
        meta_json = json.dumps({"sample": True, "source_kind": source_kind})
        command = (
            "source scripts/lib/log_event.sh && "
            "OPENVIBECODING_CI_LOG_EVENT_PATH="
            f"{json.dumps(str(log_path))} "
            "OPENVIBECODING_LOG_RUN_ID=run_ci_sample "
            "OPENVIBECODING_LOG_REQUEST_ID=req_ci_sample "
            "OPENVIBECODING_LOG_TRACE_ID=trace_ci_sample "
            "OPENVIBECODING_LOG_SESSION_ID=session_ci_sample "
            "OPENVIBECODING_LOG_TEST_ID=test_ci_sample "
            "OPENVIBECODING_LOG_ARTIFACT_KIND=governance_report "
            f"OPENVIBECODING_LOG_DOMAIN={domain} "
            f"OPENVIBECODING_LOG_SURFACE={surface} "
            f"OPENVIBECODING_LOG_SERVICE={service} "
            f"OPENVIBECODING_LOG_LANE={lane} "
            f"OPENVIBECODING_LOG_META_JSON={shlex.quote(meta_json)} "
            f"log_ci_event \"$PWD\" \"{name}\" \"{name.upper()}_CONTRACT_SAMPLE\" \"info\" \"$OPENVIBECODING_LOG_META_JSON\""
        )
        subprocess.run(["bash", "-lc", command], cwd=ROOT, check=True, capture_output=True, text=True)
        lines = log_path.read_text(encoding="utf-8").splitlines()
        if not lines:
            raise RuntimeError("ci log helper produced no payload")
        return json.loads(lines[-1])


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate OpenVibeCoding log_event.v2 contract across all emitters.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    schema = _load_schema()
    samples = {
        "backend": _backend_sample(),
        "dashboard": _node_sample("dashboard", "pm_shell", "pm_send_attempt"),
        "desktop": _node_sample("desktop", "ux_telemetry", "pm_send_blocked"),
        "ci": _machine_sample("ci_contract", domain="ci", surface="ci", service="openvibecoding-ci", lane="ci"),
        "governance": _machine_sample("governance_contract", domain="governance", surface="ci", service="openvibecoding-governance", lane="governance"),
    }

    errors: list[str] = []
    for name, payload in samples.items():
        errors.extend(_validate_payload(name, payload, schema))

    for name, payload in samples.items():
        if isinstance(payload.get("meta"), dict) and "raw_meta" in payload["meta"]:
            errors.append(f"{name}: `meta.raw_meta` fallback is forbidden in log_event.v2")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "log_event.v2",
        "ok": not errors,
        "samples": samples,
        "errors": errors,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if errors:
        print("❌ [log-event-contract] violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print(f"✅ [log-event-contract] contract satisfied: {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
