#!/usr/bin/env bash

run_ci_step10_pm_chat_e2e() {
  echo "🚀 [STEP 10/12] Start: PM Chat Command Tower E2E"
  if [[ "$CI_SLICE" == "resilience-and-e2e" && "${GITHUB_EVENT_NAME:-}" == "pull_request" && "${OPENVIBECODING_CI_PM_CHAT_ON_PR:-0}" != "1" ]]; then
    echo "ℹ️ [ci] skip PM chat on PR resilience slice; PR path keeps minimal real external probe only"
  elif [ "${OPENVIBECODING_CI_PM_CHAT_E2E:-1}" = "1" ]; then
    if ! load_pm_chat_policy_env_or_fail; then
      echo "❌ [ci] failed to load PM chat policy env from resolver"
      exit 1
    fi
    if [[ "${CI_PROFILE:-}" == "strict" ]] && [[ "${OPENVIBECODING_CI_PM_CHAT_ALLOW_MISSING_KEY:-0}" == "1" ]]; then
      echo "❌ [ci] OPENVIBECODING_CI_PM_CHAT_ALLOW_MISSING_KEY=1 is forbidden in strict profile" >&2
      exit 1
    fi
    if [[ -n "${CI:-}" ]] && [[ "${OPENVIBECODING_CI_PM_CHAT_ALLOW_MISSING_KEY:-0}" == "1" ]]; then
      PM_CHAT_MISSING_KEY_BREAK_GLASS_ACTIVE="$(resolve_ci_break_glass \
        "pm_chat_allow_missing_key" \
        "OPENVIBECODING_CI_PM_CHAT_ALLOW_MISSING_KEY_BREAK_GLASS" \
        "OPENVIBECODING_CI_PM_CHAT_ALLOW_MISSING_KEY_BREAK_GLASS_REASON" \
        "OPENVIBECODING_CI_PM_CHAT_ALLOW_MISSING_KEY_BREAK_GLASS_TICKET")" || {
        echo "❌ [ci] OPENVIBECODING_CI_PM_CHAT_ALLOW_MISSING_KEY=1 requires valid break-glass metadata"
        exit 1
      }
      if [[ "$PM_CHAT_MISSING_KEY_BREAK_GLASS_ACTIVE" != "1" ]]; then
        echo "❌ [ci] OPENVIBECODING_CI_PM_CHAT_ALLOW_MISSING_KEY=1 is blocked (fail-closed)."
        echo "❌ [ci] set OPENVIBECODING_CI_PM_CHAT_ALLOW_MISSING_KEY_BREAK_GLASS=1 with reason/ticket."
        exit 1
      fi
      echo "⚠️ [ci] PM chat missing-key override enabled via audited break-glass"
    fi
    if [[ "${CI_PROFILE:-}" == "strict" ]] && [[ "$PM_CHAT_MODE" != "real" ]]; then
      echo "❌ [ci] PM chat E2E must remain real in strict profile; mock/skip overrides are forbidden" >&2
      exit 1
    fi
    if [[ -n "${CI:-}" ]] && [[ "$PM_CHAT_MODE" != "real" ]]; then
      if [[ "${OPENVIBECODING_CI_PM_CHAT_ALLOW_MOCK_ON_CI:-0}" != "1" ]]; then
        echo "❌ [ci] PM chat E2E must run in real mode on CI (set OPENVIBECODING_CI_PM_CHAT_ALLOW_MOCK_ON_CI=1 for emergency override)"
        exit 1
      fi
      PM_CHAT_MOCK_MODE_BREAK_GLASS_ACTIVE="$(resolve_ci_break_glass \
        "pm_chat_allow_mock_on_ci" \
        "OPENVIBECODING_CI_PM_CHAT_ALLOW_MOCK_ON_CI_BREAK_GLASS" \
        "OPENVIBECODING_CI_PM_CHAT_ALLOW_MOCK_ON_CI_BREAK_GLASS_REASON" \
        "OPENVIBECODING_CI_PM_CHAT_ALLOW_MOCK_ON_CI_BREAK_GLASS_TICKET")" || {
        echo "❌ [ci] OPENVIBECODING_CI_PM_CHAT_ALLOW_MOCK_ON_CI=1 requires valid break-glass metadata"
        exit 1
      }
      if [[ "$PM_CHAT_MOCK_MODE_BREAK_GLASS_ACTIVE" != "1" ]]; then
        echo "❌ [ci] OPENVIBECODING_CI_PM_CHAT_ALLOW_MOCK_ON_CI=1 is blocked (fail-closed)."
        echo "❌ [ci] set OPENVIBECODING_CI_PM_CHAT_ALLOW_MOCK_ON_CI_BREAK_GLASS=1 with reason/ticket."
        exit 1
      fi
      echo "⚠️ [ci] PM chat mock mode override enabled via audited break-glass"
    fi
    if [[ -z "${CI:-}" ]] && [[ "${PM_CHAT_HAS_LLM_KEY:-0}" != "1" ]] && [[ -z "${OPENVIBECODING_CI_PM_CHAT_MODE:-}" ]] && [[ "$PM_CHAT_MODE" == "mock" ]]; then
      echo "⚠️ [WARN] missing LLM credentials in env/config, fallback PM chat E2E mode to mock"
    fi
    if [[ "$PM_CHAT_REQUIRES_KEY" == "1" ]]; then
      if [[ "${PM_CHAT_REQUIRES_GEMINI_KEY:-0}" == "1" ]]; then
        echo "❌ [ci] PM chat real E2E requires GEMINI_API_KEY/GOOGLE_API_KEY (or codex gemini provider token)"
      else
        echo "❌ [ci] PM chat real E2E requires LLM credential (env key or ~/.codex/config.toml provider token)"
      fi
      exit 1
    fi
    PM_CHAT_MAX_ATTEMPTS="${OPENVIBECODING_CI_PM_CHAT_MAX_ATTEMPTS:-4}"
    STEP10_PM_CHAT_ATTEMPT_TIMEOUT_SEC="$(resolve_step_timeout "OPENVIBECODING_CI_STEP10_PM_CHAT_ATTEMPT_TIMEOUT_SEC" "2400" "OPENVIBECODING_CI_STEP10_TIMEOUT_SEC" "OPENVIBECODING_CI_STEP_TIMEOUT_SEC")"
    if [[ "$PM_CHAT_MAX_ATTEMPTS" -lt 1 ]]; then
      PM_CHAT_MAX_ATTEMPTS=1
    fi
    pm_chat_attempt=1
    pm_chat_ok=0
    while [[ "$pm_chat_attempt" -le "$PM_CHAT_MAX_ATTEMPTS" ]]; do
      echo "🚀 [ci] PM chat E2E attempt ${pm_chat_attempt}/${PM_CHAT_MAX_ATTEMPTS}"
      set +e
      OPENVIBECODING_E2E_RUN_MODE="$PM_CHAT_MODE" \
      OPENVIBECODING_E2E_RUNNER="$PM_CHAT_RUNNER" \
      OPENVIBECODING_E2E_WEB_MODE="$PM_CHAT_WEB_MODE" \
      OPENVIBECODING_E2E_USE_CODEX_CONFIG="$PM_CHAT_USE_CODEX_CONFIG" \
      OPENVIBECODING_E2E_RUNTIME_OPTIONS_PROVIDER="${PM_CHAT_RUNTIME_OPTIONS_PROVIDER:-}" \
      OPENVIBECODING_E2E_CODEX_BASE_URL="${PM_CHAT_CODEX_BASE_URL:-}" \
      OPENVIBECODING_E2E_CODEX_PROVIDER="${PM_CHAT_CODEX_PROVIDER:-}" \
      OPENVIBECODING_E2E_CODEX_MODEL="${PM_CHAT_CODEX_MODEL:-}" \
      OPENVIBECODING_E2E_CODEX_KEY_SOURCE="${PM_CHAT_CODEX_KEY_SOURCE:-}" \
      OPENVIBECODING_MCP_CONNECT_TIMEOUT_SEC="${OPENVIBECODING_CI_PM_CHAT_MCP_CONNECT_TIMEOUT_SEC:-${OPENVIBECODING_MCP_CONNECT_TIMEOUT_SEC:-120}}" \
      OPENVIBECODING_MCP_TIMEOUT_SEC="${OPENVIBECODING_CI_PM_CHAT_MCP_TIMEOUT_SEC:-${OPENVIBECODING_MCP_TIMEOUT_SEC:-1200}}" \
      OPENVIBECODING_E2E_API_POST_TIMEOUT_SEC="${OPENVIBECODING_CI_PM_CHAT_API_POST_TIMEOUT_SEC:-420}" \
      OPENVIBECODING_E2E_STATUS_STAGNATION_SEC="${OPENVIBECODING_CI_PM_CHAT_STATUS_STAGNATION_SEC:-420}" \
      OPENVIBECODING_E2E_REEXEC_STRICT=true \
      run_with_timeout_heartbeat_and_cleanup \
        "step10:pm-chat-e2e:attempt-${pm_chat_attempt}" \
        "${STEP10_PM_CHAT_ATTEMPT_TIMEOUT_SEC}" \
        bash scripts/e2e_pm_chat_command_tower_success.sh
      pm_chat_status=$?
      set -e
      if [[ "$pm_chat_status" -eq 0 ]]; then
        pm_chat_ok=1
        break
      fi
      if [[ "$pm_chat_attempt" -lt "$PM_CHAT_MAX_ATTEMPTS" ]]; then
        echo "⚠️ [WARN] PM chat E2E attempt ${pm_chat_attempt}/${PM_CHAT_MAX_ATTEMPTS} failed, retry in 5s"
        sleep 5
      fi
      pm_chat_attempt=$((pm_chat_attempt + 1))
    done
    pm_chat_attempts_used="$pm_chat_attempt"
    if [[ "$pm_chat_ok" -ne 1 ]]; then
      write_retry_telemetry_report \
        "pm_chat_command_tower_e2e" \
        "$pm_chat_attempts_used" \
        "$PM_CHAT_MAX_ATTEMPTS" \
        "failure" \
        ".runtime-cache/test_output/ci_retry_telemetry/pm_chat_command_tower_e2e.json"
      echo "❌ [ci] PM chat E2E failed after ${PM_CHAT_MAX_ATTEMPTS} attempts"
      exit 1
    fi
    write_retry_telemetry_report \
      "pm_chat_command_tower_e2e" \
      "$pm_chat_attempts_used" \
      "$PM_CHAT_MAX_ATTEMPTS" \
      "success" \
      ".runtime-cache/test_output/ci_retry_telemetry/pm_chat_command_tower_e2e.json"
  else
    require_skip_gate_break_glass_or_fail "OPENVIBECODING_CI_PM_CHAT_E2E" "pm_chat_e2e_skip"
    echo "⚠️ [WARN] OPENVIBECODING_CI_PM_CHAT_E2E=0, skip PM chat e2e gate (break-glass)"
  fi
  echo "✅ [STEP 10/12] Completed"
}
