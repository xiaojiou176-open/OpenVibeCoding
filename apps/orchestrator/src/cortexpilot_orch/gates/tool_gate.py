from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Iterable


_NON_INTERACTIVE_BLOCKLIST = [
    " --interactive",
    " -i ",
    " -it ",
    " read ",
    " sudo ",
    " su ",
    " passwd",
    " ssh ",
]

_NETWORK_BLOCKLIST = [
    " curl ",
    " wget ",
    " http://",
    " https://",
    " ping ",
    " ssh ",
    " scp ",
    " sftp ",
]

_INLINE_EXEC_FLAGS = {"-c", "-e", "--eval"}
_SHELL_OPERATOR_CHARS = {";", "|", "&", ">", "<"}
_SHELL_OPERATOR_TOKENS = {"&&", "||", ">>"}
_SCRIPT_BINARIES = {"python", "python3", "node", "bash", "sh"}
_FORBIDDEN_POLICY_FILE = "policies/forbidden_actions.json"
_POLICY_PACK_DIR = "policies/packs"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _allowlist_policy(repo_root: Path) -> tuple[list[dict], list[str]]:
    policy_path = repo_root / "policies" / "command_allowlist.json"
    if not policy_path.exists():
        return [], []
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [], []
    allow = payload.get("allow") if isinstance(payload, dict) else []
    deny = payload.get("deny_substrings") if isinstance(payload, dict) else []
    allow_list = [item for item in allow if isinstance(item, dict)]
    deny_list = [str(item).lower() for item in deny if str(item).strip()]
    return allow_list, deny_list


def _load_forbidden_actions(repo_root: Path | None) -> list[str]:
    if repo_root is None:
        return []
    policy_path = repo_root / _FORBIDDEN_POLICY_FILE
    if not policy_path.exists():
        return []
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    actions = payload.get("forbidden_actions") if isinstance(payload, dict) else []
    return [str(item).strip() for item in actions if str(item).strip()]


def _load_policy_pack(repo_root: Path | None, policy_pack: str | None) -> dict:
    if repo_root is None:
        return {"allow": [], "deny_substrings": [], "forbidden_actions": []}
    if not policy_pack:
        return {"allow": [], "deny_substrings": [], "forbidden_actions": []}
    pack_name = str(policy_pack).strip().lower()
    if not pack_name:
        return {"allow": [], "deny_substrings": [], "forbidden_actions": []}
    pack_path = repo_root / _POLICY_PACK_DIR / f"{pack_name}.json"
    if not pack_path.exists():
        return {"allow": [], "deny_substrings": [], "forbidden_actions": []}
    try:
        payload = json.loads(pack_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"allow": [], "deny_substrings": [], "forbidden_actions": []}
    allow = payload.get("allow") if isinstance(payload, dict) else []
    deny = payload.get("deny_substrings") if isinstance(payload, dict) else []
    forbidden = payload.get("forbidden_actions") if isinstance(payload, dict) else []
    allow_list = [item for item in allow if isinstance(item, dict)]
    deny_list = [str(item).lower() for item in deny if str(item).strip()]
    forbidden_list = [str(item).strip() for item in forbidden if str(item).strip()]
    return {"allow": allow_list, "deny_substrings": deny_list, "forbidden_actions": forbidden_list}


def _merge_forbidden_actions(
    forbidden_actions: Iterable[str],
    repo_root: Path | None,
    extra_actions: Iterable[str] | None = None,
) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    extra = list(extra_actions or [])
    for item in _load_forbidden_actions(repo_root) + extra + list(forbidden_actions):
        token = str(item).strip()
        if not token:
            continue
        lowered = token.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        merged.append(token)
    return merged


def _network_approved() -> bool:
    raw = os.getenv("CORTEXPILOT_NETWORK_APPROVED", "").strip().lower()
    return raw in {"1", "true", "yes"}


def _split_command(command: str) -> list[str] | None:
    try:
        return shlex.split(command)
    except ValueError:
        return None


