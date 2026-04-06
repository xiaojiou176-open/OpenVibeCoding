from pathlib import Path

from cortexpilot_orch.scheduler import runtime_utils


def test_runtime_utils_branch_matrix(monkeypatch, tmp_path: Path) -> None:
    call_log: list[tuple[str, tuple[str, ...]]] = []

    def _fake_git_allow_nonzero(args, cwd, allowed=(0, 1)):
        call_log.append(("allow", tuple(args)))
        if args[:2] == ["git", "diff"] and len(args) == 2:
            return "BASE"
        return "PATCH"

    monkeypatch.setattr(runtime_utils, "git_allow_nonzero", _fake_git_allow_nonzero)
    monkeypatch.setattr(runtime_utils, "git", lambda args, cwd: "?? file.txt\n??    ")
    text = runtime_utils.collect_diff_text(tmp_path)
    assert text.endswith("\n")
    assert "PATCH" in text

    monkeypatch.setattr(runtime_utils, "git", lambda args, cwd: "")
    only_base = runtime_utils.collect_diff_text(tmp_path)
    assert only_base == "BASE\n"

    class StoreRaise:
        def write_contract_signature(self, run_id, contract_path):
            raise RuntimeError("boom")

    sig, err = runtime_utils.write_contract_signature(StoreRaise(), "run", tmp_path / "contract.json")
    assert sig is None and "boom" in str(err)

    class StoreNone:
        def write_contract_signature(self, run_id, contract_path):
            return None

    sig2, err2 = runtime_utils.write_contract_signature(StoreNone(), "run", tmp_path / "contract.json")
    assert sig2 is None and err2 is None

    sig_path = tmp_path / "sig.txt"
    sig_path.write_text("abc", encoding="utf-8")

    class StoreReadFail:
        def write_contract_signature(self, run_id, contract_path):
            return sig_path

    monkeypatch.setattr(Path, "read_text", lambda self, _encoding="utf-8": (_ for _ in ()).throw(RuntimeError("read fail")))
    sig3, err3 = runtime_utils.write_contract_signature(StoreReadFail(), "run", tmp_path / "contract.json")
    assert sig3 is None and "read fail" in str(err3)

    snapshot = runtime_utils.llm_params_snapshot({"tool_permissions": "bad"}, "runner", None)
    assert snapshot["runner"] == "runner"
    assert snapshot["mcp_tools"] == []
