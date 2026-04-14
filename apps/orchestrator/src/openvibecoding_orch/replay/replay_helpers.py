from __future__ import annotations

import hashlib
import hmac
import json
import os
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openvibecoding_orch.gates.path_match import is_allowed_path


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_text(path.read_text(encoding="utf-8"))


def _hash_events(path: Path) -> str:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            lines.append(raw)
            continue
        if payload.get("event") in {
            "REPLAY_START",
            "REPLAY_DONE",
            "REPLAY_FAILED",
            "REPLAY_AUDIT",
            "REPLAY_VERIFY",
            "REPLAY_VERIFY_FAILED",
        }:
            continue
        lines.append(json.dumps(payload, ensure_ascii=False))
    return _sha256_text("\n".join(lines))


def _hmac_sha256(key: str, payload: bytes) -> str:
    return hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _verify_contract_signature(contract_path: Path, sig_path: Path) -> tuple[bool, str]:
    key = os.getenv("OPENVIBECODING_CONTRACT_HMAC_KEY", "").strip()
    if not key:
        return False, "hmac key missing"
    try:
        signature = sig_path.read_text(encoding="utf-8").strip()
    except Exception as exc:  # noqa: BLE001
        return False, f"signature read failed: {exc}"
    try:
        expected = _hmac_sha256(key, contract_path.read_bytes())
    except Exception as exc:  # noqa: BLE001
        return False, f"signature compute failed: {exc}"
    if signature != expected:
        return False, "signature mismatch"
    return True, ""