def _contains_shell_operators(command: str) -> bool:
    in_single = False
    in_double = False
    idx = 0
    length = len(command)
    while idx < length:
        ch = command[idx]
        if ch == "'" and not in_double:
            in_single = not in_single
            idx += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            idx += 1
            continue
        if not in_single and not in_double:
            if idx + 1 < length:
                pair = command[idx : idx + 2]
                if pair in _SHELL_OPERATOR_TOKENS:
                    return True
            if ch in _SHELL_OPERATOR_CHARS:
                return True
        idx += 1
    return False


def _is_within(path: Path, root: Path) -> bool:
    resolved_root = root.resolve()
    try:
        path.relative_to(resolved_root)
    except ValueError:
        return False
    return True


def _managed_toolchain_root() -> Path:
    return _repo_root() / ".runtime-cache" / "cache" / "toolchains"


def _is_allowed_external_command_path(candidate: Path) -> bool:
    return _is_within(candidate, _managed_toolchain_root())


def _resolve_binary(token: str, repo_root: Path | None) -> tuple[str | None, str | None]:
    if "/" in token or token.startswith("."):
        if repo_root is None:
            return None, "command path requires repo_root"
        resolved_repo_root = repo_root.resolve()
        candidate = (
            Path(os.path.abspath(os.path.join(str(resolved_repo_root), token)))
            if not Path(token).is_absolute()
            else Path(os.path.abspath(str(Path(token).expanduser())))
        )
        if not _is_within(candidate, resolved_repo_root) and not _is_allowed_external_command_path(candidate):
            return None, "command path outside repo"
        if not candidate.exists():
            return None, "command path not found"
        if candidate.is_dir():
            return None, "command path is directory"
        return candidate.name, None
    return token, None


def _extract_script_target(tokens: list[str]) -> tuple[str | None, str | None, bool]:
    if len(tokens) <= 1:
        return None, "script path missing", False
    binary_name = Path(tokens[0]).name
    if binary_name in {"python", "python3"} and "-m" in tokens:
        return None, None, True
    idx = 1
    while idx < len(tokens):
        token = tokens[idx]
        if token == "--":
            if idx + 1 < len(tokens):
                return tokens[idx + 1], None, False
            return None, "script path missing", False
        if token.startswith("-"):
            idx += 1
            continue
        return token, None, False
    return None, "script path missing", False


def _token_matches(token: str, pattern: str) -> bool:
    if pattern.endswith("/*"):
        return token.startswith(pattern[:-1])
    if pattern.endswith("/"):
        return token.startswith(pattern)
    if pattern.endswith("*"):
        return token.startswith(pattern[:-1])
    return token == pattern


def _match_allowlist(tokens: list[str], binary: str, allowlist: list[dict]) -> bool:
    normalized_tokens = list(tokens)
    if normalized_tokens:
        normalized_tokens[0] = binary
    for rule in allowlist:
        exec_name = rule.get("exec")
        prefixes = rule.get("argv_prefixes")
        if exec_name != binary or not isinstance(prefixes, list):
            continue
        for prefix in prefixes:
            if not isinstance(prefix, list):
                continue
            if len(normalized_tokens) < len(prefix):
                continue
            matched = True
            for idx, token in enumerate(prefix):
                if not isinstance(token, str):
                    matched = False
                    break
                if not _token_matches(normalized_tokens[idx], token):
                    matched = False
                    break
            if matched:
                return True
    return False


