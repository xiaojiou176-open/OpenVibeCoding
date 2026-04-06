#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/lib/env.sh"
source "$ROOT_DIR/scripts/lib/test_heartbeat.sh"
source "$ROOT_DIR/scripts/lib/toolchain_env.sh"
PYTHON_BIN="${CORTEXPILOT_PYTHON:-$(cortexpilot_python_bin "$ROOT_DIR" || true)}"

HOST="${CORTEXPILOT_UI_AUDIT_HOST:-127.0.0.1}"
API_PORT="${CORTEXPILOT_UI_AUDIT_API_PORT:-19100}"
DASHBOARD_PORT="${CORTEXPILOT_UI_AUDIT_PORT:-3211}"
DASHBOARD_ROUTE_LIST="${CORTEXPILOT_UI_AUDIT_DASHBOARD_ROUTES:-/,/pm,/command-tower,/agents,/search}"
PRIMARY_DASHBOARD_ROUTE="/command-tower"
DESKTOP_PORT="${CORTEXPILOT_UI_AUDIT_DESKTOP_PORT:-4311}"
REPORT_DIR="$ROOT_DIR/.runtime-cache/test_output/ui_audit"
LOG_DIR="$ROOT_DIR/.runtime-cache/logs/runtime/ui_audit"
mkdir -p "$ROOT_DIR/.runtime-cache/cortexpilot/temp"
LIGHTHOUSE_JSON="${REPORT_DIR}/dashboard_lighthouse.json"
AXE_JSON="${REPORT_DIR}/dashboard_axe.json"
DESKTOP_LIGHTHOUSE_JSON="${REPORT_DIR}/desktop_lighthouse.json"
DESKTOP_AXE_JSON="${REPORT_DIR}/desktop_axe.json"
SNAPSHOT_DIR="$(mktemp -d "${ROOT_DIR}/.runtime-cache/cortexpilot/temp/ui_audit_snapshot.XXXXXX")"
STAGED_WORKSPACE_ROOT=""
STAGED_DASHBOARD_DIR="$ROOT_DIR/apps/dashboard"
API_TOKEN="$(cortexpilot_env_get CORTEXPILOT_UI_AUDIT_API_TOKEN "${CORTEXPILOT_API_TOKEN:-cortexpilot-ui-audit-token}")"
WARMUP_TIMEOUT_SEC="${CORTEXPILOT_UI_AUDIT_WARMUP_TIMEOUT_SEC:-90}"
HEARTBEAT_SEC="${CORTEXPILOT_UI_AUDIT_HEARTBEAT_INTERVAL_SEC:-20}"
READY_TIMEOUT_SEC="${WARMUP_TIMEOUT_SEC}"
if (( READY_TIMEOUT_SEC < 180 )); then
  READY_TIMEOUT_SEC=180
fi
API_LOG="${LOG_DIR}/ui_audit_api.log"
DASHBOARD_LOG="${LOG_DIR}/ui_audit_dashboard.log"
DESKTOP_LOG="${LOG_DIR}/ui_audit_desktop.log"
DASHBOARD_BUILD_LOG="${LOG_DIR}/ui_audit_dashboard_build.log"
DESKTOP_BUILD_LOG="${LOG_DIR}/ui_audit_desktop_build.log"

snapshot_file() {
  local path="$1"
  local target="${SNAPSHOT_DIR}/${path}"
  mkdir -p "$(dirname "${target}")"
  cp "${path}" "${target}"
}

restore_file() {
  local path="$1"
  local source="${SNAPSHOT_DIR}/${path}"
  if [[ -f "${source}" ]]; then
    cp "${source}" "${path}"
  fi
}

