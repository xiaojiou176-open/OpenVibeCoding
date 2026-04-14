from pathlib import Path

import pytest
from fastapi import HTTPException

from openvibecoding_orch.api import main as api_main
from openvibecoding_orch.runners import agents_runner
from openvibecoding_orch.scheduler import core_helpers
from openvibecoding_orch.store.run_store import RunStore


def test_agents_runner_guard_clauses() -> None:
    assert agents_runner._codex_allowed({}) is False
    assert agents_runner._codex_allowed({"tool_permissions": {"mcp_tools": "codex"}}) is False
    assert agents_runner._shell_policy({}) == "deny"
    assert agents_runner._shell_policy({"tool_permissions": {"shell": ""}}) == "deny"
    assert agents_runner._is_valid_thread_id(None) is False
    assert agents_runner._is_valid_thread_id(" ") is False
    assert agents_runner._path_allowed("", ["allowed/"]) is False
    assert agents_runner._path_allowed("file.txt", [123, None]) is False


def test_scheduler_trace_url_early_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_TRACE_URL_TEMPLATE", "{missing}")
    assert core_helpers.trace_url("trace", "run") == ""

    monkeypatch.delenv("OPENVIBECODING_TRACE_URL_TEMPLATE", raising=False)
    monkeypatch.delenv("OPENVIBECODING_TRACE_BASE_URL", raising=False)
    assert core_helpers.trace_url("trace", "run") == ""


def test_api_main_early_returns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    repo_root = tmp_path / "repo"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_REPO_ROOT", str(repo_root))

    default = {"ok": True}
    assert api_main._read_json(tmp_path / "missing.json", default) == default

    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert api_main._read_json(bad, default) == default

    assert api_main._read_report_file("missing-run", "missing.json") is None
    assert api_main._load_locks() == []
    assert api_main._extract_search_queries({"inputs": {"artifacts": "bad"}}) == []

    with pytest.raises(HTTPException) as excinfo:
        api_main._safe_artifact_target("run-x", "")
    assert excinfo.value.status_code == 400


def test_api_main_load_worktrees_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> list[str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(api_main.worktree_manager, "list_worktrees", _boom)
    assert api_main._load_worktrees() == [{"error": "boom"}]


def test_core_helpers_self_heal_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    text_file = tmp_path / "sample.txt"
    text_file.write_text("hello", encoding="utf-8")
    assert len(core_helpers.sha256_file(text_file)) == 64

    monkeypatch.delenv("OPENVIBECODING_TRACE_URL_TEMPLATE", raising=False)
    monkeypatch.setenv("OPENVIBECODING_TRACE_BASE_URL", "https://trace.local/base/")
    assert core_helpers.trace_url("trace-123", "run-123") == "https://trace.local/base/trace-123"

    no_media = core_helpers.artifact_ref_from_hash("a", "b.txt", "sha", 1)
    assert "media_type" not in no_media
    assert core_helpers.guess_media_type("unknown.bin") is None

    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "AGENTS.override.md").write_text("repo", encoding="utf-8")
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "AGENTS.override.md").write_text("home", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    overrides = core_helpers.detect_agents_overrides(repo_root)
    assert str(repo_root / "AGENTS.override.md") in overrides
    assert str(codex_home / "AGENTS.override.md") in overrides

    monkeypatch.setenv("OPENVIBECODING_CODEX_HOME_PER_RUN", "true")
    assert core_helpers.per_run_codex_home_enabled() is True

    base_home = tmp_path / "base_home"
    base_home.mkdir(parents=True, exist_ok=True)
    (base_home / "config.toml").write_text("cfg", encoding="utf-8")
    (base_home / "requirements.toml").write_text("req", encoding="utf-8")
    runtime_root = tmp_path / "runtime"
    target = core_helpers.materialize_codex_home(base_home, "run-1", runtime_root)
    assert (target / "config.toml").exists()
    assert (target / "requirements.toml").exists()

    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run("task_core_helpers")
    core_helpers.append_policy_violation(store, run_id, "policy boom", path="x/y.txt")
    core_helpers.append_gate_failed(store, run_id, "tool_gate", "blocked", schema="s", path="p")
    events_text = (tmp_path / "runs" / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "policy_violation" in events_text
    assert "gate_failed" in events_text

    policy_gate = core_helpers.build_policy_gate(
        integrated_gate={"ok": True},
        network_gate={"ok": True},
        mcp_gate={"ok": True},
        sampling_gate={"ok": False},
        tool_gate={"ok": True},
        human_approval_required=False,
        human_approved=None,
    )
    assert policy_gate["passed"] is False
    assert "sampling_gate" in policy_gate["violations"]

    assert core_helpers.extract_user_request({"inputs": {"spec": "   "}}) == ""
    assert core_helpers.extract_evidence_refs(None) == {}
