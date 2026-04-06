import hashlib
import json
import subprocess
from pathlib import Path

from cortexpilot_orch.replay import replayer


def _build_valid_hashchain(events: list[str]) -> list[str]:
    chain_lines: list[str] = []
    prev_hash = ""
    for idx, event_line in enumerate(events, start=1):
        event_sha = replayer._sha256_text(event_line)
        chain_hash = hashlib.sha256(f"{idx}:{prev_hash}:{event_sha}".encode("utf-8")).hexdigest()
        chain_lines.append(
            json.dumps(
                {
                    "index": idx,
                    "event_sha256": event_sha,
                    "prev_hash": prev_hash,
                    "hash": chain_hash,
                },
                ensure_ascii=False,
            )
        )
        prev_hash = chain_hash
    return chain_lines


def test_verify_contract_signature_matrix(tmp_path: Path, monkeypatch) -> None:
    contract_path = tmp_path / "contract.json"
    contract_path.write_text("{}", encoding="utf-8")
    sig_path = tmp_path / "contract.sig"

    monkeypatch.delenv("CORTEXPILOT_CONTRACT_HMAC_KEY", raising=False)
    ok, reason = replayer._verify_contract_signature(contract_path, sig_path)
    assert ok is False
    assert reason == "hmac key missing"

    monkeypatch.setenv("CORTEXPILOT_CONTRACT_HMAC_KEY", "secret")
    ok, reason = replayer._verify_contract_signature(contract_path, sig_path)
    assert ok is False
    assert reason.startswith("signature read failed:")

    sig_path.write_text("deadbeef", encoding="utf-8")
    bad_contract_path = tmp_path / "contract_dir"
    bad_contract_path.mkdir(parents=True, exist_ok=True)
    ok, reason = replayer._verify_contract_signature(bad_contract_path, sig_path)
    assert ok is False
    assert reason.startswith("signature compute failed:")

    ok, reason = replayer._verify_contract_signature(contract_path, sig_path)
    assert ok is False
    assert reason == "signature mismatch"

    sig_path.write_text(replayer._hmac_sha256("secret", contract_path.read_bytes()), encoding="utf-8")
    ok, reason = replayer._verify_contract_signature(contract_path, sig_path)
    assert ok is True
    assert reason == ""