def validate_command(
    command: str,
    forbidden_actions: Iterable[str],
    network_policy: str | None = None,
    policy_pack: str | None = None,
    repo_root: Path | None = None,
) -> dict:
    tokens = _split_command(command)
    if not tokens:
        return {
            "ok": False,
            "command": command,
            "violations": ["empty"],
            "reason": "invalid command",
        }

    lowered = f" {command.lower()} "
    pack_payload = _load_policy_pack(repo_root, policy_pack)
    pack_forbidden = pack_payload.get("forbidden_actions") if isinstance(pack_payload, dict) else []
    merged_forbidden = _merge_forbidden_actions(forbidden_actions, repo_root, pack_forbidden)
    blocked = [action for action in merged_forbidden if action and action.lower() in lowered]
    if blocked:
        return {
            "ok": False,
            "command": command,
            "violations": blocked,
            "reason": "command contains forbidden action",
        }

    if _contains_shell_operators(command):
        return {
            "ok": False,
            "command": command,
            "violations": ["shell-operator"],
            "reason": "shell operators are not allowed",
        }

    policy = (network_policy or "deny").strip().lower()
    if policy not in {"deny", "on-request", "allow"}:
        return {
            "ok": False,
            "command": command,
            "violations": [policy],
            "reason": "invalid network policy",
        }
    if policy in {"deny", "on-request"}:
        for token in _NETWORK_BLOCKLIST:
            if token in lowered:
                if policy == "on-request" and _network_approved():
                    break
                return {
                    "ok": False,
                    "command": command,
                    "violations": [token.strip()],
                    "reason": "network access blocked by policy",
                }

    for token in _NON_INTERACTIVE_BLOCKLIST:
        if token in lowered:
            return {
                "ok": False,
                "command": command,
                "violations": [token.strip()],
                "reason": "interactive commands are not allowed",
            }

    policy_root = repo_root or _repo_root()
    allowlist, deny_substrings = _allowlist_policy(policy_root)
    pack_allow = pack_payload.get("allow") if isinstance(pack_payload, dict) else []
    if isinstance(pack_allow, list) and pack_allow:
        allowlist = [item for item in pack_allow if isinstance(item, dict)]
    pack_deny = pack_payload.get("deny_substrings") if isinstance(pack_payload, dict) else []
    if isinstance(pack_deny, list):
        deny_substrings = list(deny_substrings) + [str(item).lower() for item in pack_deny if str(item).strip()]
    if not allowlist:
        return {
            "ok": False,
            "command": command,
            "violations": ["allowlist-missing"],
            "reason": "command allowlist unavailable",
        }

    for token in deny_substrings:
        if token and token in lowered:
            return {
                "ok": False,
                "command": command,
                "violations": [token],
                "reason": "command contains forbidden action",
            }

    binary, error = _resolve_binary(tokens[0], repo_root)
    if error:
        return {
            "ok": False,
            "command": command,
            "violations": [error],
            "reason": error,
        }

    if binary and not _match_allowlist(tokens, binary, allowlist):
        return {
            "ok": False,
            "command": command,
            "violations": [binary],
            "reason": "command not in allowlist",
        }

    if binary in _SCRIPT_BINARIES:
        if any(flag in tokens for flag in _INLINE_EXEC_FLAGS):
            return {
                "ok": False,
                "command": command,
                "violations": [flag for flag in _INLINE_EXEC_FLAGS if flag in tokens],
                "reason": "inline execution not allowed",
            }
        script_token, error, module_mode = _extract_script_target(tokens)
        if module_mode:
            return {"ok": True, "command": command, "violations": [], "reason": ""}
        if error:
            return {
                "ok": False,
                "command": command,
                "violations": [error],
                "reason": error,
            }
        if repo_root is None:
            return {
                "ok": False,
                "command": command,
                "violations": ["script path requires repo_root"],
                "reason": "script path requires repo_root",
            }
        target = Path(script_token)
        if target.is_absolute():
            candidate = target.resolve()
        else:
            candidate = (repo_root / target).resolve()
        if not _is_within(candidate, repo_root):
            return {
                "ok": False,
                "command": command,
                "violations": ["script path outside repo"],
                "reason": "script path outside repo",
            }
        if not candidate.exists():
            return {
                "ok": False,
                "command": command,
                "violations": ["script path not found"],
                "reason": "script path not found",
            }

    return {"ok": True, "command": command, "violations": [], "reason": ""}


def run_tool_gate(
    command: str,
    allowed: Iterable[str],
    policy_pack: str | None = None,
    repo_root: Path | None = None,
) -> dict:
    if repo_root is None:
        repo_root = _repo_root()
    return validate_command(command, allowed, policy_pack=policy_pack, repo_root=repo_root)