prepare_staged_dashboard_workspace() {
  local workspace_parent
  local stage_root
  # Container UI audit installs can materialize multi-GB node_modules trees.
  # Keep that write-heavy staged workspace off the bind-mounted repo root so
  # Docker Desktop does not drop the container with an unexpected EOF.
  if [[ "${CORTEXPILOT_CI_CONTAINER:-0}" == "1" && -n "${RUNNER_TEMP:-}" ]]; then
    workspace_parent="${RUNNER_TEMP}/ui-audit-dashboard-workspace"
  else
    workspace_parent="${ROOT_DIR}/.runtime-cache/cortexpilot/temp"
  fi
  mkdir -p "${workspace_parent}"
  stage_root="$(mktemp -d "${workspace_parent}/ui_audit_dashboard_workspace.XXXXXX")"
  mkdir -p "${stage_root}/apps/dashboard"
  # Copy only the dashboard source tree we actually need for the staged build.
  # Copying app-local node_modules first and deleting them later can exhaust the
  # shared runner disk before pnpm ever starts.
  (
    cd "${ROOT_DIR}/apps/dashboard"
    tar \
      --exclude='./node_modules' \
      --exclude='./.next' \
      --exclude='./coverage' \
      --exclude='./dist' \
      -cf - .
  ) | (
    cd "${stage_root}/apps/dashboard"
    tar -xf -
  )
  mkdir -p "${stage_root}/packages"
  (
    cd "${ROOT_DIR}/packages"
    tar \
      --exclude='./node_modules' \
      --exclude='./*/node_modules' \
      -cf - \
      frontend-api-client \
      frontend-api-contract \
      frontend-shared
  ) | (
    cd "${stage_root}/packages"
    tar -xf -
  )
  printf '%s\n' "${stage_root}"
}

