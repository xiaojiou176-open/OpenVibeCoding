from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from openvibecoding_orch.api import main_run_views_helpers
from openvibecoding_orch.api import main_state_store_helpers
from openvibecoding_orch.contract.compiler import build_role_binding_summary


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_main_run_views_helpers_branch_matrix(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    for run_id in ("run-a", "run-b", "run-c"):
        (runs_root / run_id).mkdir(parents=True, exist_ok=True)

    (runs_root / "run-a" / "reports").mkdir(parents=True, exist_ok=True)
    (runs_root / "run-a" / "reports" / "review_report.json").write_text(
        json.dumps({"ok": True}),
        encoding="utf-8",
    )
    (runs_root / "run-b" / "reports").mkdir(parents=True, exist_ok=True)
    (runs_root / "run-b" / "reports" / "review_report.json").write_text(
        "{not-json}",
        encoding="utf-8",
    )
    _write_json(runs_root / "run-a" / "manifest.json", {"task_id": "task-a", "status": "SUCCESS"})
    _write_json(runs_root / "run-a" / "contract.json", {"allowed_paths": ["apps/orchestrator/tests"]})
    (runs_root / "run-b" / "manifest.json").write_text("{broken", encoding="utf-8")
    _write_json(runs_root / "run-c" / "manifest.json", {"task_id": "task-c"})
    (runs_root / "run-a" / "diff_name_only.txt").write_text("a.py\n\nb.py\n", encoding="utf-8")

    def _read_events(run_id: str) -> list[object]:
        if run_id == "run-a":
            return [
                {"event": "OTHER"},
                {"event": "DIFF_GATE_RESULT", "context": {"reason": "old"}},
                {"event": "DIFF_GATE_RESULT", "context": {"reason": "latest"}},
            ]
        if run_id == "run-b":
            return [{"event": "OTHER"}]
        return []

    def _read_json(path: Path, default: object) -> object:
        if path.name == "manifest.json" and path.parent.name == "run-b":
            return "manifest-as-text"
        if path.name == "contract.json" and path.parent.name == "run-b":
            return ["contract-as-list"]
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return default
        return default

    diff_payload = main_run_views_helpers.list_diff_gate(
        runs_root=runs_root,
        read_events_fn=_read_events,
        read_json_fn=_read_json,
    )
    diff_by_run = {item["run_id"]: item for item in diff_payload}
    assert diff_by_run["run-a"]["diff_gate"] == {"reason": "latest"}
    assert diff_by_run["run-a"]["status"] == "SUCCESS"
    assert "run-b" not in diff_by_run
    assert "run-c" not in diff_by_run

    reports = main_run_views_helpers.list_reports_by_name(
        runs_root=runs_root,
        report_name="review_report.json",
    )
    reports_by_run = {item["run_id"]: item["report"] for item in reports}
    assert reports_by_run["run-a"] == {"ok": True}
    assert reports_by_run["run-b"]["raw"] == "{not-json}"

    agents_payload = main_run_views_helpers.list_agents(
        load_agent_registry_fn=lambda: {
            "role_contracts": {
                "WORKER": {
                    "purpose": "Execute contracted work.",
                    "system_prompt_ref": "policies/agents/codex/roles/50_worker_core.md",
                    "handoff_eligible": True,
                    "required_downstream_roles": ["REVIEWER"],
                    "fail_closed_conditions": ["scope drift"],
                }
            },
            "agents": [
                {"agent_id": "agent-a", "role": "WORKER"},
                "not-a-dict",
                {"agent_id": "agent-b", "role": "REVIEWER"},
            ]
        },
        load_locks_fn=lambda: [
            {"agent_id": "agent-a", "role": "WORKER", "path": "p1"},
            {"agent_id": "agent-a", "role": "WORKER", "path": "p2"},
            {"agent_id": "agent-a", "path": "missing-role"},
            {"role": "WORKER", "path": "missing-id"},
        ],
        build_role_binding_summary_fn=lambda contract: {
            "authority": "contract-derived-read-model",
            "source": "derived",
            "execution_authority": "task_contract",
            "skills_bundle_ref": {"status": "unresolved", "ref": None, "bundle_id": None, "resolved_skill_set": [], "validation": "fail-closed"},
            "mcp_bundle_ref": {"status": "unresolved", "ref": None, "resolved_mcp_tool_set": [], "validation": "fail-closed"},
            "runtime_binding": {
                "status": "unresolved",
                "authority_scope": "contract-derived-read-model",
                "source": {"runner": "unresolved", "provider": "unresolved", "model": "unresolved"},
                "summary": {"runner": None, "provider": None, "model": None},
            },
            "role": contract.get("assigned_agent", {}).get("role"),
        },
    )
    agents_by_id = {item["agent_id"]: item for item in agents_payload["agents"]}
    assert agents_by_id["agent-a"]["lock_count"] == 2
    assert agents_by_id["agent-a"]["locked_paths"] == ["p1", "p2"]
    assert agents_by_id["agent-b"]["lock_count"] == 0
    role_catalog = {item["role"]: item for item in agents_payload["role_catalog"]}
    assert role_catalog["WORKER"]["registered_agent_count"] == 1
    assert role_catalog["WORKER"]["role_binding_read_model"]["execution_authority"] == "task_contract"

    status_payload = main_run_views_helpers.list_agents_status(
        run_id=None,
        runs_root=runs_root,
        load_worktrees_fn=lambda: [{"run_id": "run-a", "path": "/tmp/wt-a"}, "skip"],
        load_locks_fn=lambda: [{"run_id": "run-a", "path": "locked.py"}, {"run_id": "", "path": "ignored.py"}],
        load_contract_fn=lambda rid: (
            {"assigned_agent": {"agent_id": "agent-a", "role": "WORKER"}, "allowed_paths": ["x.py"]}
            if rid == "run-a"
            else {"assigned_agent": ["invalid"]}
        ),
        read_events_fn=lambda _rid: [{"event": "ANY"}],
        derive_stage_fn=lambda _events, manifest: f"stage-{manifest.get('task_id', 'none')}",
    )
    status_by_run = {item["run_id"]: item for item in status_payload["agents"]}
    assert status_by_run["run-a"]["task_id"] == "task-a"
    assert status_by_run["run-a"]["worktree"] == "/tmp/wt-a"
    assert status_by_run["run-a"]["locked_paths"] == ["locked.py"]
    assert status_by_run["run-a"]["current_files"] == ["a.py", "b.py"]
    assert status_by_run["run-b"]["agent_id"] == ""
    assert status_by_run["run-b"]["allowed_paths"] == []

    filtered = main_run_views_helpers.list_agents_status(
        run_id="run-a",
        runs_root=runs_root,
        load_worktrees_fn=lambda: [],
        load_locks_fn=lambda: [],
        load_contract_fn=lambda _rid: {},
        read_events_fn=lambda _rid: [],
        derive_stage_fn=lambda _events, _manifest: "ok",
    )
    assert [item["run_id"] for item in filtered["agents"]] == ["run-a"]

    assert main_run_views_helpers.list_policies(
        load_agent_registry_fn=lambda: {"registry": True},
        load_command_allowlist_fn=lambda: {"allow": ["a"]},
        load_forbidden_actions_fn=lambda: {"deny": ["b"]},
        load_tool_registry_fn=lambda: {"tool": ["c"]},
        load_control_plane_runtime_policy_fn=lambda: {"version": "v1", "title": "command tower"},
    ) == {
        "agent_registry": {"registry": True},
        "command_allowlist": {"allow": ["a"]},
        "forbidden_actions": {"deny": ["b"]},
        "tool_registry": {"tool": ["c"]},
        "control_plane_runtime_policy": {"version": "v1", "title": "command tower"},
    }
    assert main_run_views_helpers.list_locks(load_locks_fn=lambda: [{"lock_id": "1"}]) == [{"lock_id": "1"}]
    released_paths: list[list[str]] = []
    release_payload = main_run_views_helpers.release_locks(
        paths=[" src/a.py ", "src/a.py", "", "src/b.py"],
        release_lock_fn=lambda values: released_paths.append(list(values)),
    )
    assert released_paths == [["src/a.py", "src/b.py"]]
    assert release_payload == {"ok": True, "released_paths": ["src/a.py", "src/b.py"]}
    assert main_run_views_helpers.list_worktrees(load_worktrees_fn=lambda: [{"path": "/tmp"}]) == [{"path": "/tmp"}]


def test_list_diff_gate_skips_transient_missing_run_dir(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    run_good = runs_root / "run-good"
    run_missing = runs_root / "run-missing"
    run_good.mkdir(parents=True, exist_ok=True)
    run_missing.mkdir(parents=True, exist_ok=True)
    _write_json(run_good / "manifest.json", {"status": "SUCCESS"})
    _write_json(run_good / "contract.json", {"allowed_paths": ["apps/orchestrator/src"]})

    original_stat = Path.stat

    def _patched_stat(self: Path, *args, **kwargs):
        if self == run_missing:
            raise FileNotFoundError("transient run dir disappeared")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", _patched_stat)

    def _read_json(path: Path, default: object) -> object:
        if path.parent == run_missing:
            raise FileNotFoundError("transient run dir disappeared during read")
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    payload = main_run_views_helpers.list_diff_gate(
        runs_root=runs_root,
        read_events_fn=lambda run_id: (
            [{"event": "DIFF_GATE_RESULT", "context": {"ok": True}}]
            if run_id == "run-good"
            else [{"event": "DIFF_GATE_RESULT", "context": {"ok": False}}]
        ),
        read_json_fn=_read_json,
    )

    assert payload == [
        {
            "run_id": "run-good",
            "diff_gate": {"ok": True},
            "status": "SUCCESS",
            "failure_reason": None,
            "allowed_paths": ["apps/orchestrator/src"],
        }
    ]


def test_main_state_store_helpers_branch_matrix(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    locks_dir = runtime_root / "locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    (locks_dir / "lock-a.lock").write_text(
        "\n".join(["run_id=run-a", "path=apps/orchestrator/tests/a.py", "ts=2026-03-08T00:00:00Z"]),
        encoding="utf-8",
    )
    (locks_dir / "lock-b.lock").write_text("path=only-path\n", encoding="utf-8")

    locks = main_state_store_helpers.load_locks(
        runtime_root=runtime_root,
        load_contract_fn=lambda rid: {"assigned_agent": {"agent_id": f"agent-{rid}", "role": "WORKER"}},
    )
    lock_by_id = {item["lock_id"]: item for item in locks}
    assert lock_by_id["lock-a"]["agent_id"] == "agent-run-a"
    assert lock_by_id["lock-a"]["role"] == "WORKER"
    assert lock_by_id["lock-b"]["run_id"] == ""

    assert main_state_store_helpers.load_locks(
        runtime_root=tmp_path / "missing-runtime",
        load_contract_fn=lambda _rid: {},
    ) == []

    worktree_root = tmp_path / "worktrees"
    inside = worktree_root / "run-x" / "task-9"
    outside = tmp_path / "external" / "repo"
    entries = main_state_store_helpers.load_worktrees(
        list_worktrees_lines_fn=lambda: [
            "noise-line",
            f"worktree {inside}",
            "HEAD abc123",
            "branch refs/heads/main",
            "locked by workflow",
            f"worktree {outside}",
            "branch refs/heads/feature",
        ],
        worktree_root=worktree_root,
    )
    assert entries[0]["run_id"] == "run-x"
    assert entries[0]["task_id"] == "task-9"
    assert entries[0]["locked"] is True
    assert entries[1]["run_id"] == ""

    load_error = main_state_store_helpers.load_worktrees(
        list_worktrees_lines_fn=lambda: (_ for _ in ()).throw(RuntimeError("git unavailable")),
        worktree_root=worktree_root,
    )
    assert load_error == [{"error": "git unavailable"}]

    runs_root = tmp_path / "runs"
    run_target = runs_root / "run-target"
    run_good = runs_root / "run-good"
    run_bad_ts = runs_root / "run-bad-ts"
    run_missing_manifest = runs_root / "run-no-manifest"
    for item in (run_target, run_good, run_bad_ts, run_missing_manifest):
        item.mkdir(parents=True, exist_ok=True)
    _write_json(run_target / "manifest.json", {"run_id": "run-target", "created_at": "2024-01-01T00:00:00Z"})
    _write_json(run_good / "manifest.json", {"run_id": "run-good", "created_at": "2024-01-03T00:00:00Z"})
    _write_json(run_bad_ts / "manifest.json", {"run_id": "run-bad-ts", "created_at": "bad-ts"})
    now = datetime(2024, 1, 4, tzinfo=timezone.utc).timestamp()
    os.utime(run_bad_ts / "manifest.json", (now, now))

    def _parse_iso(raw: str) -> datetime:
        if raw == "bad-ts":
            raise ValueError("bad timestamp")
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))

    selected = main_state_store_helpers.select_baseline_by_window(
        run_id="run-target",
        window={"created_at": "2024-01-01T00:00:00Z", "finished_at": "2024-12-31T00:00:00Z"},
        runs_root=runs_root,
        parse_iso_ts_fn=_parse_iso,
    )
    assert selected == "run-bad-ts"

    assert (
        main_state_store_helpers.select_baseline_by_window(
            run_id="run-target",
            window={"created_at": "2025-01-01T00:00:00Z"},
            runs_root=runs_root,
            parse_iso_ts_fn=_parse_iso,
        )
        is None
    )

    events_path = run_good / "events.jsonl"
    events_path.write_text(
        "\n".join([json.dumps({"event": "A"}), "", "not-json", json.dumps({"event": "B"})]) + "\n",
        encoding="utf-8",
    )
    parsed_events = main_state_store_helpers.read_events(run_id="run-good", runs_root=runs_root)
    assert parsed_events[0]["event"] == "A"
    assert parsed_events[1]["raw"] == "not-json"
    assert parsed_events[2]["event"] == "B"
    assert main_state_store_helpers.read_events(run_id="missing", runs_root=runs_root) == []

    missing_incremental = main_state_store_helpers.read_events_incremental(
        run_id="missing",
        runs_root=runs_root,
    )
    assert missing_incremental == ([], 0)

    items_no_filter, offset_after = main_state_store_helpers.read_events_incremental(
        run_id="run-good",
        runs_root=runs_root,
        offset=999999,  # force safe_offset reset path
    )
    assert any(item.get("raw") == "not-json" for item in items_no_filter)
    assert offset_after > 0

    filtered_items, _filtered_offset = main_state_store_helpers.read_events_incremental(
        run_id="run-good",
        runs_root=runs_root,
        offset=0,
        since="2024-01-01T00:00:00Z",
        limit=1,
        tail=True,
        filter_events_fn=lambda items, **kwargs: [
            {"count": len(items), "since": kwargs.get("since"), "limit": kwargs.get("limit"), "tail": kwargs.get("tail")}
        ],
    )
    assert filtered_items == [{"count": 3, "since": "2024-01-01T00:00:00Z", "limit": 1, "tail": True}]

    run_workflow_ok = runs_root / "run-workflow-ok"
    run_workflow_invalid = runs_root / "run-workflow-invalid"
    run_workflow_empty = runs_root / "run-workflow-empty"
    run_workflow_no_dict = runs_root / "run-workflow-no-dict"
    run_workflow_skip = runs_root / "run-workflow-skip"
    for item in (
        run_workflow_ok,
        run_workflow_invalid,
        run_workflow_empty,
        run_workflow_no_dict,
        run_workflow_skip,
    ):
        item.mkdir(parents=True, exist_ok=True)

    _write_json(
        run_workflow_ok / "manifest.json",
        {
            "run_id": "run-workflow-ok",
            "task_id": "task-1",
            "status": "RUNNING",
            "created_at": "2024-01-02T00:00:00Z",
            "role_binding_summary": build_role_binding_summary(
                {
                    "runtime_options": {"runner": "agents", "provider": "cliproxyapi"},
                    "role_contract": {
                        "skills_bundle_ref": "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
                        "mcp_bundle_ref": "policies/agent_registry.json#agents(role=WORKER).capabilities.mcp_tools",
                        "runtime_binding": {"runner": "agents", "provider": "cliproxyapi", "model": None},
                        "resolved_mcp_tool_set": ["codex"],
                    },
                }
            ),
            "workflow": {"workflow_id": "wf-1", "task_queue": "q1", "namespace": "n1", "status": "RUNNING"},
        },
    )
    _write_json(
        run_workflow_skip / "manifest.json",
        {"run_id": "run-workflow-skip", "workflow": {"workflow_id": ""}},
    )
    _write_json(
        run_workflow_empty / "manifest.json",
        {"run_id": "run-workflow-empty", "workflow": None},
    )
    _write_json(
        run_workflow_no_dict / "manifest.json",
        {"run_id": "run-workflow-no-dict", "workflow": "not-a-dict"},
    )
    (run_workflow_invalid / "manifest.json").write_text("{invalid", encoding="utf-8")
    _write_json(
        runs_root / "run-workflow-2" / "manifest.json",
        {
            "run_id": "run-workflow-2",
            "task_id": "task-2",
            "status": "SUCCESS",
            "start_ts": "2024-01-03T00:00:00Z",
            "workflow": {"workflow_id": "wf-1", "task_queue": "q1", "namespace": "n1", "status": "DONE"},
        },
    )

    workflows = main_state_store_helpers.collect_workflows(runs_root=runs_root)
    assert set(workflows.keys()) == {"wf-1"}
    assert workflows["wf-1"]["status"] == "DONE"
    assert len(workflows["wf-1"]["runs"]) == 2
    assert workflows["wf-1"]["workflow_case_read_model"]["workflow_id"] == "wf-1"
    assert workflows["wf-1"]["workflow_case_read_model"]["source_run_id"] == "run-workflow-ok"
    assert (
        workflows["wf-1"]["workflow_case_read_model"]["role_binding_summary"]["skills_bundle_ref"]["bundle_id"]
        == "worker_delivery_core_v1"
    )

    _write_json(
        runs_root / "run-workflow-3" / "manifest.json",
        {
            "run_id": "run-workflow-zz",
            "task_id": "task-3",
            "status": "SUCCESS",
            "created_at": "2024-01-02T00:00:00Z",
            "role_binding_summary": build_role_binding_summary(
                {
                    "runtime_options": {"runner": "agents", "provider": "cliproxyapi"},
                    "role_contract": {
                        "skills_bundle_ref": "policies/skills_bundle_registry.json#bundles.reviewer_gate_v1",
                        "mcp_bundle_ref": "policies/agent_registry.json#agents(role=REVIEWER).capabilities.mcp_tools",
                        "runtime_binding": {"runner": "agents", "provider": "cliproxyapi", "model": None},
                        "resolved_mcp_tool_set": ["codex"],
                    },
                }
            ),
            "workflow": {"workflow_id": "wf-1", "task_queue": "q1", "namespace": "n1", "status": "DONE"},
        },
    )

    workflows = main_state_store_helpers.collect_workflows(runs_root=runs_root)
    assert workflows["wf-1"]["workflow_case_read_model"]["source_run_id"] == "run-workflow-zz"