def test_verify_hashchain_error_matrix_and_success(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    event_lines = [
        json.dumps({"event": "TEST_RESULT", "ts": "2024-01-01T00:00:00Z"}, ensure_ascii=False),
        json.dumps({"event": "REVIEW_RESULT", "ts": "2024-01-01T00:00:01Z"}, ensure_ascii=False),
    ]
    events_path.write_text("\n".join(event_lines) + "\n", encoding="utf-8")
    chain_path = tmp_path / "events.hashchain.jsonl"

    ok, reason = replayer._verify_hashchain(events_path, chain_path)
    assert ok is False and reason == "hashchain missing"

    chain_path.write_text("{}\n", encoding="utf-8")
    ok, reason = replayer._verify_hashchain(tmp_path / "missing-events.jsonl", chain_path)
    assert ok is False and reason.startswith("events read failed:")

    bad_chain_path = tmp_path / "chain-dir"
    bad_chain_path.mkdir(parents=True, exist_ok=True)
    ok, reason = replayer._verify_hashchain(events_path, bad_chain_path)
    assert ok is False and reason.startswith("hashchain read failed:")

    chain_path.write_text("\n", encoding="utf-8")
    ok, reason = replayer._verify_hashchain(events_path, chain_path)
    assert ok is False and reason == "hashchain missing"

    chain_path.write_text("{}\n", encoding="utf-8")
    ok, reason = replayer._verify_hashchain(events_path, chain_path)
    assert ok is False and reason == "hashchain length mismatch"

    invalid_chain = _build_valid_hashchain(event_lines)
    invalid_chain[0] = "not-json"
    chain_path.write_text("\n".join(invalid_chain) + "\n", encoding="utf-8")
    ok, reason = replayer._verify_hashchain(events_path, chain_path)
    assert ok is False and reason == "hashchain line 1 invalid json"

    not_object_chain = _build_valid_hashchain(event_lines)
    not_object_chain[0] = "[]"
    chain_path.write_text("\n".join(not_object_chain) + "\n", encoding="utf-8")
    ok, reason = replayer._verify_hashchain(events_path, chain_path)
    assert ok is False and reason == "hashchain line 1 not object"

    index_mismatch_chain = _build_valid_hashchain(event_lines)
    payload = json.loads(index_mismatch_chain[0])
    payload["index"] = 3
    index_mismatch_chain[0] = json.dumps(payload, ensure_ascii=False)
    chain_path.write_text("\n".join(index_mismatch_chain) + "\n", encoding="utf-8")
    ok, reason = replayer._verify_hashchain(events_path, chain_path)
    assert ok is False and reason == "hashchain index mismatch at 1"

    event_sha_mismatch_chain = _build_valid_hashchain(event_lines)
    payload = json.loads(event_sha_mismatch_chain[0])
    payload["event_sha256"] = "x" * 64
    event_sha_mismatch_chain[0] = json.dumps(payload, ensure_ascii=False)
    chain_path.write_text("\n".join(event_sha_mismatch_chain) + "\n", encoding="utf-8")
    ok, reason = replayer._verify_hashchain(events_path, chain_path)
    assert ok is False and reason == "event sha mismatch at 1"

    prev_hash_mismatch_chain = _build_valid_hashchain(event_lines)
    payload = json.loads(prev_hash_mismatch_chain[1])
    payload["prev_hash"] = "broken-prev"
    prev_hash_mismatch_chain[1] = json.dumps(payload, ensure_ascii=False)
    chain_path.write_text("\n".join(prev_hash_mismatch_chain) + "\n", encoding="utf-8")
    ok, reason = replayer._verify_hashchain(events_path, chain_path)
    assert ok is False and reason == "prev_hash mismatch at 2"

    hash_mismatch_chain = _build_valid_hashchain(event_lines)
    payload = json.loads(hash_mismatch_chain[1])
    payload["hash"] = "broken-hash"
    hash_mismatch_chain[1] = json.dumps(payload, ensure_ascii=False)
    chain_path.write_text("\n".join(hash_mismatch_chain) + "\n", encoding="utf-8")
    ok, reason = replayer._verify_hashchain(events_path, chain_path)
    assert ok is False and reason == "hash mismatch at 2"

    valid_chain = _build_valid_hashchain(event_lines)
    chain_path.write_text("\n".join(valid_chain) + "\n", encoding="utf-8")
    ok, reason = replayer._verify_hashchain(events_path, chain_path)
    assert ok is True and reason == ""


def test_replayer_small_helpers_matrix(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "git").mkdir(parents=True, exist_ok=True)

    assert replayer._load_llm_params(run_dir) == {}

    (run_dir / "meta.json").write_text("not-json", encoding="utf-8")
    assert replayer._load_llm_params(run_dir) == {}

    (run_dir / "meta.json").write_text(json.dumps({"llm_params": [1, 2]}), encoding="utf-8")
    assert replayer._load_llm_params(run_dir) == {}

    (run_dir / "meta.json").write_text(json.dumps({"llm_params": {"model": "gpt-test"}}), encoding="utf-8")
    assert replayer._load_llm_params(run_dir) == {"model": "gpt-test"}

    assert replayer._load_llm_snapshot(run_dir) == {}
    (run_dir / "trace").mkdir(parents=True, exist_ok=True)
    (run_dir / "trace" / "llm_snapshot.json").write_text("[]", encoding="utf-8")
    assert replayer._load_llm_snapshot(run_dir) == {}

    (run_dir / "trace" / "llm_snapshot.json").write_text(
        json.dumps({"provider": "equilibrium"}), encoding="utf-8"
    )
    assert replayer._load_llm_snapshot(run_dir) == {"provider": "equilibrium"}

    (run_dir / "git" / "diff_name_only.txt").write_text("docs/README.md\n", encoding="utf-8")
    assert replayer._load_changed_files(run_dir) == ["docs/README.md"]

    commands = replayer._normalize_acceptance_cmds(
        {
            "acceptance_tests": [
                "echo ok",
                "unterminated 'quote",
                {"cmd": "pytest -q"},
                {"command": "python -m pytest"},
                {"command": 123},
            ]
        }
    )
    assert ["echo", "ok"] in commands
    assert ["pytest", "-q"] in commands
    assert ["python", "-m", "pytest"] in commands

    extracted = replayer._extract_report_cmds(
        {
            "commands": [
                {"cmd_argv": ["pytest", "-q"]},
                {"cmd_argv": []},
                {"cmd_argv": ["ok", 1]},
                "bad",
            ]
        }
    )
    assert extracted == [["pytest", "-q"]]


def _init_git_repo(repo: Path) -> str:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def test_replay_marks_llm_and_snapshot_drift(tmp_path: Path) -> None:
    store = replayer.RunStore(runs_root=tmp_path)
    baseline_id = store.create_run("baseline-llm")
    current_id = store.create_run("current-llm")

    baseline_dir = tmp_path / baseline_id
    current_dir = tmp_path / current_id

    event = json.dumps({"event": "TEST_RESULT", "ts": "2024-01-01T00:00:00Z"}, ensure_ascii=False) + "\n"
    for run_dir, run_id in [(baseline_dir, baseline_id), (current_dir, current_id)]:
        (run_dir / "events.jsonl").write_text(event, encoding="utf-8")
        (run_dir / "manifest.json").write_text(json.dumps({"run_id": run_id, "task_id": "task"}), encoding="utf-8")
        (run_dir / "reports").mkdir(parents=True, exist_ok=True)
        (run_dir / "reports" / "test_report.json").write_text(
            json.dumps({"task_id": "task", "run_id": run_id, "commands": []}), encoding="utf-8"
        )
        (run_dir / "trace").mkdir(parents=True, exist_ok=True)

    (baseline_dir / "meta.json").write_text(json.dumps({"llm_params": {"model": "a", "temperature": 0}}), encoding="utf-8")
    (current_dir / "meta.json").write_text(json.dumps({"llm_params": {"model": "b", "top_p": 1}}), encoding="utf-8")

    (baseline_dir / "trace" / "llm_snapshot.json").write_text(json.dumps({"seed": "s1", "provider": "eq"}), encoding="utf-8")
    (current_dir / "trace" / "llm_snapshot.json").write_text(json.dumps({"seed": "s2", "new": True}), encoding="utf-8")

    runner = replayer.ReplayRunner(store)
    report = runner.replay(current_id, baseline_run_id=baseline_id)

    assert report["status"] == "fail"
    assert report["llm_params"]["ok"] is False
    assert report["llm_snapshot"]["ok"] is False
    assert report["llm_params"]["mismatched"]
    assert report["llm_snapshot"]["mismatched"]


def test_verify_strict_uses_manifest_refs_when_task_result_invalid(tmp_path: Path) -> None:
    store = replayer.RunStore(runs_root=tmp_path)
    run_id = store.create_run("verify-strict-manifest")
    run_dir = tmp_path / run_id

    contract = {
        "task_id": "task-001",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "spec", "artifacts": []},
        "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["README.md"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "mcp_tool_set": ["01-filesystem"],
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": ""},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }
    (run_dir / "contract.json").write_text(json.dumps(contract), encoding="utf-8")
    (run_dir / "events.jsonl").write_text(json.dumps({"event": "TEST_RESULT", "ts": "2024-01-01T00:00:00Z"}) + "\n", encoding="utf-8")
    (run_dir / "patch.diff").write_text("diff --git a/README.md b/README.md\n", encoding="utf-8")
    (run_dir / "diff_name_only.txt").write_text("README.md\n", encoding="utf-8")

    reports = run_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "review_report.json").write_text(
        json.dumps({
            "run_id": run_id,
            "task_id": "task-001",
            "reviewer": {"role": "REVIEWER", "agent_id": "r1"},
            "reviewed_at": "2024-01-01T00:00:00Z",
            "verdict": "PASS",
            "summary": "ok",
            "scope_check": {"passed": True, "violations": []},
            "evidence": [],
            "produced_diff": False,
        }),
        encoding="utf-8",
    )
    (reports / "test_report.json").write_text(
        json.dumps({
            "run_id": run_id,
            "task_id": "task-001",
            "runner": {"role": "TEST_RUNNER", "agent_id": "t1"},
            "started_at": "2024-01-01T00:00:00Z",
            "finished_at": "2024-01-01T00:00:01Z",
            "status": "PASS",
            "commands": [{"cmd_argv": ["echo", "ok"]}],
            "artifacts": [],
        }),
        encoding="utf-8",
    )
    (reports / "task_result.json").write_text("{bad-json", encoding="utf-8")

    manifest = {
        "run_id": run_id,
        "task_id": "task-001",
        "repo": {"baseline_ref": "HEAD", "final_ref": "HEAD"},
        "evidence_hashes": {
            "contract.json": replayer._sha256_file(run_dir / "contract.json"),
            "patch.diff": replayer._sha256_file(run_dir / "patch.diff"),
            "diff_name_only.txt": replayer._sha256_file(run_dir / "diff_name_only.txt"),
            "reports/review_report.json": replayer._sha256_file(reports / "review_report.json"),
            "reports/test_report.json": replayer._sha256_file(reports / "test_report.json"),
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    runner = replayer.ReplayRunner(store)
    report = runner.verify(run_id, strict=True)

    codes = {item["code"] for item in report["errors"]}
    assert "task_result_invalid" in codes
    assert "baseline_missing" not in codes
    assert "head_missing" not in codes


def test_reexecute_reexec_exception_and_hard_diffs(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    baseline = _init_git_repo(repo)
    (repo / "README.md").write_text("changed\n", encoding="utf-8")

    store = replayer.RunStore(runs_root=tmp_path)
    run_id = store.create_run("reexec-extra")
    run_dir = tmp_path / run_id

    contract = {
        "task_id": "task-reexec",
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": baseline},
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
        "forbidden_actions": [],
        "tool_permissions": {"network": "deny"},
    }
    (run_dir / "contract.json").write_text(json.dumps(contract), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({"repo": {"baseline_ref": baseline, "final_ref": "HEAD"}}),
        encoding="utf-8",
    )
    (run_dir / "patch.diff").write_text("diff --git a/README.md b/README.md\nold\n", encoding="utf-8")
    (run_dir / "diff_name_only.txt").write_text("README.md\n", encoding="utf-8")

    reports = run_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "test_report.json").write_text(
        json.dumps({"status": "PASS", "commands": [{"cmd_argv": ["echo", "ok"]}]}),
        encoding="utf-8",
    )
    (reports / "task_result.json").write_text("{bad-json", encoding="utf-8")

    monkeypatch.setattr(replayer.worktree_manager, "create_worktree", lambda *_args, **_kwargs: repo)
    monkeypatch.setattr(replayer.worktree_manager, "remove_worktree", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(replayer, "run_acceptance_tests", lambda *_args, **_kwargs: {"ok": False, "reports": []})

    runner = replayer.ReplayRunner(store)

    # First pass: force exception path inside reexec.
    monkeypatch.setattr(replayer, "_collect_diff_text", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("forced reexec fail")))
    report_fail = runner.reexecute(run_id, strict=True)
    assert report_fail["status"] == "fail"
    assert any("task_result invalid" in err for err in report_fail["errors"])
    assert any("reexec failed: forced reexec fail" in err for err in report_fail["errors"])

    # Second pass: restore diff collector and validate hard-diff branches.
    monkeypatch.setattr(replayer, "_collect_diff_text", lambda *_args, **_kwargs: "diff --git a/README.md b/README.md\nnew\n")
    report_diff = runner.reexecute(run_id, strict=True)
    assert report_diff["status"] == "fail"
    keys = {item["key"] for item in report_diff["hard_diffs"]}
    assert "patch.diff" in keys
    assert "tests" in keys


def test_reexecute_strict_enforces_run_id_and_baseline_binding(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo-bindings"
    baseline = _init_git_repo(repo)

    store = replayer.RunStore(runs_root=tmp_path)
    run_id = store.create_run("reexec-bindings")
    run_dir = tmp_path / run_id

    contract = {
        "task_id": "task-bindings",
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": baseline},
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
        "forbidden_actions": [],
        "tool_permissions": {"network": "deny"},
    }
    (run_dir / "contract.json").write_text(json.dumps(contract), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "run-not-target",
                "repo": {"baseline_ref": "HEAD~1", "final_ref": "HEAD~2"},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "patch.diff").write_text("", encoding="utf-8")
    (run_dir / "diff_name_only.txt").write_text("", encoding="utf-8")

    reports = run_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "test_report.json").write_text(
        json.dumps({"status": "PASS", "run_id": "run-not-target", "commands": [{"cmd_argv": ["echo", "ok"]}]}),
        encoding="utf-8",
    )
    (reports / "task_result.json").write_text(
        json.dumps(
            {
                "run_id": "run-not-target",
                "git": {"baseline_ref": "HEAD~3", "head_ref": "HEAD~4"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(replayer.worktree_manager, "create_worktree", lambda *_args, **_kwargs: repo)
    monkeypatch.setattr(replayer.worktree_manager, "remove_worktree", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(replayer, "run_acceptance_tests", lambda *_args, **_kwargs: {"ok": True, "reports": []})

    runner = replayer.ReplayRunner(store)
    report = runner.reexecute(run_id, strict=True)
    assert report["status"] == "fail"
    assert "manifest run_id mismatch against reexec target" in report["errors"]
    assert "run_id mismatch against reexec target" in report["errors"]
    assert "baseline_ref mismatch across reexec artifacts" in report["errors"]
    assert "head_ref mismatch across reexec artifacts" in report["errors"]


def test_replayer_lastmile_helper_paths(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_dir / "codex" / "task-a").mkdir(parents=True, exist_ok=True)
    (run_dir / "trace").mkdir(parents=True, exist_ok=True)

    (run_dir / "artifacts" / "evidence.txt").write_text("x", encoding="utf-8")
    (run_dir / "codex" / "task-a" / "mcp_stdout.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "trace" / "llm_snapshot.json").write_text("not-json", encoding="utf-8")

    hashes = replayer._collect_evidence_hashes(run_dir)
    assert "artifacts/evidence.txt" in hashes
    assert "codex/task-a/mcp_stdout.jsonl" in hashes

    assert replayer._normalize_acceptance_cmds({"acceptance_tests": {"bad": True}}) == []
    assert replayer._extract_report_cmds({"commands": {"bad": True}}) == []
    assert replayer._load_json_dict(run_dir / "missing.json") == {}

    events_path = run_dir / "events.jsonl"
    events_path.write_text("\n" + json.dumps({"event": "X", "ts": "2024-01-01T00:00:00Z"}) + "\n", encoding="utf-8")
    events = replayer._load_events(events_path)
    assert len(events) == 1
    assert events[0]["event"] == "X"

    assert replayer._load_llm_snapshot(run_dir) == {}
