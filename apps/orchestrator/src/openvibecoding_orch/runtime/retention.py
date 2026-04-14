from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from openvibecoding_orch.config import OpenVibeCodingConfig

CANONICAL_CACHE_NAMESPACES = ("runtime", "test", "build")
RETENTION_REPORT_SCHEMA_VERSION = 6
RETENTION_SCOPE_LABELS = ("runs", "worktrees", "logs", "cache", "codex_homes", "intakes", "contracts", "machine_cache")


@dataclass(frozen=True)
class MachineCacheCandidate:
    path: Path
    policy_entry_id: str
    ttl_hours: int
    age_hours: float
    size_bytes: int
    selection_reason: str


@dataclass(frozen=True)
class RetentionPlan:
    run_candidates: list[Path]
    worktree_candidates: list[Path]
    log_candidates: list[Path]
    cache_candidates: list[Path]
    codex_home_candidates: list[Path]
    intake_candidates: list[Path]
    contract_candidates: list[Path]
    machine_cache_entries: list[dict[str, Any]] = field(default_factory=list)
    machine_cache_candidates: list[MachineCacheCandidate] = field(default_factory=list)

    @property
    def total_candidates(self) -> int:
        return (
            len(self.run_candidates)
            + len(self.worktree_candidates)
            + len(self.log_candidates)
            + len(self.cache_candidates)
            + len(self.codex_home_candidates)
            + len(self.intake_candidates)
            + len(self.contract_candidates)
            + len(self.machine_cache_candidates)
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _cutoff(days: int) -> datetime:
    return _utc_now() - timedelta(days=days)


def _cutoff_hours(hours: int) -> datetime:
    return _utc_now() - timedelta(hours=hours)


def _mtime_utc(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _safe_collect_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted([item for item in root.iterdir() if item.is_dir()])


def _safe_collect_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted([item for item in root.rglob("*") if item.is_file()])


def _path_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def _path_within_prefixes(path: Path, prefixes: list[Path]) -> bool:
    resolved = path.resolve(strict=False)
    for prefix in prefixes:
        try:
            resolved.relative_to(prefix.resolve(strict=False))
            return True
        except ValueError:
            continue
    return False


def _path_size_bytes_excluding(path: Path, excluded_prefixes: list[Path]) -> int:
    if not path.exists():
        return 0
    if _path_within_prefixes(path, excluded_prefixes):
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file() and not _path_within_prefixes(child, excluded_prefixes):
                total += child.stat().st_size
        except OSError:
            continue
    return total


def human_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{int(num_bytes)} B"


def _cache_namespace(path: Path, cache_root: Path) -> str:
    try:
        relative = path.resolve().relative_to(cache_root.resolve())
    except ValueError:
        return "__out_of_scope__"
    return relative.parts[0] if relative.parts else "__root__"


def _cache_namespace_summary(cache_candidates: list[Path], cache_root: Path) -> dict[str, Any]:
    bucket_counts: dict[str, int] = {}
    for path in cache_candidates:
        bucket = _cache_namespace(path, cache_root)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    non_contract_buckets = sorted(
        bucket
        for bucket in bucket_counts
        if bucket not in CANONICAL_CACHE_NAMESPACES
    )
    return {
        "canonical_namespaces": list(CANONICAL_CACHE_NAMESPACES),
        "candidate_bucket_counts": dict(sorted(bucket_counts.items())),
        "non_contract_buckets": non_contract_buckets,
    }


def _test_output_root(cfg: OpenVibeCodingConfig) -> Path:
    return cfg.runtime_root.parent / "test_output"


def _test_output_visibility_summary(test_output_root: Path) -> dict[str, Any]:
    if not test_output_root.exists():
        return {
            "path": str(test_output_root),
            "exists": False,
            "total_files": 0,
            "total_size_bytes": 0,
            "root_level_files": [],
            "bucket_file_counts": {},
        }

    total_files = 0
    total_size_bytes = 0
    bucket_file_counts: dict[str, int] = {}
    root_level_files: list[str] = []
    for path in sorted(test_output_root.rglob("*")):
        if not path.is_file():
            continue
        total_files += 1
        total_size_bytes += path.stat().st_size
        relative = path.relative_to(test_output_root)
        if len(relative.parts) == 1:
            root_level_files.append(str(relative))
            bucket = "__root__"
        else:
            bucket = relative.parts[0]
        bucket_file_counts[bucket] = bucket_file_counts.get(bucket, 0) + 1

    return {
        "path": str(test_output_root),
        "exists": True,
        "total_files": total_files,
        "total_size_bytes": total_size_bytes,
        "root_level_files": root_level_files,
        "bucket_file_counts": dict(sorted(bucket_file_counts.items())),
    }


def _cleanup_scope(cfg: OpenVibeCodingConfig) -> dict[str, Any]:
    return {
        "labels": list(RETENTION_SCOPE_LABELS),
        "included_roots": {
            "runs": str(cfg.runs_root),
            "worktrees": str(cfg.worktree_root),
            "logs": str(cfg.logs_root),
            "cache": str(cfg.cache_root),
            "codex_homes": str(cfg.runtime_root / "codex-homes"),
            "intakes": str(cfg.runtime_root / "intakes"),
            "contracts": str(cfg.runtime_contract_root),
            "machine_cache": str(cfg.machine_cache_root),
        },
        "observed_roots": {
            "test_output": str(_test_output_root(cfg)),
        },
        "protected_live_roots": {
            "active_contract": str(cfg.runtime_root / "active"),
            "machine_cache_toolchains": str(cfg.machine_cache_root / "toolchains"),
            "machine_cache_python_current": str(cfg.machine_cache_root / "toolchains" / "python" / "current"),
        },
        "excluded_examples": [
            str(cfg.runtime_root / "backups"),
            str(cfg.runtime_root / "temp"),
            str(cfg.runtime_root / "locks"),
            str(cfg.machine_cache_root),
        ],
    }


def _log_lane_summary(cfg: OpenVibeCodingConfig) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for lane in ("runtime", "error", "access", "e2e", "ci", "governance"):
        lane_root = cfg.logs_root / lane
        files = _safe_collect_files(lane_root)
        total_size_bytes = sum(path.stat().st_size for path in files)
        newest_mtime = max((_mtime_utc(path) for path in files), default=None)
        oldest_mtime = min((_mtime_utc(path) for path in files), default=None)
        max_file_size_bytes = max((path.stat().st_size for path in files), default=0)
        summary[lane] = {
            "path": str(lane_root),
            "file_count": len(files),
            "total_size_bytes": total_size_bytes,
            "newest_mtime": newest_mtime.isoformat() if newest_mtime else None,
            "oldest_mtime": oldest_mtime.isoformat() if oldest_mtime else None,
            "rotation_headroom_bytes_estimate": max(int(cfg.logging.max_bytes) - max_file_size_bytes, 0),
            "max_file_size_bytes": max_file_size_bytes,
        }
    return summary


def _space_bridge(cfg: OpenVibeCodingConfig) -> dict[str, Any]:
    report_path = cfg.runtime_root / "reports" / "space_governance" / "report.json"
    if not report_path.exists():
        return {
            "path": str(report_path),
            "exists": False,
            "latest_space_audit_generated_at": None,
            "repo_internal_total_bytes": 0,
            "repo_external_related_total_bytes": 0,
            "shared_observation_total_bytes": 0,
        }
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "path": str(report_path),
            "exists": True,
            "latest_space_audit_generated_at": None,
            "repo_internal_total_bytes": 0,
            "repo_external_related_total_bytes": 0,
            "shared_observation_total_bytes": 0,
        }
    summary = payload.get("summary", {})
    return {
        "path": str(report_path),
        "exists": True,
        "latest_space_audit_generated_at": payload.get("generated_at"),
        "repo_internal_total_bytes": int(summary.get("repo_internal_total_bytes", 0)),
        "repo_external_related_total_bytes": int(summary.get("repo_external_related_total_bytes", 0)),
        "shared_observation_total_bytes": int(summary.get("shared_observation_total_bytes", 0)),
    }


def _load_machine_cache_policy(cfg: OpenVibeCodingConfig) -> dict[str, Any] | None:
    policy_path = cfg.repo_root / "configs" / "space_governance_policy.json"
    if not policy_path.exists():
        return None

    from openvibecoding_orch.runtime.space_governance import load_space_governance_policy

    return load_space_governance_policy(policy_path)


def _machine_cache_policy_prefixes(cfg: OpenVibeCodingConfig, key: str) -> list[Path]:
    policy = _load_machine_cache_policy(cfg)
    if not isinstance(policy, dict):
        return []
    machine_cache_policy = policy.get("machine_cache_retention_policy", {})
    if not isinstance(machine_cache_policy, dict):
        return []
    raw_items = machine_cache_policy.get(key, [])
    if not isinstance(raw_items, list):
        return []
    prefixes: list[Path] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        text = str(raw_item or "").strip()
        if not text:
            continue
        text = text.replace("${OPENVIBECODING_MACHINE_CACHE_ROOT}", str(cfg.machine_cache_root))
        path = Path(text).expanduser()
        path = path.resolve() if path.is_absolute() else (cfg.repo_root / path).resolve()
        normalized = str(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        prefixes.append(path)
    return prefixes


def _machine_cache_retention_entries(cfg: OpenVibeCodingConfig) -> list[dict[str, Any]]:
    policy = _load_machine_cache_policy(cfg)
    if not isinstance(policy, dict):
        return []

    from openvibecoding_orch.runtime.space_governance import collect_process_matches, expand_policy_entry

    current_time = _utc_now()
    recent_window_hours = int(policy.get("recent_activity_hours", 24))
    protected_prefixes = _machine_cache_policy_prefixes(cfg, "protected_prefixes")
    cap_excluded_prefixes = _machine_cache_policy_prefixes(cfg, "cap_excluded_prefixes")
    entries: list[dict[str, Any]] = []
    for entry_spec in policy.get("layers", {}).get("repo_external_related", []):
        if not bool(entry_spec.get("retention_auto_cleanup", False)):
            continue
        ttl_hours = int(entry_spec.get("retention_ttl_hours", 0))
        if ttl_hours <= 0:
            continue
        if str(entry_spec.get("cleanup_mode", "")) != "remove-path":
            continue
        for entry in expand_policy_entry(
            repo_root=cfg.repo_root,
            entry_spec=entry_spec,
            layer_name="repo_external_related",
            policy=policy,
            now=current_time,
            recent_window_hours=recent_window_hours,
        ):
            if not bool(entry.get("exists")):
                continue
            if bool(entry.get("shared_realpath_escape", False)):
                continue
            resolved_path = Path(str(entry.get("canonical_path", entry["path"])))
            try:
                relative = resolved_path.relative_to(cfg.machine_cache_root.resolve())
            except ValueError:
                continue
            if not relative.parts:
                continue
            if Path(str(entry["path"])).is_symlink():
                continue
            entry["retention_ttl_hours"] = ttl_hours
            entry["size_bytes"] = _path_size_bytes(Path(str(entry["path"])))
            entry["retention_protected"] = _path_within_prefixes(Path(str(entry["path"])), protected_prefixes)
            entry["retention_cap_excluded"] = _path_within_prefixes(Path(str(entry["path"])), cap_excluded_prefixes)
            process_blockers: list[dict[str, Any]] = []
            if entry.get("process_path_hints") or entry.get("process_command_hints"):
                process_matches = collect_process_matches(
                    policy=policy,
                    repo_root=cfg.repo_root,
                    entries=[entry],
                )
                process_blockers = [
                    {
                        "process_group": group_name,
                        "matches": [
                            match
                            for match in matches
                            if str(match.get("scope", "")).strip() in {"repo_scoped", "target_scoped"}
                        ],
                    }
                    for group_name, matches in process_matches.items()
                    if any(str(match.get("scope", "")).strip() in {"repo_scoped", "target_scoped"} for match in matches)
                ]
            entry["retention_process_blockers"] = process_blockers
            entry["retention_process_blocked"] = bool(process_blockers)
            entries.append(entry)
    return entries


def _machine_cache_retention_candidates(
    cfg: OpenVibeCodingConfig,
    *,
    entries: list[dict[str, Any]],
) -> list[MachineCacheCandidate]:
    machine_cache_root = cfg.machine_cache_root
    if not machine_cache_root.exists():
        return []

    if not entries:
        return []

    cap_excluded_prefixes = _machine_cache_policy_prefixes(cfg, "cap_excluded_prefixes")
    total_size_bytes = _path_size_bytes_excluding(machine_cache_root, cap_excluded_prefixes)
    cap_bytes = cfg.retention_machine_cache_cap_bytes
    current_time = _utc_now()
    selected: dict[str, MachineCacheCandidate] = {}
    reclaim_bytes = 0

    def _candidate_from_entry(entry: dict[str, Any], *, selection_reason: str) -> MachineCacheCandidate:
        mtime_raw = str(entry.get("mtime_utc") or "")
        mtime = datetime.fromisoformat(mtime_raw) if mtime_raw else current_time
        age_hours = max((current_time - mtime).total_seconds() / 3600.0, 0.0)
        return MachineCacheCandidate(
            path=Path(str(entry["path"])),
            policy_entry_id=str(entry["policy_entry_id"]),
            ttl_hours=int(entry.get("retention_ttl_hours", 0)),
            age_hours=age_hours,
            size_bytes=int(entry.get("size_bytes", 0)),
            selection_reason=selection_reason,
        )

    ordered_entries = sorted(
        entries,
        key=lambda entry: (
            entry.get("mtime_utc") or "",
            str(entry.get("path", "")),
        ),
    )

    for entry in ordered_entries:
        if bool(entry.get("retention_process_blocked", False)):
            continue
        if bool(entry.get("retention_protected", False)) or bool(entry.get("retention_cap_excluded", False)):
            continue
        candidate = _candidate_from_entry(entry, selection_reason="ttl_expired")
        if candidate.age_hours < float(candidate.ttl_hours):
            continue
        key = str(candidate.path.resolve(strict=False))
        selected[key] = candidate
        reclaim_bytes += candidate.size_bytes

    over_cap_bytes = max(total_size_bytes - cap_bytes, 0)
    if over_cap_bytes > reclaim_bytes:
        cap_pressure_entries = sorted(
            entries,
            key=lambda entry: (
                entry.get("mtime_utc") or "",
                -int(entry.get("size_bytes", 0)),
                str(entry.get("path", "")),
            ),
        )
        for entry in cap_pressure_entries:
            if bool(entry.get("retention_process_blocked", False)):
                continue
            if bool(entry.get("retention_protected", False)) or bool(entry.get("retention_cap_excluded", False)):
                continue
            candidate = _candidate_from_entry(entry, selection_reason="cap_pressure")
            key = str(candidate.path.resolve(strict=False))
            if key in selected:
                continue
            selected[key] = candidate
            reclaim_bytes += candidate.size_bytes
            if reclaim_bytes >= over_cap_bytes:
                break

    return sorted(
        selected.values(),
        key=lambda item: (item.selection_reason, item.path.as_posix()),
    )


def _machine_cache_summary(
    cfg: OpenVibeCodingConfig,
    entries: list[dict[str, Any]],
    candidates: list[MachineCacheCandidate],
) -> dict[str, Any]:
    machine_cache_root = cfg.machine_cache_root
    total_size_bytes = _path_size_bytes(machine_cache_root)
    cap_excluded_prefixes = _machine_cache_policy_prefixes(cfg, "cap_excluded_prefixes")
    protected_prefixes = _machine_cache_policy_prefixes(cfg, "protected_prefixes")
    cap_tracked_total_bytes = _path_size_bytes_excluding(machine_cache_root, cap_excluded_prefixes)
    cap_excluded_total_bytes = max(total_size_bytes - cap_tracked_total_bytes, 0)
    cap_bytes = cfg.retention_machine_cache_cap_bytes
    reclaim_bytes = sum(item.size_bytes for item in candidates)
    candidate_paths = {str(item.path.resolve(strict=False)) for item in candidates}
    reason_counts: dict[str, int] = {}
    bucket_counts: dict[str, int] = {}
    process_blocked_entries = [entry for entry in entries if bool(entry.get("retention_process_blocked", False))]
    for item in candidates:
        reason_counts[item.selection_reason] = reason_counts.get(item.selection_reason, 0) + 1
        bucket_counts[item.policy_entry_id] = bucket_counts.get(item.policy_entry_id, 0) + 1
    projected_remaining_bytes = max(cap_tracked_total_bytes - reclaim_bytes, 0)
    return {
        "path": str(machine_cache_root),
        "exists": machine_cache_root.exists(),
        "cap_bytes": cap_bytes,
        "cap_human": human_size(cap_bytes),
        "total_size_bytes": total_size_bytes,
        "total_size_human": human_size(total_size_bytes),
        "cap_tracked_total_bytes": cap_tracked_total_bytes,
        "cap_tracked_total_human": human_size(cap_tracked_total_bytes),
        "cap_excluded_total_bytes": cap_excluded_total_bytes,
        "cap_excluded_total_human": human_size(cap_excluded_total_bytes),
        "cap_excluded_prefixes": [str(path) for path in cap_excluded_prefixes],
        "protected_prefixes": [str(path) for path in protected_prefixes],
        "over_cap_bytes": max(cap_tracked_total_bytes - cap_bytes, 0),
        "over_cap_human": human_size(max(cap_tracked_total_bytes - cap_bytes, 0)),
        "candidate_count": len(candidates),
        "candidate_reclaim_bytes": reclaim_bytes,
        "candidate_reclaim_human": human_size(reclaim_bytes),
        "projected_remaining_bytes": projected_remaining_bytes,
        "projected_remaining_human": human_size(projected_remaining_bytes),
        "projected_over_cap_bytes": max(projected_remaining_bytes - cap_bytes, 0),
        "projected_over_cap_human": human_size(max(projected_remaining_bytes - cap_bytes, 0)),
        "scanned_entry_count": len(entries),
        "process_blocked_count": len(process_blocked_entries),
        "process_blocked_paths": [str(entry.get("path", "")) for entry in process_blocked_entries],
        "candidate_reason_counts": dict(sorted(reason_counts.items())),
        "candidate_bucket_counts": dict(sorted(bucket_counts.items())),
        "entries": [
            {
                "path": str(entry.get("path", "")),
                "policy_entry_id": str(entry.get("policy_entry_id", "")),
                "ttl_hours": int(entry.get("retention_ttl_hours", 0)),
                "age_hours": round(
                    max(
                        (
                            _utc_now() - datetime.fromisoformat(str(entry.get("mtime_utc") or _utc_now().isoformat()))
                        ).total_seconds()
                        / 3600.0,
                        0.0,
                    ),
                    2,
                ),
                "size_bytes": int(entry.get("size_bytes", 0)),
                "cleanup_candidate": str(Path(str(entry.get("path", ""))).resolve(strict=False)) in candidate_paths,
                "process_blocked": bool(entry.get("retention_process_blocked", False)),
                "protected": bool(entry.get("retention_protected", False)),
                "cap_excluded": bool(entry.get("retention_cap_excluded", False)),
            }
            for entry in entries
        ],
        "candidates": [
            {
                "path": str(item.path),
                "policy_entry_id": item.policy_entry_id,
                "ttl_hours": item.ttl_hours,
                "age_hours": round(item.age_hours, 2),
                "size_bytes": item.size_bytes,
                "selection_reason": item.selection_reason,
            }
            for item in candidates
        ],
    }


def _machine_cache_auto_prune_summary(cfg: OpenVibeCodingConfig) -> dict[str, Any] | None:
    state_path = cfg.machine_cache_root / "retention-auto-prune" / "state.json"
    if not state_path.exists():
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "path": str(state_path),
            "exists": True,
            "status": "invalid",
        }
    if not isinstance(payload, dict):
        return {
            "path": str(state_path),
            "exists": True,
            "status": "invalid",
        }
    payload["path"] = str(state_path)
    payload["exists"] = True
    return payload


def _overflow_log_candidates(logs_root: Path, max_files: int) -> list[Path]:
    if max_files <= 0:
        return []
    by_group: dict[Path, list[Path]] = {}
    for path in _safe_collect_files(logs_root):
        group = path.parent
        by_group.setdefault(group, []).append(path)

    overflow: list[Path] = []
    for files in by_group.values():
        if len(files) <= max_files:
            continue
        sorted_files = sorted(files, key=_mtime_utc, reverse=True)
        overflow.extend(sorted_files[max_files:])
    return overflow


def _collect_contract_artifacts(contract_root: Path) -> list[Path]:
    buckets = ("results", "reviews", "tasks")
    items: list[Path] = []
    for bucket in buckets:
        base = contract_root / bucket
        if not base.exists():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and child.name.startswith("run_"):
                items.append(child)
            elif child.is_file() and child.name.startswith("task-") and child.suffix == ".json":
                items.append(child)
    return items


def build_retention_plan(cfg: OpenVibeCodingConfig) -> RetentionPlan:
    runs = _safe_collect_dirs(cfg.runs_root)
    worktrees = _safe_collect_dirs(cfg.worktree_root)
    logs = _safe_collect_files(cfg.logs_root)
    caches = _safe_collect_files(cfg.cache_root)
    codex_homes = _safe_collect_dirs(cfg.runtime_root / "codex-homes")
    intakes = _safe_collect_dirs(cfg.runtime_root / "intakes")
    contract_artifacts = _collect_contract_artifacts(cfg.runtime_contract_root)

    run_cutoff = _cutoff(cfg.retention_run_days)
    worktree_cutoff = _cutoff(cfg.retention_worktree_days)
    log_cutoff = _cutoff(cfg.retention_log_days)
    cache_cutoff = _cutoff_hours(cfg.retention_cache_hours)
    codex_home_cutoff = _cutoff(cfg.retention_codex_home_days)
    intake_cutoff = _cutoff(cfg.retention_intake_days)
    contract_cutoff = _cutoff(cfg.retention_run_days)

    expired_runs = [path for path in runs if _mtime_utc(path) < run_cutoff]
    if len(runs) > cfg.retention_max_runs:
        sorted_runs = sorted(runs, key=_mtime_utc)
        overflow = len(runs) - cfg.retention_max_runs
        expired_runs.extend(sorted_runs[:overflow])
    unique_runs = sorted(set(expired_runs))

    expired_worktrees = [path for path in worktrees if _mtime_utc(path) < worktree_cutoff]

    aged_logs = [path for path in logs if _mtime_utc(path) < log_cutoff]
    overflow_logs = _overflow_log_candidates(cfg.logs_root, cfg.retention_log_max_files)
    expired_logs = sorted(set(aged_logs + overflow_logs))

    expired_caches = [path for path in caches if _mtime_utc(path) < cache_cutoff]

    expired_codex_homes = [path for path in codex_homes if _mtime_utc(path) < codex_home_cutoff]
    if len(codex_homes) > cfg.retention_max_codex_homes:
        sorted_codex_homes = sorted(codex_homes, key=_mtime_utc)
        overflow = len(codex_homes) - cfg.retention_max_codex_homes
        expired_codex_homes.extend(sorted_codex_homes[:overflow])
    unique_codex_homes = sorted(set(expired_codex_homes))

    expired_intakes = [path for path in intakes if _mtime_utc(path) < intake_cutoff]
    if len(intakes) > cfg.retention_max_intakes:
        sorted_intakes = sorted(intakes, key=_mtime_utc)
        overflow = len(intakes) - cfg.retention_max_intakes
        expired_intakes.extend(sorted_intakes[:overflow])
    unique_intakes = sorted(set(expired_intakes))

    expired_contracts = [path for path in contract_artifacts if _mtime_utc(path) < contract_cutoff]
    if len(contract_artifacts) > cfg.retention_max_runs:
        sorted_contracts = sorted(contract_artifacts, key=_mtime_utc)
        overflow = len(contract_artifacts) - cfg.retention_max_runs
        expired_contracts.extend(sorted_contracts[:overflow])
    unique_contracts = sorted(set(expired_contracts))
    machine_cache_entries = _machine_cache_retention_entries(cfg)
    machine_cache_candidates = _machine_cache_retention_candidates(cfg, entries=machine_cache_entries)

    return RetentionPlan(
        run_candidates=unique_runs,
        worktree_candidates=expired_worktrees,
        log_candidates=expired_logs,
        cache_candidates=expired_caches,
        codex_home_candidates=unique_codex_homes,
        intake_candidates=unique_intakes,
        contract_candidates=unique_contracts,
        machine_cache_entries=machine_cache_entries,
        machine_cache_candidates=machine_cache_candidates,
    )


def _safe_remove_path(path: Path, allowed_root: Path) -> bool:
    try:
        path.resolve().relative_to(allowed_root.resolve())
    except ValueError:
        return False
    if not path.exists():
        return False
    if path.is_dir():
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        path.rmdir()
    else:
        path.unlink(missing_ok=True)
    return True


def apply_retention_plan(cfg: OpenVibeCodingConfig, plan: RetentionPlan) -> dict[str, Any]:
    removed: dict[str, list[str]] = {
        "runs": [],
        "worktrees": [],
        "logs": [],
        "cache": [],
        "codex_homes": [],
        "intakes": [],
        "contracts": [],
        "machine_cache": [],
    }

    for path in plan.run_candidates:
        if _safe_remove_path(path, cfg.runs_root):
            removed["runs"].append(str(path))
    for path in plan.worktree_candidates:
        if _safe_remove_path(path, cfg.worktree_root):
            removed["worktrees"].append(str(path))
    for path in plan.log_candidates:
        if _safe_remove_path(path, cfg.logs_root):
            removed["logs"].append(str(path))
    for path in plan.cache_candidates:
        if _safe_remove_path(path, cfg.cache_root):
            removed["cache"].append(str(path))
    codex_homes_root = cfg.runtime_root / "codex-homes"
    for path in plan.codex_home_candidates:
        if _safe_remove_path(path, codex_homes_root):
            removed["codex_homes"].append(str(path))
    intakes_root = cfg.runtime_root / "intakes"
    for path in plan.intake_candidates:
        if _safe_remove_path(path, intakes_root):
            removed["intakes"].append(str(path))
    for path in plan.contract_candidates:
        if _safe_remove_path(path, cfg.runtime_contract_root):
            removed["contracts"].append(str(path))
    for item in plan.machine_cache_candidates:
        if _safe_remove_path(item.path, cfg.machine_cache_root):
            removed["machine_cache"].append(str(item.path))

    return {
        "applied_at": _utc_now().isoformat(),
        "removed": removed,
        "removed_total": sum(len(items) for items in removed.values()),
    }


def write_retention_report(cfg: OpenVibeCodingConfig, plan: RetentionPlan, applied: bool, apply_result: dict[str, Any] | None) -> Path:
    reports_dir = cfg.runtime_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "retention_report.json"
    payload = {
        "schema_version": RETENTION_REPORT_SCHEMA_VERSION,
        "generated_at": _utc_now().isoformat(),
        "applied": applied,
        "policy": {
            "retention_run_days": cfg.retention_run_days,
            "retention_max_runs": cfg.retention_max_runs,
            "retention_log_days": cfg.retention_log_days,
            "retention_worktree_days": cfg.retention_worktree_days,
            "retention_log_max_files": cfg.retention_log_max_files,
            "retention_cache_hours": cfg.retention_cache_hours,
            "retention_codex_home_days": cfg.retention_codex_home_days,
            "retention_max_codex_homes": cfg.retention_max_codex_homes,
            "retention_intake_days": cfg.retention_intake_days,
            "retention_max_intakes": cfg.retention_max_intakes,
            "retention_machine_cache_cap_bytes": cfg.retention_machine_cache_cap_bytes,
        },
        "cleanup_scope": _cleanup_scope(cfg),
        "candidates": {
            "runs": [str(path) for path in plan.run_candidates],
            "worktrees": [str(path) for path in plan.worktree_candidates],
            "logs": [str(path) for path in plan.log_candidates],
            "cache": [str(path) for path in plan.cache_candidates],
            "codex_homes": [str(path) for path in plan.codex_home_candidates],
            "intakes": [str(path) for path in plan.intake_candidates],
            "contracts": [str(path) for path in plan.contract_candidates],
            "machine_cache": [str(item.path) for item in plan.machine_cache_candidates],
            "total": plan.total_candidates,
        },
        "cache_namespace_summary": _cache_namespace_summary(plan.cache_candidates, cfg.cache_root),
        "machine_cache_summary": _machine_cache_summary(cfg, plan.machine_cache_entries, plan.machine_cache_candidates),
        "machine_cache_auto_prune": _machine_cache_auto_prune_summary(cfg),
        "log_lane_summary": _log_lane_summary(cfg),
        "space_bridge": _space_bridge(cfg),
        "test_output_visibility": _test_output_visibility_summary(_test_output_root(cfg)),
        "result": apply_result
        or {
            "removed": {
                "runs": [],
                "worktrees": [],
                "logs": [],
                "cache": [],
                "codex_homes": [],
                "intakes": [],
                "contracts": [],
                "machine_cache": [],
            },
            "removed_total": 0,
        },
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path
