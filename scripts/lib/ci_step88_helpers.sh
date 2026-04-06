#!/usr/bin/env bash

run_ci_step88_ui_strict_click_gate() {
  UI_TRUTH_BATCH_RUN_ID="${CORTEXPILOT_CI_UI_TRUTH_BATCH_RUN_ID:-}"
  if [ -z "$UI_TRUTH_BATCH_RUN_ID" ]; then
    UI_TRUTH_BATCH_RUN_ID="$(resolve_ui_truth_batch_run_id_from_flake_report "${P0_REPORT_PATH:-}")"
  fi
  if [ -n "$UI_TRUTH_BATCH_RUN_ID" ]; then
    echo "ℹ️ [ci] ui truth batch run_id=${UI_TRUTH_BATCH_RUN_ID}"
  fi
  echo "🚀 [STEP 8.8/12] Start: UI strict click-governance intake"
  UI_STRICT_CLICK_GATE="${CORTEXPILOT_CI_UI_STRICT_CLICK_GATE:-1}"
  UI_STRICT_CLICK_REQUIRED="${CORTEXPILOT_CI_UI_STRICT_CLICK_REQUIRED:-1}"
  UI_STRICT_REPORT_ROOT="${CORTEXPILOT_CI_UI_STRICT_REPORT_ROOT:-.runtime-cache/test_output/ui_full_gemini_audit}"
  UI_STRICT_REPORT_PATH="${CORTEXPILOT_CI_UI_STRICT_REPORT_PATH:-}"
  UI_STRICT_REPORT_REQUIRE_COMPAT="${CORTEXPILOT_CI_UI_STRICT_REPORT_REQUIRE_COMPAT:-1}"
  UI_STRICT_REPORT_MAX_AGE_SEC="${CORTEXPILOT_CI_UI_STRICT_REPORT_MAX_AGE_SEC:-172800}"
  # Default mode is full Gemini verdict strict (fail on warn/fail verdicts).
  # Set CORTEXPILOT_CI_UI_STRICT_REQUIRE_GEMINI_VERDICT=0 only when explicitly opting into click-only strict mode.
  UI_STRICT_REQUIRE_GEMINI_VERDICT="${CORTEXPILOT_CI_UI_STRICT_REQUIRE_GEMINI_VERDICT:-1}"
  UI_TRUTH_CLICK_INVENTORY_REQUIRED="${CORTEXPILOT_CI_UI_CLICK_INVENTORY_REQUIRED:-$UI_STRICT_CLICK_REQUIRED}"
  UI_TRUTH_CLICK_INVENTORY_REPORT="${CORTEXPILOT_CI_UI_CLICK_INVENTORY_REPORT:-}"
  UI_STRICT_BREAK_GLASS_ACTIVE="$(resolve_ci_break_glass \
    "ui_strict_downgrade" \
    "CORTEXPILOT_CI_UI_STRICT_BREAK_GLASS" \
    "CORTEXPILOT_CI_UI_STRICT_BREAK_GLASS_REASON" \
    "CORTEXPILOT_CI_UI_STRICT_BREAK_GLASS_TICKET")"

  if [ "$UI_STRICT_CLICK_GATE" != "1" ] && [ "$UI_STRICT_BREAK_GLASS_ACTIVE" != "1" ]; then
    echo "❌ [ci] CORTEXPILOT_CI_UI_STRICT_CLICK_GATE=0 is blocked (fail-closed)."
    exit 1
  fi
  if [ "$UI_STRICT_CLICK_REQUIRED" != "1" ] && [ "$UI_STRICT_BREAK_GLASS_ACTIVE" != "1" ]; then
    echo "❌ [ci] CORTEXPILOT_CI_UI_STRICT_CLICK_REQUIRED!=1 is blocked (fail-closed)."
    exit 1
  fi
  if [ "$UI_STRICT_REQUIRE_GEMINI_VERDICT" != "0" ] && [ "$UI_STRICT_REQUIRE_GEMINI_VERDICT" != "1" ]; then
    echo "❌ [ci] CORTEXPILOT_CI_UI_STRICT_REQUIRE_GEMINI_VERDICT must be 0 or 1."
    exit 1
  fi
  if [ "$UI_STRICT_REQUIRE_GEMINI_VERDICT" = "0" ] && [ "$UI_STRICT_BREAK_GLASS_ACTIVE" != "1" ]; then
    echo "❌ [ci] CORTEXPILOT_CI_UI_STRICT_REQUIRE_GEMINI_VERDICT=0 is blocked (fail-closed). set CORTEXPILOT_CI_UI_STRICT_BREAK_GLASS=1 with CORTEXPILOT_CI_UI_STRICT_BREAK_GLASS_REASON and CORTEXPILOT_CI_UI_STRICT_BREAK_GLASS_TICKET."
    exit 1
  fi
  if [ "$UI_STRICT_CLICK_GATE" = "1" ]; then
    if [ -z "$UI_STRICT_REPORT_PATH" ]; then
      run_ci_ui_full_gemini_audit "ci_ui_full_gemini"
    fi
    if [ -n "$UI_STRICT_REPORT_PATH" ]; then
      echo "ℹ️ [ci] consume ui strict click report: ${UI_STRICT_REPORT_PATH}"
      STRICT_GATE_ARGS=(--report "$UI_STRICT_REPORT_PATH")
      if [ "$UI_STRICT_REQUIRE_GEMINI_VERDICT" != "1" ]; then
        STRICT_GATE_ARGS+=(--click-only)
      fi
      if [ "$UI_STRICT_BREAK_GLASS_ACTIVE" = "1" ]; then
        STRICT_GATE_ARGS+=(--allow-gemini-skipped)
      fi
      strict_gate_failed=0
      if ! CORTEXPILOT_UI_STRICT_BREAK_GLASS="$UI_STRICT_BREAK_GLASS_ACTIVE" \
        CORTEXPILOT_UI_STRICT_BREAK_GLASS_REASON="${CORTEXPILOT_CI_UI_STRICT_BREAK_GLASS_REASON:-}" \
        CORTEXPILOT_UI_STRICT_BREAK_GLASS_TICKET="${CORTEXPILOT_CI_UI_STRICT_BREAK_GLASS_TICKET:-}" \
        "$PYTHON" scripts/ui_full_e2e_gemini_strict_gate.py "${STRICT_GATE_ARGS[@]}"; then
        strict_gate_failed=1
      fi
      if [ "$strict_gate_failed" = "1" ]; then
        echo "❌ [ci] ui strict click gate validation failed"
        exit 1
      else
        if [ -z "$UI_TRUTH_CLICK_INVENTORY_REPORT" ]; then
          UI_TRUTH_CLICK_INVENTORY_REPORT="$(resolve_click_inventory_from_ui_full_report "$UI_STRICT_REPORT_PATH")"
        fi
        if [ -z "$UI_TRUTH_CLICK_INVENTORY_REPORT" ] || [ ! -f "$UI_TRUTH_CLICK_INVENTORY_REPORT" ]; then
          echo "❌ [ci] ui strict click gate missing click inventory report: ${UI_TRUTH_CLICK_INVENTORY_REPORT:-<empty>}"
          exit 1
        else
          UI_TRUTH_CLICK_INVENTORY_REQUIRED="1"
          if [ -n "${UI_TRUTH_BATCH_RUN_ID:-}" ]; then
            annotate_ui_truth_batch_run_id "$UI_STRICT_REPORT_PATH" "$UI_TRUTH_BATCH_RUN_ID"
          fi
        fi
      fi
    else
      echo "❌ [ci] ui strict click gate required but report missing (root=${UI_STRICT_REPORT_ROOT})"
      exit 1
    fi
  else
    echo "⚠️ [WARN] CORTEXPILOT_CI_UI_STRICT_CLICK_GATE=0 with break-glass"
  fi
  echo "✅ [STEP 8.8/12] Completed"
}
