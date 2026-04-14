from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from .e2e_helpers import (
    _git,
    build_env,
    create_tiny_repo,
    load_json,
    run_contract,
    run_replay,
    start_api,
    start_ui,
    wait_for_http,
)

pytestmark = pytest.mark.serial


def _output_schema_artifacts(role: str = "worker") -> list[dict]:
    schema_root = Path(__file__).resolve().parents[4] / "schemas"
    schema_name = "agent_task_result.v1.json"
    if role.lower() in {"reviewer"}:
        schema_name = "review_report.v1.json"
    if role.lower() in {"test", "test_runner"}:
        schema_name = "test_report.v1.json"
    schema_path = schema_root / schema_name
    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    return [
        {
            "name": f"output_schema.{role.lower()}",
            "uri": f"schemas/{schema_name}",
            "sha256": sha,
        }
    ]


# --------------------
# E2E-2: Out-of-bounds gate must block
# --------------------


@pytest.mark.e2e
def test_dashboard_e2e_out_of_bounds(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"

    base_env = build_env(repo_root, runtime_root, runs_root, worktree_root)
    api_proc, api_port = start_api(repo_root, base_env, tmp_path / "api.log")
    ui_proc, ui_port = start_ui(repo_root, base_env, api_port, tmp_path / "ui.log")

    try:
        wait_for_http(f"http://127.0.0.1:{api_port}/api/runs", 20, api_proc)
        wait_for_http(f"http://127.0.0.1:{ui_port}/runs", 40, ui_proc)

        repo = create_tiny_repo(tmp_path / "tiny_repo_oob")
        contract = {
            "task_id": "e2e_oob_01",
            "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
            "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
            "inputs": {"spec": "mock change outside allowed paths", "artifacts": _output_schema_artifacts("worker")},
            "required_outputs": [
                {"name": "README.md", "type": "file", "acceptance": "diff must be blocked"}
            ],
            "allowed_paths": ["allowed/"],
            "forbidden_actions": [],
            "acceptance_tests": [{"name": "echo", "cmd": "echo hello", "must_pass": True}],
            "tool_permissions": {
                "filesystem": "workspace-write",
                "shell": "on-request",
                "network": "deny",
                "mcp_tools": ["codex"],
            },
            "mcp_tool_set": ["01-filesystem"],
            "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
            "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
            "evidence_links": [],
            "log_refs": {"run_id": "", "paths": {}},
        }
        run_id = run_contract(repo, base_env, contract, tmp_path)

        runs = load_json(f"http://127.0.0.1:{api_port}/api/runs")
        run = next((item for item in runs if item.get("run_id") == run_id), None)
        assert run is not None
        assert run.get("status") == "FAILURE"

        events = load_json(f"http://127.0.0.1:{api_port}/api/runs/{run_id}/events")
        assert any(ev.get("event") == "DIFF_GATE_FAIL" for ev in events)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(
                f"http://127.0.0.1:{ui_port}/runs/{run_id}",
                wait_until="domcontentloaded",
            )
            page.get_by_test_id("run-id").wait_for(timeout=10_000)
            assert run_id in page.get_by_test_id("run-id").inner_text()
            page.get_by_test_id("run-status").wait_for(timeout=10_000)
            assert "FAILURE" in page.get_by_test_id("run-status").inner_text()
            page.get_by_test_id("event-name-DIFF_GATE_FAIL").first.wait_for(timeout=10_000)
            browser.close()
    finally:
        ui_proc.stop()
        api_proc.stop()


# --------------------
# E2E-3: Fix loop should recover
# --------------------


@pytest.mark.e2e
def test_dashboard_e2e_fix_loop(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"

    base_env = build_env(repo_root, runtime_root, runs_root, worktree_root)
    api_proc, api_port = start_api(repo_root, base_env, tmp_path / "api.log")
    ui_proc, ui_port = start_ui(repo_root, base_env, api_port, tmp_path / "ui.log")

    try:
        wait_for_http(f"http://127.0.0.1:{api_port}/api/runs", 20, api_proc)
        wait_for_http(f"http://127.0.0.1:{ui_port}/runs", 40, ui_proc)

        repo = create_tiny_repo(tmp_path / "tiny_repo_fix")
        script_dir = repo / "scripts"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / "fix_loop.py"
        script_path.write_text(
            "\n".join(
                [
                    "from pathlib import Path",
                    "import sys",
                    "",
                    "marker = Path('allowed/fix_marker.txt')",
                    "if marker.exists():",
                    "    sys.exit(0)",
                    "marker.parent.mkdir(parents=True, exist_ok=True)",
                    "marker.write_text('marker', encoding='utf-8')",
                    "sys.exit(1)",
                ]
            ),
            encoding="utf-8",
        )
        _git(["git", "add", "scripts/fix_loop.py"], cwd=repo)
        _git(["git", "commit", "-m", "add fix loop helper"], cwd=repo)
        contract = {
            "task_id": "e2e_fix_loop_01",
            "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
            "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
            "inputs": {"spec": "mock change with fix loop", "artifacts": _output_schema_artifacts("worker")},
            "required_outputs": [
                {"name": "README.md", "type": "file", "acceptance": "fix loop passes"}
            ],
            "allowed_paths": ["README.md", "allowed/"],
            "forbidden_actions": [],
            "acceptance_tests": [
                {
                    "name": "fix-loop",
                    "cmd": "python3 scripts/fix_loop.py",
                    "must_pass": True,
                }
            ],
            "tool_permissions": {
                "filesystem": "workspace-write",
                "shell": "on-request",
                "network": "deny",
                "mcp_tools": ["codex"],
            },
            "mcp_tool_set": ["01-filesystem"],
            "timeout_retry": {"timeout_sec": 1, "max_retries": 1, "retry_backoff_sec": 0},
            "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
            "evidence_links": [],
            "log_refs": {"run_id": "", "paths": {}},
        }
        run_id = run_contract(repo, base_env, contract, tmp_path)

        runs = load_json(f"http://127.0.0.1:{api_port}/api/runs")
        run = next((item for item in runs if item.get("run_id") == run_id), None)
        assert run is not None
        assert run.get("status") == "SUCCESS"

        events = load_json(f"http://127.0.0.1:{api_port}/api/runs/{run_id}/events")
        assert any(ev.get("event") == "FIX_LOOP_TRIGGERED" for ev in events)
        assert any(ev.get("event") == "FIX_LOOP_ATTEMPT" for ev in events)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(
                f"http://127.0.0.1:{ui_port}/runs/{run_id}",
                wait_until="domcontentloaded",
            )
            page.get_by_test_id("run-id").wait_for(timeout=10_000)
            assert run_id in page.get_by_test_id("run-id").inner_text()
            page.get_by_test_id("run-status").wait_for(timeout=10_000)
            assert "SUCCESS" in page.get_by_test_id("run-status").inner_text()
            page.get_by_test_id("event-name-FIX_LOOP_TRIGGERED").first.wait_for(timeout=10_000)
            browser.close()
    finally:
        ui_proc.stop()
        api_proc.stop()


# --------------------
# E2E-4: Replay should rehydrate evidence
# --------------------


@pytest.mark.e2e
def test_dashboard_e2e_replay(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"

    base_env = build_env(repo_root, runtime_root, runs_root, worktree_root)
    api_proc, api_port = start_api(repo_root, base_env, tmp_path / "api.log")
    ui_proc, ui_port = start_ui(repo_root, base_env, api_port, tmp_path / "ui.log")

    try:
        wait_for_http(f"http://127.0.0.1:{api_port}/api/runs", 20, api_proc)
        wait_for_http(f"http://127.0.0.1:{ui_port}/runs", 40, ui_proc)

        repo = create_tiny_repo(tmp_path / "tiny_repo_replay")
        contract = {
            "task_id": "e2e_replay_01",
            "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
            "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
            "inputs": {"spec": "mock change for replay", "artifacts": _output_schema_artifacts("worker")},
            "required_outputs": [
                {"name": "README.md", "type": "file", "acceptance": "replay ok"}
            ],
            "allowed_paths": ["README.md"],
            "forbidden_actions": [],
            "acceptance_tests": [{"name": "echo", "cmd": "echo hello", "must_pass": True}],
            "tool_permissions": {
                "filesystem": "workspace-write",
                "shell": "on-request",
                "network": "deny",
                "mcp_tools": ["codex"],
            },
            "mcp_tool_set": ["01-filesystem"],
            "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
            "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
            "evidence_links": [],
            "log_refs": {"run_id": "", "paths": {}},
        }
        run_id = run_contract(repo, base_env, contract, tmp_path)

        runs = load_json(f"http://127.0.0.1:{api_port}/api/runs")
        run = next((item for item in runs if item.get("run_id") == run_id), None)
        assert run is not None
        assert run.get("status") == "SUCCESS"

        run_replay(repo, base_env, run_id)

        events = load_json(f"http://127.0.0.1:{api_port}/api/runs/{run_id}/events")
        assert any(ev.get("event") == "REPLAY_START" for ev in events)
        assert any(ev.get("event") == "REPLAY_DONE" for ev in events)
        assert any(
            ev.get("event") == "REPLAY_AUDIT" and ev.get("context", {}).get("baseline_run_id") == run_id
            for ev in events
        )

        reports = load_json(f"http://127.0.0.1:{api_port}/api/runs/{run_id}/reports")
        replay_report = next((item for item in reports if item.get("name") == "replay_report.json"), None)
        assert replay_report is not None
        assert replay_report.get("data", {}).get("status") == "ok"
        assert replay_report.get("data", {}).get("manifest_hash")
        assert replay_report.get("data", {}).get("evidence_hashes", {}).get("ok") is True

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(
                f"http://127.0.0.1:{ui_port}/runs/{run_id}",
                wait_until="domcontentloaded",
            )
            page.get_by_test_id("run-id").wait_for(timeout=10_000)
            assert run_id in page.get_by_test_id("run-id").inner_text()
            page.get_by_test_id("event-name-REPLAY_DONE").first.wait_for(timeout=10_000)
            browser.close()
    finally:
        ui_proc.stop()
        api_proc.stop()


# --------------------
# E2E-5: Browser allowlist must fail closed
# --------------------


@pytest.mark.e2e
def test_dashboard_e2e_browser_allowlist_block(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"

    base_env = build_env(repo_root, runtime_root, runs_root, worktree_root)
    base_env["OPENVIBECODING_BROWSER_ALLOWLIST"] = "https://chatgpt.com/"
    api_proc, api_port = start_api(repo_root, base_env, tmp_path / "api.log")
    ui_proc, ui_port = start_ui(repo_root, base_env, api_port, tmp_path / "ui.log")

    try:
        wait_for_http(f"http://127.0.0.1:{api_port}/api/runs", 20, api_proc)
        wait_for_http(f"http://127.0.0.1:{ui_port}/runs", 40, ui_proc)

        repo = create_tiny_repo(tmp_path / "tiny_repo_browser")
        browser_tasks = {
            "tasks": [
                {"url": "https://example.com/", "script": ""},
            ]
        }
        browser_path = repo / "browser_tasks.json"
        browser_path.write_text(json.dumps(browser_tasks), encoding="utf-8")
        browser_sha = hashlib.sha256(browser_path.read_bytes()).hexdigest()

        contract = {
            "task_id": "e2e_browser_allowlist_01",
            "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
            "assigned_agent": {"role": "SEARCHER", "agent_id": "agent-1", "codex_thread_id": ""},
            "inputs": {
                "spec": "browser tasks must obey allowlist",
                "artifacts": [
                    *_output_schema_artifacts("searcher"),
                    {
                        "name": "browser_tasks.json",
                        "uri": str(browser_path),
                        "sha256": browser_sha,
                    }
                ],
            },
            "required_outputs": [
                {"name": "README.md", "type": "file", "acceptance": "allowlist failure blocks run"}
            ],
            "allowed_paths": ["README.md"],
            "forbidden_actions": [],
            "acceptance_tests": [{"name": "echo", "cmd": "echo hello", "must_pass": True}],
            "tool_permissions": {
                "filesystem": "workspace-write",
                "shell": "on-request",
                "network": "allow",
                "mcp_tools": ["codex"],
            },
            "mcp_tool_set": ["01-filesystem"],
            "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
            "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
            "evidence_links": [],
            "log_refs": {"run_id": "", "paths": {}},
        }
        run_id = run_contract(repo, base_env, contract, tmp_path)

        runs = load_json(f"http://127.0.0.1:{api_port}/api/runs")
        run = next((item for item in runs if item.get("run_id") == run_id), None)
        assert run is not None
        assert run.get("status") == "FAILURE"
        manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
        assert manifest.get("failure_reason") == "browser tasks failed"

        events = load_json(f"http://127.0.0.1:{api_port}/api/runs/{run_id}/events")
        assert any(ev.get("event") == "BROWSER_TASKS_RESULT" for ev in events)

        result_path = runs_root / run_id / "artifacts" / "browser_results.json"
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        latest = payload.get("latest", {})
        summary = latest.get("summary", {})
        failures = summary.get("results", [])
        assert failures
        first = failures[0]
        assert first.get("error") == "url not allowlisted"
        error_ref = first.get("artifacts", {}).get("error")
        assert error_ref and Path(error_ref).exists()

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(
                f"http://127.0.0.1:{ui_port}/runs/{run_id}",
                wait_until="domcontentloaded",
            )
            page.get_by_test_id("run-id").wait_for(timeout=10_000)
            assert run_id in page.get_by_test_id("run-id").inner_text()
            page.get_by_test_id("run-status").wait_for(timeout=10_000)
            assert "FAILURE" in page.get_by_test_id("run-status").inner_text()
            page.get_by_test_id("event-name-BROWSER_TASKS_RESULT").first.wait_for(timeout=10_000)
            browser.close()
    finally:
        ui_proc.stop()
        api_proc.stop()
