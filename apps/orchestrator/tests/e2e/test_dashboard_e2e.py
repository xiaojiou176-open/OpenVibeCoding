from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .e2e_helpers import (
    build_env,
    create_tiny_repo,
    load_json,
    run_contract,
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


@pytest.mark.e2e
def test_dashboard_e2e_happy_path(tmp_path: Path) -> None:
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

        repo = create_tiny_repo(tmp_path / "tiny_repo")
        contract = {
            "task_id": "e2e_happy",
            "owner_agent": {"role": "WORKER", "agent_id": "e2e-worker", "codex_thread_id": ""},
            "assigned_agent": {"role": "WORKER", "agent_id": "e2e-worker", "codex_thread_id": ""},
            "inputs": {"spec": "mock change", "artifacts": _output_schema_artifacts("worker")},
            "required_outputs": [
                {"name": "mock_output.txt", "type": "file", "acceptance": "mock file exists"}
            ],
            "allowed_paths": ["mock_output.txt"],
            "forbidden_actions": [],
            "acceptance_tests": [{"name": "echo", "cmd": "echo hello", "must_pass": True}],
            "tool_permissions": {
                "filesystem": "workspace-write",
                "shell": "on-request",
                "network": "deny",
                "mcp_tools": ["codex"],
            },
            "mcp_tool_set": ["01-filesystem"],
            "timeout_retry": {"timeout_sec": 60, "max_retries": 0, "retry_backoff_sec": 0},
            "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
            "evidence_links": [],
            "log_refs": {
                "run_id": "",
                "paths": {
                    "codex_jsonl": "",
                    "codex_transcript": "",
                    "git_diff": "",
                    "tests_log": "",
                    "trace_id": "",
                },
            },
        }
        run_id = run_contract(repo, base_env, contract, tmp_path)

        runs = load_json(f"http://127.0.0.1:{api_port}/api/runs")
        assert any(item.get("run_id") == run_id for item in runs)
        wait_for_http(f"http://127.0.0.1:{api_port}/api/runs/{run_id}", 20, api_proc)
        wait_for_http(f"http://127.0.0.1:{ui_port}/runs/{run_id}", 60, ui_proc)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            artifacts_dir = tmp_path / "artifacts"
            try:
                page.goto(
                    f"http://127.0.0.1:{ui_port}/runs/{run_id}",
                    wait_until="domcontentloaded",
                )
                page.get_by_test_id("run-detail-title").wait_for(timeout=20_000)
                page.get_by_test_id("run-id").wait_for(timeout=20_000)
                assert run_id in page.get_by_test_id("run-id").inner_text()
                page.get_by_test_id("task-id").wait_for(timeout=20_000)
                assert "e2e_happy" in page.get_by_test_id("task-id").inner_text()
                page.get_by_test_id("allowed-paths-label").wait_for(timeout=20_000)
                page.get_by_text("1 path").wait_for(timeout=20_000)
                page.get_by_text("Expand path details").click()
                page.get_by_test_id("allowed-paths-content").wait_for(timeout=20_000)
                assert "mock_output.txt" in page.get_by_test_id("allowed-paths-content").inner_text()
                page.get_by_test_id("event-timeline-title").wait_for(timeout=20_000)
                page.get_by_test_id("detail-panel-title").wait_for(timeout=20_000)
                page.get_by_test_id("detail-panel-title").scroll_into_view_if_needed()
                page.get_by_test_id("tab-reports").scroll_into_view_if_needed()

                # Wait until the detail-panel state actually flips to Reports
                # instead of assuming the first click lands after hydration.
                page.wait_for_timeout(500)
                for _ in range(10):
                    page.get_by_role("tab", name="Reports").click()
                    try:
                        page.wait_for_function(
                            """() => document.querySelector('[data-testid="run-detail-active-tab-state"]')?.textContent?.includes('Reports')""",
                            timeout=1_000,
                        )
                        break
                    except PlaywrightTimeoutError:
                        page.wait_for_timeout(500)
                else:
                    raise AssertionError("Reports tab never became active during the run-detail e2e flow.")

                page.get_by_test_id("replay-controls-title").wait_for(timeout=10_000)
                page.get_by_test_id("replay-compare-button").wait_for(timeout=10_000)
            except Exception:  # noqa: BLE001
                artifacts_dir.mkdir(parents=True, exist_ok=True)
                try:
                    html_path = artifacts_dir / "dashboard_failure.html"
                    html_path.write_text(page.content(), encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
                try:
                    page.screenshot(path=str(artifacts_dir / "dashboard_failure.png"), full_page=True)
                except Exception:  # noqa: BLE001
                    pass
                raise
            finally:
                browser.close()
    finally:
        ui_proc.stop()
        api_proc.stop()
