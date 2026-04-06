#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR="${CORTEXPILOT_CI_CONTROL_PLANE_DOCTOR_OUT_DIR:-.runtime-cache/test_output/ci_control_plane_doctor}"
mkdir -p "$OUT_DIR"
REPORT_JSON="${OUT_DIR}/report.json"
REPORT_MD="${OUT_DIR}/summary.md"

REQUIRE_DOCKER="${CORTEXPILOT_DOCTOR_REQUIRE_DOCKER:-1}"
REQUIRE_SUDO="${CORTEXPILOT_DOCTOR_REQUIRE_SUDO:-1}"

check_cmd() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

tool_cache_ok=1
workspace="${GITHUB_WORKSPACE:-$ROOT_DIR}"
for key in AGENT_TOOLSDIRECTORY RUNNER_TOOL_CACHE; do
  value="${!key:-}"
  if [[ -n "$value" && "$value" == "$workspace"* ]]; then
    tool_cache_ok=0
  fi
done

docker_ok=0
sudo_ok=0
jq_ok=0
curl_ok=0
runner_temp_ok=0

if [[ "$REQUIRE_DOCKER" != "1" ]] || check_cmd docker; then
  docker_ok=1
fi
if [[ "$REQUIRE_SUDO" != "1" ]] || check_cmd sudo; then
  sudo_ok=1
fi
if check_cmd jq; then jq_ok=1; fi
if check_cmd curl; then curl_ok=1; fi
if [[ -n "${RUNNER_TEMP:-}" ]]; then runner_temp_ok=1; fi

allowlist_json='["CORTEXPILOT_DOC_GATE_MODE","CORTEXPILOT_DOC_GATE_BASE_SHA","CORTEXPILOT_DOC_GATE_HEAD_SHA","CORTEXPILOT_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE","CORTEXPILOT_CI_LIVE_PREFLIGHT_PROVIDER_API_MODE","CORTEXPILOT_CI_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE"]'

python3 - "$REPORT_JSON" "$REPORT_MD" "$docker_ok" "$sudo_ok" "$jq_ok" "$curl_ok" "$runner_temp_ok" "$tool_cache_ok" "$allowlist_json" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    report_json,
    report_md,
    docker_ok,
    sudo_ok,
    jq_ok,
    curl_ok,
    runner_temp_ok,
    tool_cache_ok,
    allowlist_json,
) = sys.argv[1:]

payload = {
    "report_type": "cortexpilot_ci_control_plane_doctor",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "checks": {
        "docker": docker_ok == "1",
        "sudo": sudo_ok == "1",
        "jq": jq_ok == "1",
        "curl": curl_ok == "1",
        "runner_temp": runner_temp_ok == "1",
        "tool_cache_contract": tool_cache_ok == "1",
    },
    "strict_ci_cortexpilot_allowlist": json.loads(allowlist_json),
}
Path(report_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
Path(report_md).write_text(
    "\n".join(
        [
            "## CI Control Plane Doctor",
            "",
            f"- docker: **{payload['checks']['docker']}**",
            f"- sudo: **{payload['checks']['sudo']}**",
            f"- jq: **{payload['checks']['jq']}**",
            f"- curl: **{payload['checks']['curl']}**",
            f"- runner_temp: **{payload['checks']['runner_temp']}**",
            f"- tool_cache_contract: **{payload['checks']['tool_cache_contract']}**",
            f"- strict_ci_cortexpilot_allowlist: `{', '.join(payload['strict_ci_cortexpilot_allowlist'])}`",
            "",
        ]
    )
    + "\n",
    encoding="utf-8",
)
PY

if [[ "$docker_ok" != "1" || "$sudo_ok" != "1" || "$jq_ok" != "1" || "$curl_ok" != "1" || "$runner_temp_ok" != "1" || "$tool_cache_ok" != "1" ]]; then
  echo "❌ [ci-control-plane-doctor] control-plane contract failed" >&2
  exit 1
fi

echo "✅ [ci-control-plane-doctor] control-plane contract ok"
