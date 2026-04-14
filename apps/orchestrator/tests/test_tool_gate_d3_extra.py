import json
from pathlib import Path

from openvibecoding_orch.gates import tool_gate as tg


_DEFAULT_PACK = {"allow": [], "deny_substrings": [], "forbidden_actions": []}


def _write_allowlist(root: Path, allow: list[dict] | None = None, deny: list[str] | None = None) -> None:
    policies = root / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "v1",
        "allow": allow or [],
        "deny_substrings": deny or [],
    }
    (policies / "command_allowlist.json").write_text(json.dumps(payload), encoding="utf-8")


def test_tool_gate_loader_and_merge_edge_cases(tmp_path: Path) -> None:
    assert tg._allowlist_policy(tmp_path) == ([], [])

    policies = tmp_path / "policies"
    policies.mkdir(parents=True, exist_ok=True)

    (policies / "command_allowlist.json").write_text("{", encoding="utf-8")
    assert tg._allowlist_policy(tmp_path) == ([], [])

    (policies / "forbidden_actions.json").write_text("{", encoding="utf-8")
    assert tg._load_forbidden_actions(tmp_path) == []

    assert tg._load_policy_pack(tmp_path, "   ") == _DEFAULT_PACK
    assert tg._load_policy_pack(tmp_path, "high") == _DEFAULT_PACK

    packs_dir = policies / "packs"
    packs_dir.mkdir(parents=True, exist_ok=True)
    (packs_dir / "high.json").write_text("{", encoding="utf-8")
    assert tg._load_policy_pack(tmp_path, "high") == _DEFAULT_PACK

    (policies / "forbidden_actions.json").write_text(
        json.dumps({"forbidden_actions": [" rm -rf ", "", "RM -RF"]}),
        encoding="utf-8",
    )
    merged = tg._merge_forbidden_actions(["", "rm -rf"], tmp_path, extra_actions=["RM -RF", " "])
    assert merged == ["rm -rf"]


def test_tool_gate_internal_matchers_cover_edge_paths(tmp_path: Path) -> None:
    assert tg._contains_shell_operators("echo a && echo b") is True
    assert tg._token_matches("scripts/job.py", "scripts/*") is True
    assert tg._token_matches("scripts/job.py", "script*") is True

    assert tg._extract_script_target(["python"]) == (None, "script path missing", False)
    assert tg._extract_script_target(["python", "--"]) == (None, "script path missing", False)
    assert tg._extract_script_target(["python", "-u", "-B"]) == (None, "script path missing", False)

    allowlist = [
        {
            "exec": "echo",
            "argv_prefixes": [
                "invalid-prefix",
                ["echo", "ok", "extra"],
                ["echo", 123],
                ["echo", "ok"],
            ],
        }
    ]
    assert tg._match_allowlist(["echo", "ok"], "echo", allowlist) is True

    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    tool = scripts / "tool.sh"
    tool.write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
    binary, error = tg._resolve_binary("scripts/tool.sh", tmp_path)
    assert error is None
    assert binary == "tool.sh"


def test_tool_gate_validation_denies_and_repo_root_edges(monkeypatch, tmp_path: Path) -> None:
    missing_allowlist = tg.validate_command("echo ok", [], repo_root=tmp_path)
    assert missing_allowlist["ok"] is False
    assert missing_allowlist["reason"] == "command allowlist unavailable"

    _write_allowlist(
        tmp_path,
        allow=[
            {"exec": "echo", "argv_prefixes": [["echo"]]},
            {"exec": "python", "argv_prefixes": [["python"]]},
            {"exec": "tool.sh", "argv_prefixes": [["tool.sh"]]},
        ],
        deny=["danger-token"],
    )

    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "tool.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    deny_hit = tg.validate_command("echo danger-token", [], repo_root=tmp_path)
    assert deny_hit["ok"] is False
    assert deny_hit["reason"] == "command contains forbidden action"

    policy_deny_no_network = tg.validate_command("echo ok", [], network_policy="deny", repo_root=tmp_path)
    assert policy_deny_no_network["ok"] is True

    pack_dir = tmp_path / "policies" / "packs"
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "medium.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "allow": [{"exec": "echo", "argv_prefixes": [["echo"]]}],
                "deny_substrings": [],
                "forbidden_actions": [],
            }
        ),
        encoding="utf-8",
    )
    pack_result = tg.validate_command("echo ok", [], policy_pack="medium", repo_root=tmp_path)
    assert pack_result["ok"] is True

    path_binary = tg.validate_command("scripts/tool.sh", [], repo_root=tmp_path)
    assert path_binary["ok"] is True

    missing_script = tg.validate_command("python --", [], repo_root=tmp_path)
    assert missing_script["ok"] is False
    assert missing_script["reason"] == "script path missing"

    monkeypatch.setattr(tg, "_repo_root", lambda: tmp_path)
    repo_required = tg.validate_command("python scripts/task.py", [], repo_root=None)
    assert repo_required["ok"] is False
    assert repo_required["reason"] == "script path requires repo_root"

    run_gate = tg.run_tool_gate("echo ok", [], repo_root=tmp_path)
    assert run_gate["ok"] is True


def test_tool_gate_pack_deny_non_list_branch(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "echo", "argv_prefixes": [["echo"]]}], deny=[])

    monkeypatch.setattr(
        tg,
        "_load_policy_pack",
        lambda *_args, **_kwargs: {
            "allow": [{"exec": "echo", "argv_prefixes": [["echo"]]}],
            "deny_substrings": "not-a-list",
            "forbidden_actions": [],
        },
    )

    result = tg.validate_command("echo ok", [], policy_pack="medium", repo_root=tmp_path)
    assert result["ok"] is True
