from __future__ import annotations

from pathlib import Path


def _script_text() -> str:
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "e2e_pm_chat_command_tower_success.sh"
    return script.read_text(encoding="utf-8")


def _runner_text() -> str:
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "e2e_pm_chat_command_tower_success_runner.py"
    return script.read_text(encoding="utf-8")


def test_pm_chat_e2e_real_mode_requires_ui_intake_by_default() -> None:
    text = _runner_text()
    assert 'OPENVIBECODING_E2E_REQUIRE_UI_INTAKE", "1" if run_mode == "real" else "0"' in text
    assert "failed to create intake through PM UI in strict mode" in text


def test_pm_chat_e2e_no_longer_falls_back_to_sessions_head() -> None:
    text = _runner_text()
    assert "sessions_payload[0]" not in text
    assert 'api_get_json("/api/pm/sessions")' not in text


def test_pm_chat_e2e_route_rewrite_does_not_override_headers() -> None:
    text = _runner_text()
    assert 'route.continue_(post_data=json.dumps(payload, ensure_ascii=False), headers=headers)' in text
    assert "route.continue_(method=\"POST\", headers=headers, post_data=" not in text


def test_pm_chat_e2e_resets_pm_dialog_before_first_send() -> None:
    text = _runner_text()
    assert 'reset_btn = page.get_by_role(' in text
    assert "Start first request" in text
    assert "新建 PM 对话" in text
    assert "if reset_btn.is_visible() and reset_btn.is_enabled():" in text


def test_pm_chat_e2e_explicitly_forbids_git_ops_in_objective_and_answers() -> None:
    text = _runner_text()
    assert "禁止执行任何版本控制命令" in text
    assert "git add/commit/push/rebase/reset" in text


def test_pm_chat_e2e_fallback_constraints_also_forbid_git_ops() -> None:
    text = _runner_text()
    assert '"constraints": [' in text
    assert "禁止执行任何版本控制命令（含 git add/commit/push/rebase/reset）" in text


def test_pm_chat_e2e_force_overrides_ui_default_acceptance_tests() -> None:
    text = _runner_text()
    assert "Always override UI defaults so E2E acceptance remains deterministic in clean worktrees." in text
    assert 'payload["acceptance_tests"] = [' in text
    assert 'if acceptance_cmd:' in text


def test_pm_chat_e2e_avoids_eval_for_codex_config_parsing() -> None:
    text = _script_text()
    assert 'eval "$(' not in text
    assert "tomllib" in text


def test_pm_chat_e2e_config_api_key_import_requires_explicit_opt_in() -> None:
    text = _script_text()
    assert (
        'IMPORT_CONFIG_API_KEY="${OPENVIBECODING_E2E_IMPORT_CONFIG_API_KEY:-0}"' in text
        or 'IMPORT_CONFIG_API_KEY="$(openvibecoding_env_get OPENVIBECODING_E2E_IMPORT_CONFIG_API_KEY "0")"' in text
    )
    assert 'if [[ "$IMPORT_CONFIG_API_KEY" == "1" ]]' in text


def test_pm_chat_e2e_default_acceptance_command_avoids_bash_prefix_for_tool_gate() -> None:
    text = _script_text()
    assert 'ACCEPTANCE_CMD="$(openvibecoding_env_get OPENVIBECODING_E2E_ACCEPTANCE_CMD "")"' in text
    assert 'ACCEPTANCE_CMD="python3 -m pytest apps/orchestrator/tests/test_schema_validation.py apps/orchestrator/tests/test_policy_registry_alignment.py -q"' in text
    assert 'verify_third_party_refs.sh --strict' not in text


def test_pm_chat_e2e_writes_evidence_directly_into_ui_regression_namespace() -> None:
    text = _script_text()
    assert 'UI_REG_OUT_DIR="$ROOT_DIR/.runtime-cache/test_output/ui_regression"' in text
    assert 'OUT_DIR="$UI_REG_OUT_DIR"' in text
    assert 'cp "$EVIDENCE_JSON" "$UI_REG_EVIDENCE_JSON"' not in text
    assert 'cp "$SCREEN_PM" "$UI_REG_SCREEN_PM"' not in text


def test_pm_chat_e2e_writes_runtime_logs_under_dedicated_subdirectory() -> None:
    text = _script_text()
    assert 'LOG_DIR="$ROOT_DIR/.runtime-cache/logs/runtime/pm_chat_e2e"' in text
    assert 'API_LOG="$LOG_DIR/e2e_pm_chat_api_${RUN_MODE}_${TS}.log"' in text
    assert 'UI_LOG="$LOG_DIR/e2e_pm_chat_dashboard_${RUN_MODE}_${TS}.log"' in text


def test_pm_chat_e2e_run_transport_error_is_fail_fast_with_snapshot() -> None:
    text = _runner_text()
    assert "if run_response_status == 0:" in text
    assert 'run request transport timeout observed; continue with downstream run_id discovery' in text
    assert '"reason": "run_id_detection_timeout"' in text


def test_pm_chat_e2e_plan_probe_timeout_does_not_fail_fast_before_run() -> None:
    text = _runner_text()
    assert "intake plan probe not ready before /run; continue with /run retries" in text
    assert "intake plan not ready before /run" not in text


def test_pm_chat_e2e_plan_probe_reads_intake_ssot_not_pm_session_view() -> None:
    text = _runner_text()
    probe_block = text.split("def ensure_intake_plan_ready(session_value: str, intake_value: str) -> tuple[bool, dict]:", 1)[1]
    probe_block = probe_block.split("if pending_questions:", 1)[0]
    assert 'api_get_json(f"/api/intake/{intake_value}")' in text
    assert 'api_get_json(f"/api/pm/sessions/{session_value}")' not in probe_block


def test_pm_chat_e2e_repairs_ui_created_intake_when_tool_set_missing() -> None:
    text = _runner_text()
    assert 'def _repair_intake_if_missing_tool_set(current_intake: str) -> tuple[str, str]:' in text
    assert 'progress("intake payload missing mcp_tool_set; recreate deterministic intake via API before /answer")' in text
    assert 'intake_id, session_id = _repair_intake_if_missing_tool_set(intake_id)' in text


def test_pm_chat_e2e_strict_acceptance_defaults_to_real_mode_and_supports_override() -> None:
    text = _runner_text()
    assert 'strict_acceptance_env = str(os.getenv("OPENVIBECODING_E2E_STRICT_ACCEPTANCE", "")).strip().lower()' in text
    assert 'strict_acceptance = str(run_mode).strip().lower() == "real"' in text
    assert 'payload["strict_acceptance"] = strict_acceptance' in text


def test_pm_chat_e2e_orchestration_smoke_must_not_treat_terminal_failure_as_success() -> None:
    text = _runner_text()
    assert "if status not in accepted_fail and (non_pm_roles or status in accepted_success or status in accepted_active):" in text
    assert 'raise RuntimeError(f"session run not successful: status={status!r}, failure_reason={failure_reason!r}")' in text
