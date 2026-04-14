#!/usr/bin/env bash

run_ci_step9_resilience_gates() {
  echo "🚀 [STEP 9/12] Start: Command Tower rollback/perf drills"
  if [ "${OPENVIBECODING_CI_RESILIENCE_GATES:-1}" = "1" ]; then
    PERF_API_HOST="${OPENVIBECODING_CI_PERF_API_HOST:-127.0.0.1}"
    PERF_API_PORT="${OPENVIBECODING_CI_PERF_API_PORT:-18080}"
    PERF_API_PORT="$(resolve_port "$PERF_API_PORT" "PERF_API_PORT" "OPENVIBECODING_CI_PERF_API_PORT")"
    PERF_API_BASE_URL="http://${PERF_API_HOST}:${PERF_API_PORT}"
    PERF_API_LOG=".runtime-cache/logs/runtime/ci_perf/ci_perf_api.log"
    STEP9_ROLLBACK_TIMEOUT_SEC="$(resolve_step_timeout "OPENVIBECODING_CI_STEP9_ROLLBACK_TIMEOUT_SEC" "1800" "OPENVIBECODING_CI_STEP9_TIMEOUT_SEC" "OPENVIBECODING_CI_STEP_TIMEOUT_SEC")"
    STEP9_PERF_ATTEMPT_TIMEOUT_SEC="$(resolve_step_timeout "OPENVIBECODING_CI_STEP9_PERF_ATTEMPT_TIMEOUT_SEC" "600" "OPENVIBECODING_CI_STEP9_TIMEOUT_SEC" "OPENVIBECODING_CI_STEP_TIMEOUT_SEC")"
    mkdir -p .runtime-cache/logs/runtime/ci_perf
    run_with_timeout_heartbeat_and_cleanup \
      "step9:rollback-drill" \
      "${STEP9_ROLLBACK_TIMEOUT_SEC}" \
      bash scripts/command_tower_rollback_drill.sh
    (
      PERF_API_PID=""
      cleanup_perf_api() {
        if [[ -n "$PERF_API_PID" ]] && kill -0 "$PERF_API_PID" >/dev/null 2>&1; then
          kill "$PERF_API_PID" >/dev/null 2>&1 || true
          wait "$PERF_API_PID" >/dev/null 2>&1 || true
        fi
      }
      trap cleanup_perf_api EXIT INT TERM
      PYTHONPATH=apps/orchestrator/src \
      OPENVIBECODING_API_AUTH_REQUIRED=false \
      "$PYTHON" -m openvibecoding_orch.cli serve --host "$PERF_API_HOST" --port "$PERF_API_PORT" \
        >"$PERF_API_LOG" 2>&1 &
      PERF_API_PID=$!
      perf_probe_ready=0
      for _ in $(seq 1 90); do
        if curl -fsS "${PERF_API_BASE_URL}/health" >/dev/null 2>&1; then
          perf_probe_ready=1
          break
        fi
        sleep 1
      done
      if [[ "$perf_probe_ready" -ne 1 ]]; then
        echo "❌ [ci] perf probe api not ready: ${PERF_API_BASE_URL} (log: ${PERF_API_LOG})"
        exit 1
      fi
      PERF_MAX_ATTEMPTS="${OPENVIBECODING_CI_PERF_MAX_ATTEMPTS:-2}"
      if [[ "$PERF_MAX_ATTEMPTS" -lt 1 ]]; then
        PERF_MAX_ATTEMPTS=1
      fi
      perf_attempt=1
      perf_ok=0
      while [[ "$perf_attempt" -le "$PERF_MAX_ATTEMPTS" ]]; do
        echo "🚀 [ci] perf smoke attempt ${perf_attempt}/${PERF_MAX_ATTEMPTS}"
        if run_with_timeout_heartbeat_and_cleanup \
          "step9:perf-smoke:attempt-${perf_attempt}" \
          "${STEP9_PERF_ATTEMPT_TIMEOUT_SEC}" \
          env \
            COMMAND_TOWER_BASE_URL="$PERF_API_BASE_URL" \
            COMMAND_TOWER_PERF_STRICT_HTTP=1 \
            bash scripts/command_tower_perf_smoke.sh; then
          perf_ok=1
          break
        fi
        if [[ "$perf_attempt" -lt "$PERF_MAX_ATTEMPTS" ]]; then
          echo "⚠️ [WARN] perf smoke attempt ${perf_attempt}/${PERF_MAX_ATTEMPTS} failed, retry in 3s"
          sleep 3
        fi
        perf_attempt=$((perf_attempt + 1))
      done
      perf_attempts_used="$perf_attempt"
      if [[ "$perf_ok" -ne 1 ]]; then
        write_retry_telemetry_report \
          "command_tower_perf_smoke" \
          "$perf_attempts_used" \
          "$PERF_MAX_ATTEMPTS" \
          "failure" \
          ".runtime-cache/test_output/ci_retry_telemetry/command_tower_perf_smoke.json"
        echo "❌ [ci] perf smoke failed after ${PERF_MAX_ATTEMPTS} attempts"
        exit 1
      fi
      write_retry_telemetry_report \
        "command_tower_perf_smoke" \
        "$perf_attempts_used" \
        "$PERF_MAX_ATTEMPTS" \
        "success" \
        ".runtime-cache/test_output/ci_retry_telemetry/command_tower_perf_smoke.json"
    )
  else
    require_skip_gate_break_glass_or_fail "OPENVIBECODING_CI_RESILIENCE_GATES" "resilience_gates_skip"
    echo "⚠️ [WARN] OPENVIBECODING_CI_RESILIENCE_GATES=0; skipping rollback/perf gates (break-glass)"
  fi
  echo "✅ [STEP 9/12] Completed"
}