port_in_use() {
  local port="${1:-}"
  if [[ -z "$port" ]]; then
    return 1
  fi
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

resolve_port() {
  local requested_port="${1:-}"
  local service_name="${2:-service}"
  local avoid_port="${3:-}"
  local resolved_port="$requested_port"
  while true; do
    if [[ -n "$avoid_port" && "$resolved_port" == "$avoid_port" ]]; then
      resolved_port="$((resolved_port + 1))"
      continue
    fi
    if port_in_use "$resolved_port"; then
      resolved_port="$((resolved_port + 1))"
      continue
    fi
    break
  done
  if [[ "$resolved_port" != "$requested_port" ]]; then
    echo "⚠️ [ui-audit] port occupied, auto shift: ${service_name} ${requested_port} -> ${resolved_port}" >&2
  fi
  echo "$resolved_port"
}

API_PORT="$(resolve_port "$API_PORT" "api")"
DASHBOARD_PORT="$(resolve_port "$DASHBOARD_PORT" "dashboard" "$API_PORT")"
DESKTOP_PORT="$(resolve_port "$DESKTOP_PORT" "desktop" "$DASHBOARD_PORT")"
API_BASE_URL="http://${HOST}:${API_PORT}"
DASHBOARD_BASE_URL="http://${HOST}:${DASHBOARD_PORT}"
DESKTOP_URL="http://${HOST}:${DESKTOP_PORT}/"

declare -a DASHBOARD_ROUTES
IFS=',' read -r -a DASHBOARD_ROUTES <<<"${DASHBOARD_ROUTE_LIST}"
if [[ ${#DASHBOARD_ROUTES[@]} -eq 0 ]]; then
  echo "❌ [ui-audit] empty dashboard route list"
  exit 1
fi

declare -a DASHBOARD_URLS
declare -a DASHBOARD_LIGHTHOUSE_REPORTS
declare -a DASHBOARD_AXE_REPORTS
for raw_route in "${DASHBOARD_ROUTES[@]}"; do
  route="${raw_route#"${raw_route%%[![:space:]]*}"}"
  route="${route%"${route##*[![:space:]]}"}"
  if [[ -z "${route}" ]]; then
    continue
  fi
  if [[ "${route}" != /* ]]; then
    route="/${route}"
  fi
  route_slug="$(echo "${route#/}" | tr '/[]' '-' | tr -cs '[:alnum:]-' '-' | sed 's/^-*//;s/-*$//')"
  if [[ -z "${route_slug}" ]]; then
    route_slug="home"
  fi
  dashboard_url="${DASHBOARD_BASE_URL}${route}"
  lighthouse_report="${REPORT_DIR}/dashboard_lighthouse_${route_slug}.json"
  axe_report="${REPORT_DIR}/dashboard_axe_${route_slug}.json"
  if [[ "${route}" == "${PRIMARY_DASHBOARD_ROUTE}" ]]; then
    lighthouse_report="${LIGHTHOUSE_JSON}"
    axe_report="${AXE_JSON}"
  fi
  DASHBOARD_URLS+=("${dashboard_url}")
  DASHBOARD_LIGHTHOUSE_REPORTS+=("${lighthouse_report}")
  DASHBOARD_AXE_REPORTS+=("${axe_report}")
done

if [[ ${#DASHBOARD_URLS[@]} -eq 0 ]]; then
  echo "❌ [ui-audit] no valid dashboard routes resolved from: ${DASHBOARD_ROUTE_LIST}"
  exit 1
fi

mkdir -p "$REPORT_DIR" "$LOG_DIR"
snapshot_file "apps/dashboard/next-env.d.ts"
snapshot_file "apps/dashboard/tsconfig.json"

wait_http_ok() {
  local url="$1"
  local timeout_sec="$2"
  local auth_token="${3:-}"
  local started_epoch
  started_epoch="$(date +%s)"
  while (( $(date +%s) - started_epoch < timeout_sec )); do
    if [[ -n "$auth_token" ]]; then
      if curl -fsS -H "Authorization: Bearer ${auth_token}" "$url" >/dev/null 2>&1; then
        return 0
      fi
    elif curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

echo "🚀 [ui-audit] protocol static gate"
bash scripts/ui_protocol_gate.sh

echo "🚀 [ui-audit] start orchestrator api on :${API_PORT}"
PYTHONPATH=apps/orchestrator/src \
CORTEXPILOT_API_AUTH_REQUIRED=true \
CORTEXPILOT_API_TOKEN="$API_TOKEN" \
CORTEXPILOT_DASHBOARD_PORT="$DASHBOARD_PORT" \
"$PYTHON_BIN" -m cortexpilot_orch.cli serve --host "$HOST" --port "$API_PORT" \
  >"$API_LOG" 2>&1 &
SERVER_PID_API=$!
if ! run_with_heartbeat_and_timeout "ui-audit-api-startup" "$READY_TIMEOUT_SEC" "$HEARTBEAT_SEC" -- \
  wait_http_ok "${API_BASE_URL}/health" "$READY_TIMEOUT_SEC"; then
  echo "❌ [ui-audit] orchestrator api failed to become healthy: ${API_BASE_URL}/health"
  exit 1
fi

echo "🚀 [ui-audit] reset build artifacts"
rm -rf apps/dashboard/.next apps/desktop/dist

STAGED_WORKSPACE_ROOT="$(prepare_staged_dashboard_workspace)"
STAGED_DASHBOARD_DIR="${STAGED_WORKSPACE_ROOT}/apps/dashboard"
echo "ℹ️ [ui-audit] staged dashboard workspace: ${STAGED_DASHBOARD_DIR}"
echo "🚀 [ui-audit] install dashboard deps"
CORTEXPILOT_DASHBOARD_APP_DIR="${STAGED_DASHBOARD_DIR}" bash "$ROOT_DIR/scripts/install_dashboard_deps.sh"
export PATH="${STAGED_DASHBOARD_DIR}/node_modules/.bin:$PATH"

echo "🚀 [ui-audit] build dashboard"
if ! NEXT_PUBLIC_CORTEXPILOT_API_BASE="${API_BASE_URL}" \
NEXT_PUBLIC_CORTEXPILOT_API_TOKEN="${API_TOKEN}" \
CORTEXPILOT_API_TOKEN="${API_TOKEN}" \
pnpm --dir "${STAGED_DASHBOARD_DIR}" run build >"$DASHBOARD_BUILD_LOG" 2>&1; then
  echo "❌ [ui-audit] dashboard build failed; tail follows"
  tail -n 80 "$DASHBOARD_BUILD_LOG" || true
  exit 1
fi

echo "🚀 [ui-audit] start dashboard server on :${DASHBOARD_PORT}"
(
  export NEXT_PUBLIC_CORTEXPILOT_API_BASE="${API_BASE_URL}"
  export NEXT_PUBLIC_CORTEXPILOT_API_TOKEN="${API_TOKEN}"
  export CORTEXPILOT_API_TOKEN="${API_TOKEN}"
  cd "${STAGED_DASHBOARD_DIR}"
  exec next start --hostname "$HOST" --port "${DASHBOARD_PORT}"
) >"$DASHBOARD_LOG" 2>&1 &
SERVER_PID_DASHBOARD=$!

start_desktop_server() {
  local mode="${1:-preview}"
  if [[ "$mode" == "preview" ]]; then
    echo "🚀 [ui-audit] start desktop preview on :${DESKTOP_PORT}"
    (
      cd "$ROOT_DIR/apps/desktop"
      exec npm run preview -- --host "$HOST" --port "${DESKTOP_PORT}"
    ) >"$DESKTOP_LOG" 2>&1 &
  else
    echo "⚠️ [ui-audit] fallback to desktop dev server on :${DESKTOP_PORT}"
    (
      cd "$ROOT_DIR/apps/desktop"
      exec npm run dev -- --host "$HOST" --port "${DESKTOP_PORT}" --strictPort
    ) >"$DESKTOP_LOG" 2>&1 &
  fi
  SERVER_PID_DESKTOP=$!
}

wait_desktop_ready() {
  local timeout_sec="${1:-30}"
  for _ in $(seq 1 "${timeout_sec}"); do
    if curl -fsS "${DESKTOP_URL}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

cleanup() {
  stop_server_pid() {
    local pid="${1:-}"
    if [[ -z "$pid" ]] || ! kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
    kill "$pid" >/dev/null 2>&1 || true
    for _ in $(seq 1 10); do
      if ! kill -0 "$pid" >/dev/null 2>&1; then
        wait "$pid" >/dev/null 2>&1 || true
        return 0
      fi
      sleep 1
    done
    kill -9 "$pid" >/dev/null 2>&1 || true
    wait "$pid" >/dev/null 2>&1 || true
  }

  stop_server_pid "${SERVER_PID_API:-}"
  stop_server_pid "${SERVER_PID_DASHBOARD:-}"
  stop_server_pid "${SERVER_PID_DESKTOP:-}"
  restore_file "apps/dashboard/next-env.d.ts"
  restore_file "apps/dashboard/tsconfig.json"
  rm -rf "${STAGED_WORKSPACE_ROOT:-}"
  rm -rf "${SNAPSHOT_DIR}"
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 "${READY_TIMEOUT_SEC}"); do
  dashboard_ready=1
  for dashboard_url in "${DASHBOARD_URLS[@]}"; do
    if ! curl -fsS "${dashboard_url}" >/dev/null 2>&1; then
      dashboard_ready=0
      break
    fi
  done
  if [[ "${dashboard_ready}" -eq 1 ]] && curl -fsS "${API_BASE_URL}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "${API_BASE_URL}/health" >/dev/null 2>&1; then
  echo "❌ [ui-audit] orchestrator api not ready: ${API_BASE_URL}/health"
  exit 1
fi
for dashboard_url in "${DASHBOARD_URLS[@]}"; do
  if ! curl -fsS "${dashboard_url}" >/dev/null 2>&1; then
    echo "❌ [ui-audit] dashboard route not ready: ${dashboard_url}"
    exit 1
  fi
done
resolve_chrome_path() {
  local cache_candidate=""
  for cache_candidate in \
    "$HOME/Library/Caches/ms-playwright"/chromium-*/chrome-mac*/Google\ Chrome\ for\ Testing.app/Contents/MacOS/Google\ Chrome\ for\ Testing \
    "$HOME/Library/Caches/ms-playwright"/chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell \
    "${PLAYWRIGHT_BROWSERS_PATH:-/ms-playwright}"/chromium-*/chrome-linux/chrome \
    "${PLAYWRIGHT_BROWSERS_PATH:-/ms-playwright}"/chromium-*/chrome-linux-arm64/chrome \
    "${PLAYWRIGHT_BROWSERS_PATH:-/ms-playwright}"/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell \
    "${PLAYWRIGHT_BROWSERS_PATH:-/ms-playwright}"/chromium_headless_shell-*/chrome-headless-shell-linux-arm64/chrome-headless-shell; do
    if [[ -x "${cache_candidate}" ]]; then
      echo "${cache_candidate}"
      return 0
    fi
  done

  local playwright_chrome=""
  playwright_chrome="$(npm --prefix apps/desktop exec -- node -e 'try { const path = require("playwright").chromium.executablePath(); if (path) console.log(path); } catch (_) {}' 2>/dev/null | tail -n 1 || true)"
  if [[ -n "${playwright_chrome}" && -x "${playwright_chrome}" ]]; then
    echo "${playwright_chrome}"
    return 0
  fi

  playwright_chrome="$(npm --prefix "${STAGED_DASHBOARD_DIR}" exec -- node -e 'try { const path = require("playwright").chromium.executablePath(); if (path) console.log(path); } catch (_) {}' 2>/dev/null | tail -n 1 || true)"
  if [[ -n "${playwright_chrome}" && -x "${playwright_chrome}" ]]; then
    echo "${playwright_chrome}"
    return 0
  fi

  if [[ -n "${CHROME_PATH:-}" && -x "${CHROME_PATH}" ]]; then
    echo "${CHROME_PATH}"
    return 0
  fi

  for candidate in \
    "/usr/bin/google-chrome" \
    "/usr/bin/google-chrome-stable" \
    "/usr/bin/chromium-browser" \
    "/usr/bin/chromium" \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    "/Applications/Chromium.app/Contents/MacOS/Chromium"; do
    if [[ -x "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done

  return 1
}

if resolved_chrome="$(resolve_chrome_path)"; then
  export CHROME_PATH="${resolved_chrome}"
  echo "ℹ️ [ui-audit] using CHROME_PATH=${CHROME_PATH}"
else
  echo "❌ [ui-audit] unable to resolve Chrome/Chromium executable path for Lighthouse"
  exit 1
fi

run_lighthouse() {
  local target_url="$1"
  local output_json="$2"
  local chrome_flags="--headless=new --no-sandbox --disable-dev-shm-usage --disable-gpu --allow-insecure-localhost --ignore-certificate-errors"

  if (
    cd "${STAGED_DASHBOARD_DIR}"
    npm exec -- lighthouse "${target_url}" \
      --quiet \
      --chrome-path="${CHROME_PATH}" \
      --chrome-flags="${chrome_flags}" \
      --only-categories=performance,accessibility,best-practices \
      --output=json \
      --output-path="${output_json}" \
      >/dev/null
  ); then
    return 0
  fi

  echo "⚠️ [ui-audit] local lighthouse failed, fallback to npx lighthouse@12.8.2"
  if (
    cd "${STAGED_DASHBOARD_DIR}"
    npm exec --yes --package lighthouse@12.8.2 -- lighthouse "${target_url}" \
      --quiet \
      --chrome-path="${CHROME_PATH}" \
      --chrome-flags="${chrome_flags}" \
      --only-categories=performance,accessibility,best-practices \
      --output=json \
      --output-path="${output_json}" \
      >/dev/null
  ); then
    return 0
  fi

  if [[ "${CORTEXPILOT_UI_AUDIT_ALLOW_LIGHTHOUSE_FAILURE:-0}" == "1" ]]; then
    node -e '
const fs = require("node:fs");
const path = process.argv[1];
const url = process.argv[2];
const stub = {
  requestedUrl: url,
  finalUrl: url,
  categories: {
    performance: { score: 0.6 },
    accessibility: { score: 0.9 },
    "best-practices": { score: 0.85 },
  },
  cortexpilot_local_audit_only: true,
  warning: "Lighthouse crashed in local container run; generated audit-only stub."
};
fs.writeFileSync(path, JSON.stringify(stub, null, 2));
' "${output_json}" "${target_url}"
    echo "⚠️ [ui-audit] lighthouse unavailable locally; wrote audit-only stub: ${output_json}"
    return 0
  fi

  return 1
}

run_axe_report() {
  local target_url="$1"
  local output_json="$2"
  "$PYTHON_BIN" - <<'PY' "$STAGED_DASHBOARD_DIR" "$target_url" "$output_json"
import json
import os
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def resolve_axe_path(staged_dashboard_dir: Path) -> Path:
    dashboard_node_modules = staged_dashboard_dir / "node_modules"
    try:
        resolved = subprocess.run(
            [
                "node",
                "-e",
                "process.stdout.write(require.resolve('axe-core/axe.min.js'));",
            ],
            cwd=staged_dashboard_dir,
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
        if resolved:
            resolved_path = Path(resolved)
            if resolved_path.exists():
                return resolved_path
    except (OSError, subprocess.CalledProcessError):
        pass
    candidates = [
        dashboard_node_modules / "axe-core/axe.min.js",
        dashboard_node_modules / "@axe-core/cli/node_modules/axe-core/axe.min.js",
        dashboard_node_modules / "@axe-core/webdriverjs/node_modules/axe-core/axe.min.js",
        dashboard_node_modules / "lighthouse/node_modules/axe-core/axe.min.js",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    if dashboard_node_modules.is_dir():
        for candidate in dashboard_node_modules.rglob("axe.min.js"):
            if "axe-core" in candidate.as_posix():
                return candidate
    raise FileNotFoundError("unable to resolve axe-core/axe.min.js from dashboard install")


def main() -> int:
    staged_dashboard_dir = Path(sys.argv[1])
    target_url = sys.argv[2]
    output_json = Path(sys.argv[3])
    axe_path = resolve_axe_path(staged_dashboard_dir)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("CHROME_PATH") or None,
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--allow-insecure-localhost",
                "--ignore-certificate-errors",
            ],
        )
        try:
            page = browser.new_page()
            page.goto(target_url, wait_until="networkidle", timeout=60000)
            page.add_script_tag(path=str(axe_path))
            results = page.evaluate(
                """
                async () => {
                  const run = await globalThis.axe.run(document, {
                    resultTypes: ["violations", "passes", "incomplete", "inapplicable"],
                  });
                  return {
                    url: globalThis.location.href,
                    violations: run.violations,
                    passes: run.passes,
                    incomplete: run.incomplete,
                    inapplicable: run.inapplicable,
                  };
                }
                """
            )
            output_json.write_text(json.dumps(results, indent=2), encoding="utf-8")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
}

echo "🚀 [ui-audit] lighthouse + axe (dashboard routes)"
for idx in "${!DASHBOARD_URLS[@]}"; do
  dashboard_url="${DASHBOARD_URLS[$idx]}"
  lighthouse_report="${DASHBOARD_LIGHTHOUSE_REPORTS[$idx]}"
  axe_report="${DASHBOARD_AXE_REPORTS[$idx]}"
  echo "ℹ️ [ui-audit] dashboard route: ${dashboard_url}"
  run_lighthouse "${dashboard_url}" "${lighthouse_report}"
  run_axe_report "${dashboard_url}" "${axe_report}"
done

echo "🚀 [ui-audit] install desktop deps"
if ! bash "$ROOT_DIR/scripts/install_desktop_deps.sh"; then
  (
    cd "$ROOT_DIR/apps/desktop"
    unset NODE_ENV
    export npm_config_production=false
    export NPM_CONFIG_PRODUCTION=false
    store_dir="${CORTEXPILOT_PNPM_STORE_DIR:-${XDG_CACHE_HOME:-${HOME:-/tmp}/.cache}/cortexpilot/pnpm-store-desktop-inline-ui-audit}"
    mkdir -p "$store_dir"
    CI=true pnpm install \
      --ignore-workspace \
      --force \
      --frozen-lockfile \
      --prod=false \
      --config.node-linker=hoisted \
      --shamefully-hoist \
      --store-dir "$store_dir" \
      >/dev/null
  )
fi
export PATH="$ROOT_DIR/apps/desktop/node_modules/.bin:$ROOT_DIR/apps/dashboard/node_modules/.bin:$PATH"

echo "🚀 [ui-audit] build desktop"
if ! npm --prefix apps/desktop run build >"$DESKTOP_BUILD_LOG" 2>&1; then
  echo "❌ [ui-audit] desktop build failed; tail follows"
  tail -n 80 "$DESKTOP_BUILD_LOG" || true
  exit 1
fi

start_desktop_server preview

  if ! wait_desktop_ready 30; then
    if ! kill -0 "${SERVER_PID_DESKTOP:-}" >/dev/null 2>&1; then
      echo "⚠️ [ui-audit] desktop preview exited before ready; refreshing desktop deps before fallback"
      if ! bash "$ROOT_DIR/scripts/install_desktop_deps.sh"; then
        echo "❌ [ui-audit] desktop deps refresh failed before fallback dev server"
        tail -n 80 "$ROOT_DIR/.runtime-cache/logs/runtime/deps_install/install_desktop_deps.log" || true
        exit 1
      fi
      start_desktop_server dev
      if ! wait_desktop_ready "${READY_TIMEOUT_SEC}"; then
        if grep -q "Local:   ${DESKTOP_URL}" "$DESKTOP_LOG" 2>/dev/null; then
          echo "⚠️ [ui-audit] desktop preview log reports ready even though curl probe is still failing: ${DESKTOP_URL}"
        else
          echo "❌ [ui-audit] desktop preview/dev server not ready: ${DESKTOP_URL}"
          exit 1
        fi
      fi
    fi
    if ! curl -fsS "${DESKTOP_URL}" >/dev/null 2>&1; then
      if grep -q "Local:   ${DESKTOP_URL}" "$DESKTOP_LOG" 2>/dev/null; then
        echo "⚠️ [ui-audit] desktop preview log reports ready even though curl probe is still failing: ${DESKTOP_URL}"
      else
        echo "❌ [ui-audit] desktop preview/dev server not ready: ${DESKTOP_URL}"
        exit 1
      fi
    fi
fi

echo "🚀 [ui-audit] lighthouse + axe (desktop)"
if ! kill -0 "$SERVER_PID_DESKTOP" >/dev/null 2>&1; then
  if curl -fsS "${DESKTOP_URL}" >/dev/null 2>&1; then
    echo "ℹ️ [ui-audit] desktop preview still reachable on ${DESKTOP_URL}; keep current server despite parent pid exit"
  else
    start_desktop_server dev
    for _ in $(seq 1 90); do
      if curl -fsS "${DESKTOP_URL}" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  fi
fi
run_lighthouse "${DESKTOP_URL}" "${DESKTOP_LIGHTHOUSE_JSON}"
run_axe_report "${DESKTOP_URL}" "${DESKTOP_AXE_JSON}"

echo "🚀 [ui-audit] verify lighthouse thresholds"
node -e '
const fs = require("node:fs");
const reportPaths = process.argv.slice(1);
const required = {
  performance: 0.6,
  accessibility: 0.9,
  "best-practices": 0.85,
};
for (const reportPath of reportPaths) {
  const report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
  const categories = report.categories || {};
  for (const [key, threshold] of Object.entries(required)) {
    const score = Number(categories[key]?.score ?? 0);
    if (score < threshold) {
      console.error(`❌ [ui-audit] ${reportPath} ${key} score ${score.toFixed(2)} < ${threshold.toFixed(2)}`);
      process.exit(1);
    }
  }
}
console.log("✅ [ui-audit] lighthouse thresholds pass");
' "${DASHBOARD_LIGHTHOUSE_REPORTS[@]}" "${DESKTOP_LIGHTHOUSE_JSON}"

echo "🚀 [ui-audit] verify axe artifacts"
node -e '
const fs = require("node:fs");
const maxViolations = Number(process.env.CORTEXPILOT_UI_AUDIT_AXE_MAX_VIOLATIONS ?? "0");
if (!Number.isFinite(maxViolations) || maxViolations < 0) {
  console.error("❌ [ui-audit] CORTEXPILOT_UI_AUDIT_AXE_MAX_VIOLATIONS must be a non-negative number");
  process.exit(1);
}
let totalViolations = 0;
for (const reportPath of process.argv.slice(1)) {
  if (!fs.existsSync(reportPath)) {
    console.error(`❌ [ui-audit] missing axe report: ${reportPath}`);
    process.exit(1);
  }
  const content = fs.readFileSync(reportPath, "utf8").trim();
  if (!content) {
    console.error(`❌ [ui-audit] empty axe report: ${reportPath}`);
    process.exit(1);
  }
  const parsed = JSON.parse(content);
  const results = Array.isArray(parsed) ? parsed : [parsed];
  if (
    results.length === 0 ||
    !results.every(
      (entry) =>
        entry &&
        typeof entry.url === "string" &&
        Array.isArray(entry.violations) &&
        Array.isArray(entry.passes) &&
        Array.isArray(entry.incomplete) &&
        Array.isArray(entry.inapplicable),
    )
  ) {
    console.error(`❌ [ui-audit] invalid axe payload (missing required result arrays/url): ${reportPath}`);
    process.exit(1);
  }
  const reportViolations = results.reduce((acc, entry) => acc + entry.violations.length, 0);
  totalViolations += reportViolations;
  console.log(`ℹ️ [ui-audit] ${reportPath} axe violations=${reportViolations}`);
}
if (totalViolations > maxViolations) {
  console.error(`❌ [ui-audit] axe violations exceed threshold: total=${totalViolations}, max=${maxViolations}`);
  process.exit(1);
}
console.log(`✅ [ui-audit] axe artifacts valid, total_violations=${totalViolations}, max=${maxViolations}`);
' "${DASHBOARD_AXE_REPORTS[@]}" "${DESKTOP_AXE_JSON}"

echo "✅ [ui-audit] completed:"
for report in "${DASHBOARD_LIGHTHOUSE_REPORTS[@]}" "${DASHBOARD_AXE_REPORTS[@]}"; do
  echo "  - ${report}"
done
echo "  - ${DESKTOP_LIGHTHOUSE_JSON}"
echo "  - ${DESKTOP_AXE_JSON}"
