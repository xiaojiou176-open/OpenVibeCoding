from __future__ import annotations

from pathlib import Path

import pytest

from openvibecoding_orch.queue import test_store as queue_test_store
from openvibecoding_orch.scheduler import test_test_pipeline_security as pipeline_security
from openvibecoding_orch.scheduler import test_wave_b1_security as wave_b1_security
from openvibecoding_orch.scheduler import test_wave_b2_regressions as wave_b2_regressions
from openvibecoding_orch.store import test_run_store_security as run_store_security


def test_proxy_wave_b1_mcp_payload_is_redacted() -> None:
    result = wave_b1_security.test_mcp_payload_is_redacted()
    assert result is None


def test_proxy_wave_b1_mcp_gate_fail_closed_on_invalid_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        wave_b1_security,
        "validate_mcp_tools",
        lambda *args, **kwargs: {"ok": False, "reason": "mcp allowlist invalid", "error": "parse error"},
    )
    wave_b1_security.test_mcp_gate_fail_closed_on_invalid_allowlist(tmp_path)


def test_proxy_wave_b1_reviewer_gate_detects_ignored_critical_file_changes(tmp_path: Path) -> None:
    wave_b1_security.test_reviewer_gate_detects_ignored_critical_file_changes(tmp_path)


def test_proxy_wave_b1_restricted_role_mcp_tools_are_converged() -> None:
    wave_b1_security.test_restricted_role_mcp_tools_are_converged()


def test_proxy_wave_b1_mcp_adapter_accepts_shell_on_request_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wave_b1_security.test_mcp_adapter_accepts_shell_on_request_semantics(tmp_path, monkeypatch)


def test_proxy_wave_b1_low_policy_pack_blocks_git_push(tmp_path: Path) -> None:
    wave_b1_security.test_low_policy_pack_blocks_git_push(tmp_path)


def test_proxy_wave_b2_isolated_execution_env_restores_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    wave_b2_regressions.test_isolated_execution_env_restores_environment(monkeypatch)


def test_proxy_wave_b2_cli_force_unlock_scoped_to_allowed_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wave_b2_regressions.test_cli_force_unlock_scoped_to_allowed_paths(tmp_path, monkeypatch)


def test_proxy_wave_b2_cli_force_unlock_rejects_invalid_allowed_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wave_b2_regressions.test_cli_force_unlock_rejects_invalid_allowed_paths(tmp_path, monkeypatch)


def test_proxy_queue_store_claim_next_is_atomic_for_single_pending_item(tmp_path: Path) -> None:
    queue_test_store.test_claim_next_is_atomic_for_single_pending_item(tmp_path)


def test_proxy_queue_store_fails_closed_when_fcntl_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue_test_store.test_queue_store_fails_closed_when_fcntl_unavailable(tmp_path, monkeypatch)


@pytest.mark.parametrize("bad_run_id", ["", "../escape", "run/../escape", "/abs/path", "..", "run..id"])
def test_proxy_run_store_rejects_unsafe_run_ids(tmp_path: Path, bad_run_id: str) -> None:
    run_store_security.test_run_dir_rejects_unsafe_run_ids(tmp_path, bad_run_id)


def test_proxy_run_store_accepts_safe_run_id(tmp_path: Path) -> None:
    run_store_security.test_run_dir_accepts_safe_run_id(tmp_path)


def test_proxy_run_store_active_contract_is_isolated_per_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_store_security.test_active_contract_is_isolated_per_run(tmp_path, monkeypatch)


def test_proxy_pipeline_read_artifact_text_blocks_path_traversal(tmp_path: Path) -> None:
    pipeline_security.test_read_artifact_text_blocks_path_traversal(tmp_path)


def test_proxy_pipeline_read_artifact_text_rejects_symlink_target(tmp_path: Path) -> None:
    pipeline_security.test_read_artifact_text_rejects_symlink_target(tmp_path)


def test_proxy_pipeline_cleanup_test_artifacts_does_not_delete_outside_file(tmp_path: Path) -> None:
    pipeline_security.test_cleanup_test_artifacts_does_not_delete_outside_file(tmp_path)