def _verify_hashchain(events_path: Path, chain_path: Path) -> tuple[bool, str]:
    if not chain_path.exists():
        return False, "hashchain missing"
    try:
        event_lines = [line for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception as exc:  # noqa: BLE001
        return False, f"events read failed: {exc}"
    try:
        chain_lines = [line for line in chain_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception as exc:  # noqa: BLE001
        return False, f"hashchain read failed: {exc}"
    if not chain_lines:
        return False, "hashchain missing"
    if len(chain_lines) != len(event_lines):
        return False, "hashchain length mismatch"
    prev_hash = ""
    for idx, (event_line, chain_line) in enumerate(zip(event_lines, chain_lines), start=1):
        try:
            payload = json.loads(chain_line)
        except json.JSONDecodeError:
            return False, f"hashchain line {idx} invalid json"
        if not isinstance(payload, dict):
            return False, f"hashchain line {idx} not object"
        if int(payload.get("index", -1)) != idx:
            return False, f"hashchain index mismatch at {idx}"
        event_sha = _sha256_text(event_line)
        if payload.get("event_sha256") != event_sha:
            return False, f"event sha mismatch at {idx}"
        if payload.get("prev_hash") != prev_hash:
            return False, f"prev_hash mismatch at {idx}"
        chain_material = f"{idx}:{prev_hash}:{event_sha}".encode("utf-8")
        expected_hash = hashlib.sha256(chain_material).hexdigest()
        if payload.get("hash") != expected_hash:
            return False, f"hash mismatch at {idx}"
        prev_hash = expected_hash
    return True, ""


def _normalize_acceptance_cmds(contract: dict[str, Any]) -> list[list[str]]:
    cmds: list[list[str]] = []
    tests = contract.get("acceptance_tests", []) if isinstance(contract, dict) else []
    if not isinstance(tests, list):
        return cmds
    for item in tests:
        cmd = ""
        if isinstance(item, str):
            cmd = item
        elif isinstance(item, dict):
            raw = item.get("cmd") or item.get("command")
            if isinstance(raw, str):
                cmd = raw
        if not cmd.strip():
            continue
        try:
            argv = shlex.split(cmd)
        except ValueError:
            continue
        if argv:
            cmds.append(argv)
    return cmds


def _extract_report_cmds(test_report: dict[str, Any]) -> list[list[str]]:
    cmds: list[list[str]] = []
    commands = test_report.get("commands")
    if not isinstance(commands, list):
        return cmds
    for item in commands:
        if not isinstance(item, dict):
            continue
        argv = item.get("cmd_argv")
        if isinstance(argv, list) and all(isinstance(tok, str) for tok in argv) and argv:
            cmds.append([str(tok) for tok in argv])
    return cmds


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _git_allow_nonzero(args: list[str], cwd: Path, allowed: tuple[int, ...] = (0, 1)) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode not in allowed:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def _collect_diff_text(worktree_path: Path, baseline_ref: str) -> str:
    base = _git(["git", "diff", f"{baseline_ref}..HEAD"], cwd=worktree_path)
    status = _git(["git", "status", "--porcelain"], cwd=worktree_path)
    untracked = [line[3:] for line in status.splitlines() if line.startswith("?? ")]
    if not untracked:
        return base
    chunks = [base] if base else []
    for rel in untracked:
        rel = rel.strip()
        if not rel:
            continue
        diff = _git_allow_nonzero(["git", "diff", "--no-index", "/dev/null", rel], cwd=worktree_path)
        if diff.strip():
            chunks.append(diff)
    return "\n".join(chunks).strip()


def _extract_diff_names_from_patch(patch_text: str) -> list[str]:
    names: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                raw = parts[3]
                path = raw[2:] if raw.startswith(("a/", "b/")) else raw
                if path:
                    names.append(path)
    seen: set[str] = set()
    ordered: list[str] = []
    for item in names:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _collect_evidence_hashes(run_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}

    def _add(path: Path) -> None:
        if not path.exists():
            return
        rel = path.relative_to(run_dir).as_posix()
        if rel == "events.jsonl":
            hashes[rel] = _hash_events(path)
        else:
            hashes[rel] = _sha256_file(path)

    for name in [
        "events.jsonl",
        "events.hashchain.jsonl",
        "contract.sig",
        "patch.diff",
        "diff_name_only.txt",
        "contract.json",
        "meta.json",
        "worktree_ref.txt",
    ]:
        _add(run_dir / name)

    for path in sorted((run_dir / "reports").glob("*.json")):
        if path.name == "replay_report.json":
            continue
        _add(path)
    for path in sorted((run_dir / "tasks").glob("*.json")):
        _add(path)
    for path in sorted((run_dir / "results").glob("**/*.json")):
        _add(path)
    for path in sorted((run_dir / "results").glob("**/*.diff")):
        _add(path)
    for path in sorted((run_dir / "reviews").glob("*.json")):
        _add(path)
    for path in sorted((run_dir / "ci").glob("**/*.json")):
        _add(path)
    for path in sorted((run_dir / "artifacts").glob("**/*")):
        if path.is_file():
            _add(path)
    for path in sorted((run_dir / "git").glob("*")):
        _add(path)
    for path in sorted((run_dir / "tests").glob("*")):
        _add(path)
    for path in sorted((run_dir / "trace").glob("*")):
        _add(path)
    for path in sorted((run_dir / "codex").glob("**/*")):
        if path.is_file():
            _add(path)
    return hashes


def _load_baseline_hashes(run_dir: Path) -> dict[str, str]:
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            baseline = manifest.get("evidence_hashes")
            if isinstance(baseline, dict) and baseline:
                return baseline
        except Exception:  # noqa: BLE001
            pass
    return _collect_evidence_hashes(run_dir)


def _load_llm_params(run_dir: Path) -> dict[str, Any]:
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    params = payload.get("llm_params") if isinstance(payload, dict) else {}
    return params if isinstance(params, dict) else {}


def _load_llm_snapshot(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "trace" / "llm_snapshot.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_events(events_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"raw": line})
    return events


def _parse_ts(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _load_acceptance_commands(contract: dict[str, Any]) -> set[tuple[str, ...]]:
    commands: set[tuple[str, ...]] = set()
    tests = contract.get("acceptance_tests", [])
    if not isinstance(tests, list):
        return commands
    for item in tests:
        if isinstance(item, str) and item.strip():
            try:
                commands.add(tuple(shlex.split(item.strip())))
            except ValueError:
                continue
            continue
        if isinstance(item, dict):
            cmd = item.get("cmd") or item.get("command")
            if isinstance(cmd, str) and cmd.strip():
                try:
                    commands.add(tuple(shlex.split(cmd.strip())))
                except ValueError:
                    continue
    return commands


def _is_allowed(path: str, allowed_paths: list[str]) -> bool:
    return is_allowed_path(path, allowed_paths)


def _load_changed_files(run_dir: Path) -> list[str]:
    candidates = [
        run_dir / "diff_name_only.txt",
        run_dir / "git" / "diff_name_only.txt",
    ]
    for path in candidates:
        if path.exists():
            return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return []


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _expected_reports(events: list[dict[str, Any]]) -> set[str]:
    expected: set[str] = set()
    for ev in events:
        event_name = ev.get("event")
        if event_name == "TEST_RESULT":
            expected.add("test_report.json")
        if event_name == "REVIEW_RESULT":
            expected.add("review_report.json")
        if event_name in {"TASK_RESULT_RECORDED", "CODEX_MOCK_EVENT", "CODEX_STDOUT", "CODEX_RAW_EVENT"}:
            expected.add("task_result.json")
    return expected
