from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


POLICY_LAYERS = (
    "repo_internal",
    "repo_external_related",
    "shared_observation",
)
SUMMARY_BUCKETS = (
    "repo_internal",
    "repo_external_related",
    "shared_layer_observation",
    "needs_verification",
)
SUMMARY_BUCKET_ALIASES = {"shared_observation": "shared_layer_observation"}
DEFAULT_RECENT_ACTIVITY_HOURS = 24
DEFAULT_APPLY_GATE_MAX_AGE_MINUTES = 15
SUMMARY_ROLES = {"leaf", "rollup_root", "breakdown_only"}
SELF_EXCLUDED_COMMAND_FRAGMENTS = (
    "scripts/build_space_governance_report.py",
    "scripts/check_space_cleanup_gate.py",
    "scripts/apply_space_cleanup.py",
    "scripts/cleanup_space.sh",
)


@dataclass(frozen=True)
class RebuildCommandStatus:
    command_id: str
    kind: str
    description: str
    available: bool
    detail: str
    argv: list[str]


class SpaceGovernancePolicyError(ValueError):
    pass


def load_space_governance_policy(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SpaceGovernancePolicyError("space governance policy must be a JSON object")
    if payload.get("version") != 1:
        raise SpaceGovernancePolicyError("space governance policy version must be 1")
    if int(payload.get("apply_gate_max_age_minutes", DEFAULT_APPLY_GATE_MAX_AGE_MINUTES)) <= 0:
        raise SpaceGovernancePolicyError("space governance policy apply_gate_max_age_minutes must be > 0")
    machine_cache_retention_policy = payload.get("machine_cache_retention_policy", {})
    if machine_cache_retention_policy and not isinstance(machine_cache_retention_policy, dict):
        raise SpaceGovernancePolicyError("space governance policy machine_cache_retention_policy must be an object")
    if isinstance(machine_cache_retention_policy, dict) and machine_cache_retention_policy:
        default_cap_bytes = int(machine_cache_retention_policy.get("default_cap_bytes", 0))
        if default_cap_bytes <= 0:
            raise SpaceGovernancePolicyError(
                "space governance policy machine_cache_retention_policy.default_cap_bytes must be > 0"
            )
        auto_prune_interval_sec = int(machine_cache_retention_policy.get("auto_prune_interval_sec", 0))
        if auto_prune_interval_sec <= 0:
            raise SpaceGovernancePolicyError(
                "space governance policy machine_cache_retention_policy.auto_prune_interval_sec must be > 0"
            )
        for list_key in ("protected_prefixes", "cap_excluded_prefixes"):
            values = machine_cache_retention_policy.get(list_key, [])
            if values and not isinstance(values, list):
                raise SpaceGovernancePolicyError(
                    f"space governance policy machine_cache_retention_policy.{list_key} must be a list"
                )

    layers = payload.get("layers")
    if not isinstance(layers, dict):
        raise SpaceGovernancePolicyError("space governance policy must define layers")
    for layer in POLICY_LAYERS:
        raw_entries = layers.get(layer)
        if not isinstance(raw_entries, list):
            raise SpaceGovernancePolicyError(f"space governance policy layer must be list: {layer}")
        for entry in raw_entries:
            if not isinstance(entry, dict):
                raise SpaceGovernancePolicyError(f"space governance policy entry must be object: {layer}")
            for field in (
                "id",
                "path",
                "type",
                "ownership",
                "sharedness",
                "rebuildability",
                "recommendation",
                "cleanup_mode",
                "risk",
                "evidence",
            ):
                if field not in entry:
                    raise SpaceGovernancePolicyError(
                        f"space governance policy entry missing `{field}` in layer `{layer}`"
                    )
            if not isinstance(entry["evidence"], list) or not entry["evidence"]:
                raise SpaceGovernancePolicyError(
                    f"space governance policy entry must include non-empty evidence list: {entry['id']}"
                )
            summary_role = str(entry.get("summary_role", "leaf"))
            if summary_role not in SUMMARY_ROLES:
                raise SpaceGovernancePolicyError(
                    f"space governance policy entry must use supported summary_role {sorted(SUMMARY_ROLES)}: {entry['id']}"
                )
            for hint_field in ("process_path_hints", "process_command_hints"):
                hints = entry.get(hint_field, [])
                if hints and not isinstance(hints, list):
                    raise SpaceGovernancePolicyError(
                        f"space governance policy entry `{entry['id']}` must define list for `{hint_field}`"
                    )
            for list_field in ("rebuild_command_ids", "post_cleanup_command_ids", "cleanup_target_names"):
                values = entry.get(list_field, [])
                if values and not isinstance(values, list):
                    raise SpaceGovernancePolicyError(
                        f"space governance policy entry `{entry['id']}` must define list for `{list_field}`"
                    )
            cleanup_mode = str(entry.get("cleanup_mode", "")).strip()
            if cleanup_mode == "named-descendants":
                if not entry.get("cleanup_target_names"):
                    raise SpaceGovernancePolicyError(
                        f"space governance policy named-descendants entry must declare cleanup_target_names: {entry['id']}"
                    )

    wave_targets = payload.get("wave_targets")
    if not isinstance(wave_targets, dict):
        raise SpaceGovernancePolicyError("space governance policy must define wave_targets")

    known_ids = {
        str(entry["id"])
        for layer in POLICY_LAYERS
        for entry in layers.get(layer, [])
        if isinstance(entry, dict) and entry.get("id")
    }
    for wave_name, wave_payload in wave_targets.items():
        if not isinstance(wave_payload, dict):
            raise SpaceGovernancePolicyError(f"wave_targets.{wave_name} must be an object")
        target_ids = wave_payload.get("target_ids")
        if not isinstance(target_ids, list) or not target_ids:
            raise SpaceGovernancePolicyError(f"wave_targets.{wave_name}.target_ids must be a non-empty list")
        for target_id in target_ids:
            if target_id not in known_ids:
                raise SpaceGovernancePolicyError(f"wave_targets.{wave_name} references unknown target: {target_id}")
        for hint_field in ("process_path_hints", "process_command_hints"):
            hints = wave_payload.get(hint_field, [])
            if hints and not isinstance(hints, list):
                raise SpaceGovernancePolicyError(f"wave_targets.{wave_name}.{hint_field} must be a list")

    process_groups = payload.get("process_groups")
    if not isinstance(process_groups, dict) or not process_groups:
        raise SpaceGovernancePolicyError("space governance policy must define process_groups")

    rebuild_commands = payload.get("rebuild_commands")
    if not isinstance(rebuild_commands, list) or not rebuild_commands:
        raise SpaceGovernancePolicyError("space governance policy must define rebuild_commands")
    for command in rebuild_commands:
        if not isinstance(command, dict):
            raise SpaceGovernancePolicyError("rebuild_commands entries must be objects")
        if command.get("kind") not in {"npm_script", "shell_script"}:
            raise SpaceGovernancePolicyError(
                f"rebuild_commands entry must use supported kind (npm_script|shell_script): {command}"
            )
        args = command.get("args", [])
        if args and not isinstance(args, list):
            raise SpaceGovernancePolicyError(
                f"rebuild_commands args must be a list when present: {command}"
            )

    known_command_ids = {
        str(command.get("id", "")).strip()
        for command in rebuild_commands
        if isinstance(command, dict) and str(command.get("id", "")).strip()
    }
    for layer in POLICY_LAYERS:
        for entry in layers.get(layer, []):
            cleanup_mode = str(entry.get("cleanup_mode", "")).strip()
            apply_eligible = cleanup_mode in {"remove-path", "aged-children", "named-descendants"}
            rebuild_command_ids = [str(item).strip() for item in entry.get("rebuild_command_ids", []) if str(item).strip()]
            verification_command_ids = [
                str(item).strip() for item in entry.get("post_cleanup_command_ids", []) if str(item).strip()
            ]
            missing = sorted(
                command_id
                for command_id in {*(rebuild_command_ids), *(verification_command_ids)}
                if command_id not in known_command_ids
            )
            if missing:
                raise SpaceGovernancePolicyError(
                    f"space governance policy entry references unknown command ids {missing}: {entry['id']}"
                )
            if apply_eligible and str(entry.get("recommendation", "")).strip() != "observe_only":
                if not rebuild_command_ids and not verification_command_ids:
                    raise SpaceGovernancePolicyError(
                        f"apply-eligible space governance policy entry must declare rebuild/verification commands: {entry['id']}"
                    )

    return payload


def build_space_governance_report(
    *,
    repo_root: Path,
    policy: dict[str, Any],
    now: datetime | None = None,
    ps_lines: list[str] | None = None,
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    recent_window_hours = int(policy.get("recent_activity_hours", DEFAULT_RECENT_ACTIVITY_HOURS))
    command_statuses = collect_rebuild_command_statuses(repo_root=repo_root, policy=policy)

    layer_entries: dict[str, list[dict[str, Any]]] = {layer: [] for layer in POLICY_LAYERS}
    all_entries: list[dict[str, Any]] = []

    for layer_name in POLICY_LAYERS:
        for entry_spec in policy["layers"][layer_name]:
            resolved_entries = expand_policy_entry(
                repo_root=repo_root,
                entry_spec=entry_spec,
                layer_name=layer_name,
                policy=policy,
                now=current_time,
                recent_window_hours=recent_window_hours,
            )
            for entry in resolved_entries:
                entry["required_rebuild_commands"] = resolve_rebuild_command_statuses(
                    command_ids=entry_spec.get("rebuild_command_ids", []),
                    statuses=command_statuses,
                )
                entry["post_cleanup_verification_commands"] = resolve_rebuild_command_statuses(
                    command_ids=entry_spec.get("post_cleanup_command_ids", entry_spec.get("rebuild_command_ids", [])),
                    statuses=command_statuses,
                )
                layer_entries[layer_name].append(entry)
                all_entries.append(entry)

    process_matches = collect_process_matches(
        policy=policy,
        repo_root=repo_root,
        entries=all_entries,
        ps_lines=ps_lines,
    )
    annotate_summary_membership(entries=all_entries)

    needs_verification = [
        entry
        for entry in all_entries
        if entry["recommendation"] == "needs_verification"
        or entry["ownership_confidence"] != "High"
        or entry.get("shared_realpath_escape", False)
    ]

    summary = {
        "recent_window_hours": recent_window_hours,
        "bucket_counting_mode": "exclusive",
    }
    for bucket_name in SUMMARY_BUCKETS:
        layer_summary = summarize_bucket_entries(all_entries, bucket_name=bucket_name)
        summary[f"{bucket_name}_reported_total_bytes"] = layer_summary["reported_total_bytes"]
        summary[f"{bucket_name}_reported_total_human"] = human_size(layer_summary["reported_total_bytes"])
        summary[f"{bucket_name}_total_bytes"] = layer_summary["effective_total_bytes"]
        summary[f"{bucket_name}_total_human"] = human_size(layer_summary["effective_total_bytes"])
        summary[f"{bucket_name}_summary_entry_ids"] = layer_summary["effective_entry_ids"]

    summary["shared_observation_reported_total_bytes"] = summary["shared_layer_observation_reported_total_bytes"]
    summary["shared_observation_reported_total_human"] = summary["shared_layer_observation_reported_total_human"]
    summary["shared_observation_total_bytes"] = summary["shared_layer_observation_total_bytes"]
    summary["shared_observation_total_human"] = summary["shared_layer_observation_total_human"]
    summary["shared_observation_summary_entry_ids"] = summary["shared_layer_observation_summary_entry_ids"]

    environment_drift_signals = collect_environment_drift_signals(
        policy=policy,
        summary=summary,
        layer_entries=layer_entries,
    )
    retention_summary = load_retention_summary(repo_root=repo_root)
    docker_runtime_summary = load_docker_runtime_summary(repo_root=repo_root)

    return {
        "generated_at": current_time.isoformat(),
        "repo_root": str(repo_root),
        "policy_version": policy["version"],
        "policy_hash": policy_hash(policy),
        "summary": summary,
        "process_matches": process_matches,
        "rebuild_commands": [status.__dict__ for status in command_statuses],
        "retention_summary": retention_summary,
        "docker_runtime_summary": docker_runtime_summary,
        "layers": layer_entries,
        "needs_verification": needs_verification,
        "environment_drift_signals": environment_drift_signals,
        "top_entries": sorted(all_entries, key=lambda item: item["size_bytes"], reverse=True)[:10],
        "entries": all_entries,
    }


def evaluate_cleanup_gate(
    *,
    repo_root: Path,
    policy: dict[str, Any],
    report: dict[str, Any],
    wave: str,
    allow_recent: bool = False,
    allow_shared: bool = False,
    ps_lines: list[str] | None = None,
) -> dict[str, Any]:
    wave_payload = policy["wave_targets"].get(wave)
    if not isinstance(wave_payload, dict):
        raise SpaceGovernancePolicyError(f"unknown cleanup wave: {wave}")

    target_ids = set(wave_payload.get("target_ids", []))
    selected_entries = [entry for entry in report["entries"] if entry["policy_entry_id"] in target_ids]
    process_groups = list(wave_payload.get("process_groups", []))
    rebuild_requirements = set(wave_payload.get("required_rebuild_commands", []))
    recent_window_hours = int(policy.get("recent_activity_hours", DEFAULT_RECENT_ACTIVITY_HOURS))

    process_matches = collect_process_matches(
        policy=policy,
        repo_root=repo_root,
        entries=selected_entries,
        ps_lines=ps_lines,
        wave_payload=wave_payload,
    )
    active_process_groups = {
        group: [match for match in matches if match.get("scope") in {"repo_scoped", "target_scoped"}]
        for group, matches in process_matches.items()
        if any(match.get("scope") in {"repo_scoped", "target_scoped"} for match in matches)
    }
    noisy_process_groups = {
        group: [match for match in matches if match.get("scope") == "machine_scoped"]
        for group, matches in process_matches.items()
        if any(match.get("scope") == "machine_scoped" for match in matches)
    }

    blocked_reasons: list[str] = []
    manual_reasons: list[str] = []
    blocked_findings: list[dict[str, Any]] = []
    manual_findings: list[dict[str, Any]] = []
    eligible_targets: list[dict[str, Any]] = []

    if active_process_groups:
        for group, matches in sorted(active_process_groups.items()):
            target_scoped = [match for match in matches if match.get("scope") == "target_scoped"]
            repo_scoped = [match for match in matches if match.get("scope") == "repo_scoped"]
            if target_scoped:
                message = f"target-scoped active processes matched this wave: {group}({len(target_scoped)})"
                blocked_reasons.append(message)
                blocked_findings.append(
                    {
                        "blocking_reason_kind": "target_scoped_process",
                        "evidence_scope": "target_scoped_process",
                        "process_group": group,
                        "message": message,
                        "matches": target_scoped,
                    }
                )
            if repo_scoped:
                message = f"repo-scoped active processes matched this wave: {group}({len(repo_scoped)})"
                blocked_reasons.append(message)
                blocked_findings.append(
                    {
                        "blocking_reason_kind": "repo_scoped_process",
                        "evidence_scope": "repo_scoped_process",
                        "process_group": group,
                        "message": message,
                        "matches": repo_scoped,
                    }
                )
    if noisy_process_groups:
        for group, matches in sorted(noisy_process_groups.items()):
            message = (
                "machine-scoped matching processes detected without repo/path proof: "
                f"{group}({len(matches)})"
            )
            manual_reasons.append(message)
            manual_findings.append(
                {
                    "blocking_reason_kind": "unknown",
                    "manual_confirmation_kind": "unknown",
                    "evidence_scope": "unknown",
                    "process_group": group,
                    "message": message,
                    "matches": matches,
                }
            )

    rebuild_status_by_id = {
        item["command_id"]: item
        for item in report.get("rebuild_commands", [])
        if isinstance(item, dict) and item.get("command_id")
    }
    missing_rebuilds = [
        command_id
        for command_id in rebuild_requirements
        if not rebuild_status_by_id.get(command_id, {}).get("available", False)
    ]
    if missing_rebuilds:
        message = "required rebuild entrypoints unavailable: " + ", ".join(sorted(missing_rebuilds))
        blocked_reasons.append(message)
        blocked_findings.append(
            {
                "blocking_reason_kind": "unknown",
                "evidence_scope": "unknown",
                "message": message,
                "missing_rebuild_commands": sorted(missing_rebuilds),
            }
        )

    for entry in selected_entries:
        if entry.get("shared_realpath_escape", False) and not allow_shared:
            message = (
                "target resolves into shared realpath and is excluded from single-repo cleanup: "
                f"{entry['path']}"
            )
            blocked_reasons.append(message)
            blocked_findings.append(
                {
                    "blocking_reason_kind": "cross_repo_symlink",
                    "evidence_scope": "cross_repo_symlink",
                    "message": message,
                    "entry_id": entry["id"],
                    "path": entry["path"],
                }
            )
            continue

        if entry.get("sharedness") in {"repo_machine_shared", "shared_observation"} and not allow_shared:
            message = f"shared cache requires explicit confirmation: {entry['path']}"
            manual_reasons.append(message)
            manual_findings.append(
                {
                    "blocking_reason_kind": "shared_layer",
                    "manual_confirmation_kind": "shared_cache",
                    "evidence_scope": "shared_layer",
                    "message": message,
                    "entry_id": entry["id"],
                    "path": entry["path"],
                }
            )

        if entry.get("recent_activity") and not allow_recent:
            message = (
                f"recent activity within {recent_window_hours}h requires explicit confirmation: {entry['path']}"
            )
            manual_reasons.append(message)
            manual_findings.append(
                {
                    "blocking_reason_kind": "recent_hot_data",
                    "manual_confirmation_kind": "recent_hot_data",
                    "evidence_scope": "recent_hot_data",
                    "message": message,
                    "entry_id": entry["id"],
                    "path": entry["path"],
                }
            )

        cleanup_mode = entry.get("cleanup_mode")
        if cleanup_mode == "remove-path" and entry.get("exists"):
            eligible_targets.append(
                {
                    "entry_id": entry["id"],
                    "path": entry["path"],
                    "canonical_path": entry["canonical_path"],
                    "target_kind": "path",
                    "size_bytes": entry["size_bytes"],
                    "expected_reclaim_bytes": entry["size_bytes"],
                    "classification": entry["recommendation"],
                    "producer": entry.get("producer", ""),
                    "lifecycle": entry.get("lifecycle", ""),
                    "rebuild_entrypoints": entry["required_rebuild_commands"],
                    "post_cleanup_verification_commands": entry["post_cleanup_verification_commands"],
                    "apply_serial_only": bool(entry.get("apply_serial_only", False)),
                }
            )
        elif cleanup_mode in {"aged-children", "named-descendants"}:
            for candidate in entry.get("cleanup_candidates", []):
                if candidate.get("recent_activity") and not allow_recent:
                    message = (
                        f"recent cleanup candidate within {recent_window_hours}h requires explicit confirmation: "
                        f"{candidate['path']}"
                    )
                    manual_reasons.append(message)
                    manual_findings.append(
                        {
                            "blocking_reason_kind": "recent_hot_data",
                            "manual_confirmation_kind": "recent_hot_data",
                            "evidence_scope": "recent_hot_data",
                            "message": message,
                            "entry_id": entry["id"],
                            "path": candidate["path"],
                        }
                    )
                    continue
                eligible_targets.append(
                    {
                        "entry_id": entry["id"],
                        "path": candidate["path"],
                        "canonical_path": candidate.get("canonical_path", candidate["path"]),
                        "target_kind": "named-descendant" if cleanup_mode == "named-descendants" else "aged-child",
                        "size_bytes": candidate["size_bytes"],
                        "expected_reclaim_bytes": candidate["size_bytes"],
                        "classification": entry["recommendation"],
                        "producer": entry.get("producer", ""),
                        "lifecycle": entry.get("lifecycle", ""),
                        "rebuild_entrypoints": entry["required_rebuild_commands"],
                        "post_cleanup_verification_commands": entry["post_cleanup_verification_commands"],
                        "apply_serial_only": bool(entry.get("apply_serial_only", False)),
                    }
                )

    eligible_targets = dedupe_target_list(eligible_targets)
    eligible_targets, deferred_targets = split_serial_cleanup_targets(eligible_targets)
    execution_order = build_execution_order(eligible_targets)
    expected_reclaim_bytes = sum(int(item.get("expected_reclaim_bytes", item.get("size_bytes", 0))) for item in eligible_targets)

    status = "pass"
    if blocked_reasons:
        status = "blocked"
    elif manual_reasons:
        status = "manual_confirmation_required"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "policy_hash": policy_hash(policy),
        "gate_max_age_minutes": int(policy.get("apply_gate_max_age_minutes", DEFAULT_APPLY_GATE_MAX_AGE_MINUTES)),
        "wave": wave,
        "status": status,
        "allow_recent": allow_recent,
        "allow_shared": allow_shared,
        "selected_entries": selected_entries,
        "blocked_reasons": dedupe(blocked_reasons),
        "manual_reasons": dedupe(manual_reasons),
        "blocked_findings": blocked_findings,
        "manual_confirmation_findings": manual_findings,
        "eligible_targets": eligible_targets,
        "deferred_targets": deferred_targets,
        "execution_order": execution_order,
        "expected_reclaim_bytes": expected_reclaim_bytes,
        "active_process_groups": active_process_groups,
        "noisy_process_groups": noisy_process_groups,
        "required_rebuild_commands": sorted(rebuild_requirements),
    }


def render_space_governance_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Space Governance Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Repo internal: **{summary['repo_internal_total_human']}** "
        f"(reported: {summary['repo_internal_reported_total_human']})",
        f"- Repo external related: **{summary['repo_external_related_total_human']}** "
        f"(reported: {summary['repo_external_related_reported_total_human']})",
        f"- Shared layer observation: **{summary['shared_layer_observation_total_human']}** "
        f"(reported: {summary['shared_layer_observation_reported_total_human']})",
        f"- Needs verification: **{summary['needs_verification_total_human']}** "
        f"(reported: {summary['needs_verification_reported_total_human']})",
        "",
        "## Retention Bridge",
        "",
    ]
    retention_summary = report.get("retention_summary")
    if not isinstance(retention_summary, dict):
        lines.append("- retention report unavailable")
    else:
        lines.append(f"- Latest retention report: `{retention_summary.get('generated_at', 'unknown')}`")
        if isinstance(retention_summary.get("result"), dict):
            lines.append(f"- Retention removed_total: **{retention_summary['result'].get('removed_total', 0)}**")
        machine_cache_summary = retention_summary.get("machine_cache_summary")
        if isinstance(machine_cache_summary, dict):
            lines.append(
                "- Machine cache: "
                f"**{machine_cache_summary.get('total_size_human', '0 B')}** total / "
                f"cap **{machine_cache_summary.get('cap_human', '0 B')}** / "
                f"candidates **{machine_cache_summary.get('candidate_count', 0)}**"
            )
            lines.append(
                "- Machine cache cap scope: "
                f"tracked **{machine_cache_summary.get('cap_tracked_total_human', '0 B')}** / "
                f"excluded **{machine_cache_summary.get('cap_excluded_total_human', '0 B')}**"
            )
            lines.append(
                "- Machine cache reclaimable: "
                f"**{machine_cache_summary.get('candidate_reclaim_human', '0 B')}** / "
                f"projected over-cap **{machine_cache_summary.get('projected_over_cap_human', '0 B')}**"
            )
    docker_runtime_summary = report.get("docker_runtime_summary")
    if isinstance(docker_runtime_summary, dict):
        lines.append(
            "- Docker runtime lane: "
            f"`{docker_runtime_summary.get('status', 'unknown')}` / "
            f"managed **{docker_runtime_summary.get('managed_totals', {}).get('managed_total_human', '0 B')}** / "
            f"planned reclaim **{docker_runtime_summary.get('plan', {}).get('planned_reclaim_human', '0 B')}**"
        )
    lines.extend(
        [
            "",
        "## Top Entries",
        "",
        "| Path | Layer | Size | Recommendation | Risk |",
        "| --- | --- | ---: | --- | --- |",
        ]
    )
    for entry in report["top_entries"]:
        lines.append(
            f"| `{entry['path']}` | `{entry['layer']}` | {entry['size_human']} | "
            f"`{entry['recommendation']}` | `{entry['risk']}` |"
        )
    lines.extend(
        [
            "",
            "## Needs Verification",
            "",
        ]
    )
    if not report["needs_verification"]:
        lines.append("- none")
    else:
        for entry in report["needs_verification"]:
            lines.append(
                f"- `{entry['path']}`: {entry['type']} / {entry['recommendation']} / "
                f"sharedness={entry['sharedness']} / ownership={entry['ownership_confidence']}"
            )
    machine_tmp_entries = [entry for entry in report["entries"] if str(entry.get("lifecycle", "")).strip() == "machine_tmp"]
    lines.extend(["", "## Machine Temp Surfaces", ""])
    if not machine_tmp_entries:
        lines.append("- none")
    else:
        lines.extend(
            [
                "| Path | Producer | Lifecycle | TTL | Size | Recommendation |",
                "| --- | --- | --- | --- | ---: | --- |",
            ]
        )
        for entry in sorted(machine_tmp_entries, key=lambda item: item["size_bytes"], reverse=True):
            lines.append(
                f"| `{entry['path']}` | `{entry.get('producer', '') or 'unknown'}` | "
                f"`{entry.get('lifecycle', '') or 'unknown'}` | "
                f"`{entry.get('retention_ttl_hours', 0) or 'n/a'}h` | {entry['size_human']} | "
                f"`{entry['recommendation']}` |"
            )
    lines.extend(["", "## Environment Drift Signals", ""])
    if not report.get("environment_drift_signals"):
        lines.append("- none")
    else:
        for signal in report["environment_drift_signals"]:
            lines.append(f"- `{signal['code']}`: {signal['message']}")
    return "\n".join(lines) + "\n"


def write_report_outputs(report: dict[str, Any], *, output_json: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(render_space_governance_markdown(report), encoding="utf-8")


def expand_policy_entry(
    *,
    repo_root: Path,
    entry_spec: dict[str, Any],
    layer_name: str,
    policy: dict[str, Any],
    now: datetime,
    recent_window_hours: int,
) -> list[dict[str, Any]]:
    raw_path = str(entry_spec["path"])
    resolved_paths = resolve_policy_paths(raw_path=raw_path, repo_root=repo_root)
    if not resolved_paths:
        resolved_paths = [resolve_policy_path(raw_path=raw_path, repo_root=repo_root)]

    entries: list[dict[str, Any]] = []
    for index, path in enumerate(resolved_paths):
        entry_id = str(entry_spec["id"])
        if len(resolved_paths) > 1:
            entry_id = f"{entry_id}:{path.name}"
        entries.append(
            inspect_path_entry(
                repo_root=repo_root,
                path=path,
                layer_name=layer_name,
                entry_id=entry_id,
                policy_entry_id=str(entry_spec["id"]),
                entry_spec=entry_spec,
                policy=policy,
                now=now,
                recent_window_hours=recent_window_hours,
                source_path=raw_path,
            )
        )
    return entries


def inspect_path_entry(
    *,
    repo_root: Path,
    path: Path,
    layer_name: str,
    entry_id: str,
    policy_entry_id: str,
    entry_spec: dict[str, Any],
    policy: dict[str, Any],
    now: datetime,
    recent_window_hours: int,
    source_path: str,
) -> dict[str, Any]:
    exists = path.exists() or path.is_symlink()
    resolved_path = path.resolve(strict=False)
    size_target = resolved_path if path.is_symlink() and resolved_path.exists() else path
    size_bytes = path_size_bytes(size_target) if exists else 0
    stat_target = resolved_path if resolved_path.exists() else path
    mtime = stat_target.stat().st_mtime if exists else None
    recent_activity = False
    mtime_iso = None
    if mtime is not None:
        mtime_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        mtime_iso = mtime_dt.isoformat()
        recent_activity = ((now - mtime_dt).total_seconds() / 3600.0) < float(recent_window_hours)

    shared_realpath_escape = False
    if path.is_symlink() and resolved_path.exists():
        for raw_prefix in policy.get("shared_realpath_prefixes", []):
            prefix_path = resolve_policy_path(raw_path=str(raw_prefix), repo_root=repo_root)
            if is_within(resolved_path, prefix_path):
                shared_realpath_escape = True
                break

    cleanup_candidates: list[dict[str, Any]] = []
    if exists and entry_spec["cleanup_mode"] == "aged-children" and path.is_dir():
        cleanup_candidates = collect_aged_child_candidates(
            base_path=path,
            cleanup_scan_depth=int(entry_spec.get("cleanup_scan_depth", 1)),
            minimum_age_hours=float(entry_spec.get("cleanup_min_age_hours", recent_window_hours)),
            exclude_names={str(item) for item in entry_spec.get("cleanup_exclude_names", [])},
            now=now,
        )
    elif exists and entry_spec["cleanup_mode"] == "named-descendants" and path.is_dir():
        cleanup_candidates = collect_named_descendant_candidates(
            base_path=path,
            target_names={str(item) for item in entry_spec.get("cleanup_target_names", []) if str(item).strip()},
            exclude_names={
                "__pycache__",
                ".pytest_cache",
                "node_modules",
                ".venv",
                ".git",
                ".runtime-cache",
                *(str(item) for item in entry_spec.get("cleanup_exclude_names", []) if str(item).strip()),
            },
            now=now,
            recent_window_hours=recent_window_hours,
        )

    governance_owner = infer_governance_owner(entry_spec=entry_spec, layer_name=layer_name)
    preserve_reason = infer_preserve_reason(entry_spec=entry_spec, layer_name=layer_name)
    expected_rebuild_commands = entry_spec.get("post_cleanup_command_ids", entry_spec.get("rebuild_command_ids", []))

    return {
        "id": entry_id,
        "policy_entry_id": policy_entry_id,
        "layer": layer_name,
        "path": str(path),
        "source_path": source_path,
        "exists": exists,
        "resolved_path": str(resolved_path) if exists else "",
        "path_is_symlink": path.is_symlink(),
        "shared_realpath_escape": shared_realpath_escape,
        "canonical_path": str(resolved_path if exists else path.resolve(strict=False)),
        "size_bytes": size_bytes,
        "size_human": human_size(size_bytes),
        "mtime_utc": mtime_iso,
        "recent_activity": recent_activity,
        "type": entry_spec["type"],
        "ownership": entry_spec["ownership"],
        "ownership_confidence": entry_spec.get("ownership_confidence", "High"),
        "sharedness": entry_spec["sharedness"],
        "summary_role": entry_spec.get("summary_role", "leaf"),
        "rebuildability": entry_spec["rebuildability"],
        "recommendation": entry_spec["recommendation"],
        "cleanup_mode": entry_spec["cleanup_mode"],
        "governance_owner": governance_owner,
        "preserve_reason": preserve_reason,
        "expected_rebuild_cost_class": infer_rebuild_cost_class(entry_spec["rebuildability"]),
        "expected_rebuild_commands": expected_rebuild_commands,
        "apply_serial_only": bool(entry_spec.get("apply_serial_only", False)),
        "retention_auto_cleanup": bool(entry_spec.get("retention_auto_cleanup", False)),
        "retention_ttl_hours": int(entry_spec.get("retention_ttl_hours", 0)),
        "producer": str(entry_spec.get("producer", "")).strip(),
        "lifecycle": str(entry_spec.get("lifecycle", "")).strip(),
        "risk": entry_spec["risk"],
        "evidence": entry_spec["evidence"],
        "notes": entry_spec.get("notes", ""),
        "process_path_hints": entry_spec.get("process_path_hints", []),
        "process_command_hints": entry_spec.get("process_command_hints", []),
        "cleanup_candidates": cleanup_candidates,
    }


def collect_rebuild_command_statuses(*, repo_root: Path, policy: dict[str, Any]) -> list[RebuildCommandStatus]:
    package_json_path = repo_root / "package.json"
    package_scripts: dict[str, Any] = {}
    if package_json_path.exists():
        payload = json.loads(package_json_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("scripts"), dict):
            package_scripts = payload["scripts"]

    statuses: list[RebuildCommandStatus] = []
    for command in policy.get("rebuild_commands", []):
        kind = str(command.get("kind"))
        command_id = str(command.get("id"))
        description = str(command.get("description", command_id))
        args = [str(item) for item in command.get("args", [])]
        if kind == "npm_script":
            script_name = str(command.get("script", "")).strip()
            available = script_name in package_scripts
            detail = f"npm script `{script_name}` {'present' if available else 'missing'}"
            argv = ["npm", "run", script_name]
            if args:
                argv.extend(["--", *args])
        elif kind == "shell_script":
            script_path = resolve_policy_path(raw_path=str(command.get("path", "")), repo_root=repo_root)
            available = script_path.is_file()
            detail = f"script `{script_path}` {'present' if available else 'missing'}"
            argv = ["bash", str(script_path), *args]
        else:
            available = False
            detail = f"unsupported rebuild command kind: {kind}"
            argv = []
        statuses.append(
            RebuildCommandStatus(
                command_id=command_id,
                kind=kind,
                description=description,
                available=available,
                detail=detail,
                argv=argv,
            )
        )
    return statuses


def resolve_rebuild_command_statuses(
    *,
    command_ids: list[str],
    statuses: list[RebuildCommandStatus],
) -> list[dict[str, Any]]:
    lookup = {status.command_id: status for status in statuses}
    result: list[dict[str, Any]] = []
    for command_id in command_ids:
        status = lookup.get(command_id)
        if status is None:
            result.append(
                {
                    "command_id": command_id,
                    "kind": "unknown",
                    "description": command_id,
                    "available": False,
                    "detail": "missing from rebuild command registry",
                    "argv": [],
                }
            )
        else:
            result.append(status.__dict__)
    return result


def collect_process_matches(
    *,
    policy: dict[str, Any],
    repo_root: Path,
    entries: list[dict[str, Any]] | None = None,
    ps_lines: list[str] | None = None,
    wave_payload: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    lines = ps_lines if ps_lines is not None else load_process_lines()
    (
        target_path_hints,
        target_command_hints,
        repo_path_hints,
        repo_command_hints,
    ) = build_process_hints(
        repo_root=repo_root,
        entries=entries or [],
        wave_payload=wave_payload,
    )
    results: dict[str, list[dict[str, Any]]] = {}
    self_pids = {os.getpid(), os.getppid()}
    for group_name, group_payload in policy.get("process_groups", {}).items():
        patterns = [re.compile(str(pattern), re.IGNORECASE) for pattern in group_payload.get("patterns", [])]
        matches: list[dict[str, Any]] = []
        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                continue
            pid, command = parse_process_line(stripped)
            if pid in self_pids:
                continue
            if any(fragment in command for fragment in SELF_EXCLUDED_COMMAND_FRAGMENTS):
                continue
            if any(pattern.search(command) for pattern in patterns):
                scope, reasons = classify_process_scope(
                    command=command,
                    repo_root=repo_root,
                    target_path_hints=target_path_hints,
                    target_command_hints=target_command_hints,
                    repo_path_hints=repo_path_hints,
                    repo_command_hints=repo_command_hints,
                )
                matches.append(
                    {
                        "pid": pid,
                        "command": command,
                        "scope": scope,
                        "relevance_reasons": reasons,
                    }
                )
        results[group_name] = matches
    return results


def load_process_lines() -> list[str]:
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return []
    return proc.stdout.splitlines()


def parse_process_line(raw_line: str) -> tuple[int | None, str]:
    match = re.match(r"^\s*(\d+)\s+(.*)$", raw_line)
    if not match:
        return None, raw_line.strip()
    return int(match.group(1)), match.group(2).strip()


def collect_aged_child_candidates(
    *,
    base_path: Path,
    cleanup_scan_depth: int,
    minimum_age_hours: float,
    exclude_names: set[str],
    now: datetime,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for candidate in iter_paths_at_depth(base_path=base_path, depth=cleanup_scan_depth):
        if candidate.name in exclude_names:
            continue
        if not candidate.exists():
            continue
        candidate_mtime = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
        candidate_age_hours = (now - candidate_mtime).total_seconds() / 3600.0
        if candidate_age_hours < minimum_age_hours:
            continue
        size_bytes = path_size_bytes(candidate)
        candidates.append(
            {
                "path": str(candidate),
                "canonical_path": str(candidate.resolve(strict=False)),
                "size_bytes": size_bytes,
                "size_human": human_size(size_bytes),
                "mtime_utc": candidate_mtime.isoformat(),
                "recent_activity": False,
            }
        )
    return sorted(candidates, key=lambda item: item["size_bytes"], reverse=True)


def collect_named_descendant_candidates(
    *,
    base_path: Path,
    target_names: set[str],
    exclude_names: set[str],
    now: datetime,
    recent_window_hours: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not target_names:
        return candidates
    for root, dirnames, _ in os.walk(base_path):
        dirnames[:] = [dirname for dirname in dirnames if dirname not in exclude_names]
        for dirname in sorted(dirnames):
            if dirname not in target_names:
                continue
            candidate = Path(root) / dirname
            candidate_mtime = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
            size_bytes = path_size_bytes(candidate)
            candidates.append(
                {
                    "path": str(candidate),
                    "canonical_path": str(candidate.resolve(strict=False)),
                    "size_bytes": size_bytes,
                    "size_human": human_size(size_bytes),
                    "mtime_utc": candidate_mtime.isoformat(),
                    "recent_activity": ((now - candidate_mtime).total_seconds() / 3600.0) < float(recent_window_hours),
                }
            )
    return sorted(candidates, key=lambda item: item["size_bytes"], reverse=True)


def iter_paths_at_depth(*, base_path: Path, depth: int) -> list[Path]:
    current: list[Path] = [base_path]
    for _ in range(depth):
        next_level: list[Path] = []
        for path in current:
            if path.is_dir():
                next_level.extend(sorted(path.iterdir()))
        if not next_level:
            break
        current = next_level
    return [path for path in current if path != base_path]


def resolve_policy_paths(*, raw_path: str, repo_root: Path) -> list[Path]:
    resolved = resolve_policy_path(raw_path=raw_path, repo_root=repo_root)
    if not any(char in raw_path for char in "*?[]"):
        return [resolved]
    matches = sorted(Path(match) for match in map(str, resolved.parent.glob(resolved.name)))
    return matches


def resolve_policy_path(*, raw_path: str, repo_root: Path) -> Path:
    normalized = raw_path.replace("$REPO_ROOT", str(repo_root))
    normalized = expand_policy_env_defaults(normalized)
    expanded = Path(os.path.expandvars(os.path.expanduser(normalized)))
    if expanded.is_absolute():
        return expanded
    return repo_root / expanded


def expand_policy_env_defaults(raw_path: str) -> str:
    normalized = raw_path
    if not os.getenv("OPENVIBECODING_MACHINE_CACHE_ROOT"):
        default_value = default_policy_env_value("OPENVIBECODING_MACHINE_CACHE_ROOT")
        normalized = normalized.replace("${OPENVIBECODING_MACHINE_CACHE_ROOT}", default_value)
        normalized = normalized.replace("$OPENVIBECODING_MACHINE_CACHE_ROOT", default_value)
    return normalized


def default_policy_env_value(env_name: str) -> str:
    if env_name == "OPENVIBECODING_MACHINE_CACHE_ROOT":
        return str(Path.home() / ".cache" / "openvibecoding")
    raise SpaceGovernancePolicyError(f"unsupported policy env default: {env_name}")


def path_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        proc = subprocess.run(
            ["du", "-sk", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
        first = proc.stdout.split()[0]
        return int(first) * 1024
    except Exception:
        if path.is_file():
            return int(path.stat().st_size)
        total = 0
        for child in path.rglob("*"):
            if child.is_file():
                total += int(child.stat().st_size)
        return total


def human_size(size_bytes: int) -> str:
    suffixes = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(size_bytes)
    for suffix in suffixes:
        if value < 1024.0 or suffix == suffixes[-1]:
            if suffix == "B":
                return f"{int(value)} {suffix}"
            return f"{value:.2f} {suffix}"
        value /= 1024.0
    return f"{size_bytes} B"


def infer_governance_owner(*, entry_spec: dict[str, Any], layer_name: str) -> str:
    if layer_name == "shared_observation" or str(entry_spec.get("recommendation", "")).strip() == "observe_only":
        return "observe_only"
    raw_path = str(entry_spec.get("path", "")).strip()
    if raw_path.startswith(".runtime-cache/"):
        return "runtime_retention"
    if layer_name == "repo_external_related":
        return "space_wave3"
    if str(entry_spec.get("cleanup_mode", "")).strip() == "named-descendants":
        return "space_wave1"
    if bool(entry_spec.get("apply_serial_only", False)) or str(entry_spec.get("recommendation", "")).strip() == "cautious_cleanup":
        return "space_wave2"
    return "space_wave1"


def infer_preserve_reason(*, entry_spec: dict[str, Any], layer_name: str) -> str:
    raw_path = str(entry_spec.get("path", "")).strip()
    if "backups" in raw_path:
        return "historical_backup"
    if layer_name in {"repo_external_related", "shared_observation"} or str(entry_spec.get("sharedness", "")).strip() in {
        "repo_machine_shared",
        "shared_observation",
    }:
        return "shared_cache"
    if any(token in raw_path for token in (".runtime-cache/logs", ".runtime-cache/test_output", ".runtime-cache/openvibecoding/contracts")):
        return "runtime_evidence"
    if raw_path.startswith(".runtime-cache/"):
        return "runtime_evidence"
    if any(token in raw_path for token in ("node_modules", ".venv", ".next", "dist", "tsbuildinfo", "target", "__pycache__", ".pytest_cache")):
        return "developer_dependency"
    return "unknown_owner"


def infer_rebuild_cost_class(rebuildability: str) -> str:
    normalized = rebuildability.strip().lower()
    if "immediately" in normalized:
        return "immediate"
    if "network" in normalized or "time" in normalized:
        return "network_time"
    if "expensive" in normalized or "high time cost" in normalized:
        return "expensive"
    return "unknown"


def load_retention_summary(*, repo_root: Path) -> dict[str, Any] | None:
    report_path = repo_root / ".runtime-cache" / "openvibecoding" / "reports" / "retention_report.json"
    if not report_path.exists():
        return None
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    result = {
        "path": str(report_path),
        "generated_at": payload.get("generated_at"),
    }
    if isinstance(payload.get("log_lane_summary"), dict):
        result["log_lane_summary"] = payload["log_lane_summary"]
    if isinstance(payload.get("result"), dict):
        result["result"] = {
            "removed_total": payload["result"].get("removed_total", 0),
        }
    if isinstance(payload.get("machine_cache_summary"), dict):
        result["machine_cache_summary"] = payload["machine_cache_summary"]
    if isinstance(payload.get("machine_cache_auto_prune"), dict):
        result["machine_cache_auto_prune"] = payload["machine_cache_auto_prune"]
    if "machine_cache_auto_prune" not in result:
        try:
            from openvibecoding_orch.config import load_config

            cfg = load_config()
            state_path = cfg.machine_cache_root / "retention-auto-prune" / "state.json"
            if state_path.exists():
                state_payload = json.loads(state_path.read_text(encoding="utf-8"))
                if isinstance(state_payload, dict):
                    state_payload["path"] = str(state_path)
                    state_payload["exists"] = True
                    result["machine_cache_auto_prune"] = state_payload
        except Exception:
            # Optional auto-prune metadata must never block the main retention summary.
            return result
    return result


def load_docker_runtime_summary(*, repo_root: Path) -> dict[str, Any] | None:
    report_path = repo_root / ".runtime-cache" / "openvibecoding" / "reports" / "space_governance" / "docker_runtime.json"
    if not report_path.exists():
        return None
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    payload["path"] = str(report_path)
    return payload


def split_serial_cleanup_targets(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    serial_targets = sorted(
        [item for item in items if item.get("apply_serial_only")],
        key=lambda item: (int(item.get("expected_reclaim_bytes", item.get("size_bytes", 0))), str(item.get("path", ""))),
        reverse=True,
    )
    non_serial_targets = sorted(
        [item for item in items if not item.get("apply_serial_only")],
        key=lambda item: (int(item.get("expected_reclaim_bytes", item.get("size_bytes", 0))), str(item.get("path", ""))),
        reverse=True,
    )
    if len(serial_targets) <= 1:
        return serial_targets + non_serial_targets, []
    kept = serial_targets[:1]
    deferred = [
        {
            "entry_id": item["entry_id"],
            "path": item["path"],
            "reason": "apply_serial_only target deferred until the current heavy target is rebuilt and verified",
        }
        for item in serial_targets[1:]
    ]
    return kept + non_serial_targets, deferred


def build_execution_order(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "entry_id": str(item.get("entry_id", "")),
            "path": str(item.get("path", "")),
            "expected_reclaim_bytes": int(item.get("expected_reclaim_bytes", item.get("size_bytes", 0))),
            "apply_serial_only": bool(item.get("apply_serial_only", False)),
        }
        for item in items
    ]


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def dedupe_target_list(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = (str(item.get("entry_id", "")), str(item.get("path", "")))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def summarize_layer_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    reported_total_bytes = sum(int(entry.get("size_bytes", 0)) for entry in entries)
    effective_entries: list[dict[str, Any]] = []
    effective_paths: list[Path] = []

    sortable_entries = sorted(
        entries,
        key=lambda entry: (
            summary_priority(str(entry.get("summary_role", "leaf"))),
            len(summary_path(entry).parts),
            str(entry.get("path", "")),
        ),
    )
    for entry in sortable_entries:
        if entry.get("summary_role", "leaf") == "breakdown_only":
            continue
        if int(entry.get("size_bytes", 0)) <= 0:
            continue
        current_path = summary_path(entry)
        if any(paths_overlap(current_path, existing) for existing in effective_paths):
            continue
        effective_entries.append(entry)
        effective_paths.append(current_path)

    return {
        "reported_total_bytes": reported_total_bytes,
        "effective_total_bytes": sum(int(entry.get("size_bytes", 0)) for entry in effective_entries),
        "effective_entry_ids": [str(entry.get("id", "")) for entry in effective_entries],
    }


def summarize_bucket_entries(entries: list[dict[str, Any]], *, bucket_name: str) -> dict[str, Any]:
    bucket_entries = [entry for entry in entries if entry.get("summary_bucket") == bucket_name]
    reported_total_bytes = sum(int(entry.get("size_bytes", 0)) for entry in bucket_entries)
    effective_entries = [entry for entry in bucket_entries if entry.get("counted_in_summary", False)]
    return {
        "reported_total_bytes": reported_total_bytes,
        "effective_total_bytes": sum(int(entry.get("size_bytes", 0)) for entry in effective_entries),
        "effective_entry_ids": [str(entry.get("id", "")) for entry in effective_entries],
    }


def collect_environment_drift_signals(
    *,
    policy: dict[str, Any],
    summary: dict[str, Any],
    layer_entries: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    repo_external_entries = layer_entries.get("repo_external_related", [])
    root_entries = [entry for entry in repo_external_entries if entry.get("summary_role", "leaf") == "rollup_root"]
    if (
        root_entries
        and all(not entry.get("exists", False) for entry in root_entries)
        and summary.get("repo_external_related_total_bytes", 0) == 0
        and summary.get("shared_observation_total_bytes", 0) > 0
    ):
        signals.append(
            {
                "code": "policy_external_cache_namespace_absent",
                "message": "policy-owned external cache namespace absent in current environment",
                "paths": [str(entry.get("path", "")) for entry in root_entries],
            }
        )
    python_toolchain_entry = next(
        (
            entry
            for entry in repo_external_entries
            if str(entry.get("policy_entry_id", "")) == "external_python_toolchain_current"
            and entry.get("exists", False)
            and not entry.get("path_is_symlink", False)
        ),
        None,
    )
    if python_toolchain_entry is not None:
        signals.append(
            {
                "code": "python_toolchain_current_materialized_as_directory",
                "message": "external python toolchain current is materialized as a directory rather than a symlink in this environment",
                "paths": [str(python_toolchain_entry.get("path", ""))],
            }
        )
    return signals


def build_process_hints(
    *,
    repo_root: Path,
    entries: list[dict[str, Any]],
    wave_payload: dict[str, Any] | None,
) -> tuple[set[str], set[str], set[str], set[str]]:
    target_path_hints: set[str] = set()
    target_command_hints: set[str] = set()
    repo_path_hints: set[str] = {str(repo_root)}
    repo_command_hints: set[str] = {repo_root.name}

    for entry in entries:
        for raw in (entry.get("path"), entry.get("resolved_path")):
            if isinstance(raw, str) and raw:
                target_path_hints.add(raw)
                rel_hint = build_repo_relative_process_hint(raw_path=raw, repo_root=repo_root)
                if rel_hint:
                    repo_command_hints.add(rel_hint)
        for raw in entry.get("process_path_hints", []) or []:
            if isinstance(raw, str) and raw:
                resolved = resolve_policy_path(raw_path=raw, repo_root=repo_root)
                target_path_hints.add(str(resolved))
        for raw in entry.get("process_command_hints", []) or []:
            if isinstance(raw, str) and raw:
                target_command_hints.add(raw)

    if wave_payload:
        for raw in wave_payload.get("process_path_hints", []) or []:
            if isinstance(raw, str) and raw:
                resolved = resolve_policy_path(raw_path=raw, repo_root=repo_root)
                target_path_hints.add(str(resolved))
                rel_hint = build_repo_relative_process_hint(raw_path=str(resolved), repo_root=repo_root)
                if rel_hint:
                    repo_command_hints.add(rel_hint)
        for raw in wave_payload.get("process_command_hints", []) or []:
            if isinstance(raw, str) and raw:
                target_command_hints.add(raw)

    return (
        {item for item in target_path_hints if item},
        {item for item in target_command_hints if item},
        {item for item in repo_path_hints if item},
        {item for item in repo_command_hints if item},
    )


def classify_process_scope(
    *,
    command: str,
    repo_root: Path,
    target_path_hints: set[str],
    target_command_hints: set[str],
    repo_path_hints: set[str],
    repo_command_hints: set[str],
) -> tuple[str, list[str]]:
    target_path_reasons: list[str] = []
    for hint in sorted(target_path_hints):
        if hint and hint in command:
            target_path_reasons.append(f"path_hint:{hint}")
    if target_path_reasons:
        return "target_scoped", dedupe(target_path_reasons)

    target_command_reasons: list[str] = []
    for hint in sorted(target_command_hints):
        if hint and hint in command:
            target_command_reasons.append(f"command_hint:{hint}")

    repo_reasons: list[str] = []
    repo_root_raw = str(repo_root)
    if repo_root_raw and repo_root_raw in command:
        repo_reasons.append(f"repo_root:{repo_root_raw}")
    for hint in sorted(repo_path_hints):
        if hint and hint in command:
            repo_reasons.append(f"repo_path_hint:{hint}")
    for hint in sorted(repo_command_hints):
        if hint and hint in command:
            repo_reasons.append(f"repo_command_hint:{hint}")
    if target_command_reasons and repo_reasons:
        return "target_scoped", dedupe(target_command_reasons + repo_reasons)
    if repo_reasons:
        return "repo_scoped", dedupe(repo_reasons)
    return "machine_scoped", []

def build_repo_relative_process_hint(*, raw_path: str, repo_root: Path) -> str:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        return ""
    try:
        rel = candidate.relative_to(repo_root)
    except ValueError:
        return ""
    if rel.parts and rel.parts[0].startswith("."):
        return ""
    if len(rel.parts) >= 2:
        return "/".join(rel.parts[:2])
    return rel.as_posix()


def summary_path(entry: dict[str, Any]) -> Path:
    resolved = str(entry.get("resolved_path", "")).strip()
    if resolved:
        return Path(resolved)
    return Path(str(entry.get("path", "")))


def summary_priority(summary_role: str) -> int:
    if summary_role == "rollup_root":
        return 0
    if summary_role == "leaf":
        return 1
    return 2


def paths_overlap(left: Path, right: Path) -> bool:
    return is_within(left, right) or is_within(right, left)


def revalidate_cleanup_targets(
    *,
    repo_root: Path,
    policy: dict[str, Any],
    gate: dict[str, Any],
) -> dict[str, Any]:
    wave = str(gate.get("wave", ""))
    wave_payload = policy.get("wave_targets", {}).get(wave)
    if not isinstance(wave_payload, dict):
        raise SpaceGovernancePolicyError(f"unknown cleanup wave during apply revalidation: {wave}")
    gate_errors: list[str] = []
    gate_status = str(gate.get("status", ""))
    if gate_status != "pass":
        gate_errors.append(f"gate status must be pass before apply, got `{gate_status or 'missing'}`")
    gate_repo_root = str(gate.get("repo_root", ""))
    if gate_repo_root != str(repo_root):
        gate_errors.append("gate repo_root does not match current repo root")
    if str(gate.get("policy_hash", "")) != policy_hash(policy):
        gate_errors.append("gate policy hash does not match current policy")
    gate_generated_at = parse_iso_datetime(str(gate.get("generated_at", "")))
    if gate_generated_at is None:
        gate_errors.append("gate generated_at is missing or invalid")
    else:
        max_age_minutes = int(gate.get("gate_max_age_minutes", policy.get("apply_gate_max_age_minutes", DEFAULT_APPLY_GATE_MAX_AGE_MINUTES)))
        gate_age_minutes = (datetime.now(timezone.utc) - gate_generated_at).total_seconds() / 60.0
        if gate_age_minutes > float(max_age_minutes):
            gate_errors.append(f"gate artifact is stale ({gate_age_minutes:.1f}m > {max_age_minutes}m)")
    if str(gate.get("wave", "")) != wave:
        gate_errors.append("gate wave is missing or invalid")

    current_time = datetime.now(timezone.utc)
    recent_window_hours = int(policy.get("recent_activity_hours", DEFAULT_RECENT_ACTIVITY_HOURS))
    allowed_index: dict[str, dict[str, Any]] = {}
    for layer_name in POLICY_LAYERS:
        for entry_spec in policy["layers"][layer_name]:
            if str(entry_spec.get("id", "")) not in set(wave_payload.get("target_ids", [])):
                continue
            for entry in expand_policy_entry(
                repo_root=repo_root,
                entry_spec=entry_spec,
                layer_name=layer_name,
                policy=policy,
                now=current_time,
                recent_window_hours=recent_window_hours,
            ):
                allowed_index[str(entry["id"])] = entry

    validated_targets: list[dict[str, Any]] = []
    rejected_targets: list[dict[str, Any]] = []
    repo_root_resolved = repo_root.resolve()

    if gate_errors:
        return {
            "wave": wave,
            "gate_errors": gate_errors,
            "validated_targets": [],
            "rejected_targets": [],
        }

    for raw_target in gate.get("eligible_targets", []):
        target = dict(raw_target)
        entry_id = str(target.get("entry_id", ""))
        path_raw = str(target.get("path", ""))
        reason = ""
        entry = allowed_index.get(entry_id)
        if entry is None:
            reason = "entry_id is not part of the current wave allowlist"
        else:
            target_path = Path(path_raw).expanduser()
            if not target_path.is_absolute():
                target_path = (repo_root / target_path).resolve(strict=False)
            canonical_target = target_path.resolve(strict=False)
            if not target_path.exists() and not target_path.is_symlink():
                reason = "target no longer exists"
            if entry.get("shared_realpath_escape", False):
                reason = "target resolves into a shared realpath escape and is not eligible for apply"
            elif entry.get("sharedness") == "shared_observation":
                reason = "shared observation layer is not eligible for apply"
            elif entry.get("recommendation") == "observe_only":
                reason = "observe-only target is not eligible for apply"
            elif bool(entry.get("recent_activity")) and not bool(gate.get("allow_recent", False)):
                reason = "recently active target requires explicit gate override"
            elif entry.get("sharedness") == "repo_machine_shared" and not bool(gate.get("allow_shared", False)):
                reason = "shared repo-machine cache requires explicit gate override"
            elif entry.get("cleanup_mode") == "remove-path":
                if path_raw != str(entry.get("path", "")):
                    reason = "remove-path target does not exactly match the current policy entry path"
            elif entry.get("cleanup_mode") == "aged-children":
                allowed_children = {
                    item["path"]: item.get("canonical_path", item["path"])
                    for item in entry.get("cleanup_candidates", [])
                }
                if path_raw not in allowed_children:
                    reason = "aged-child target is not part of the current cleanup candidate set"
                elif allowed_children[path_raw] != str(canonical_target):
                    reason = "aged-child target canonical path no longer matches current cleanup candidate set"
            elif entry.get("cleanup_mode") == "named-descendants":
                allowed_children = {
                    item["path"]: item.get("canonical_path", item["path"])
                    for item in entry.get("cleanup_candidates", [])
                }
                if path_raw not in allowed_children:
                    reason = "named-descendant target is not part of the current cleanup candidate set"
                elif allowed_children[path_raw] != str(canonical_target):
                    reason = "named-descendant target canonical path no longer matches current cleanup candidate set"
            else:
                reason = f"cleanup mode is not apply-eligible: {entry.get('cleanup_mode')}"

            if not reason:
                if entry["layer"] == "repo_internal":
                    if not is_within(canonical_target, repo_root_resolved):
                        reason = "repo-internal target escapes repo root"
                elif entry["layer"] == "repo_external_related":
                    allowed_prefixes = build_allowed_external_prefixes(entry=entry)
                    if not any(is_within(canonical_target, prefix) or canonical_target == prefix for prefix in allowed_prefixes):
                        reason = "repo-external target escapes explicit external allowlist"
                else:
                    reason = f"layer is not apply-eligible: {entry['layer']}"
            if not reason:
                verification_commands = target.get(
                    "post_cleanup_verification_commands",
                    entry.get("post_cleanup_verification_commands", []),
                )
                if any(not bool(item.get("available", False)) for item in verification_commands):
                    reason = "post-cleanup verification commands are unavailable"

        if reason:
            rejected_targets.append(
                {
                    "entry_id": entry_id,
                    "path": path_raw,
                    "revalidation_reason": reason,
                }
            )
            continue

        validated_targets.append(
            {
                "entry_id": entry_id,
                "path": path_raw,
                "canonical_path": str(canonical_target),
                "target_kind": str(target.get("target_kind", "")),
                "size_bytes": int(target.get("size_bytes", 0)),
                "expected_reclaim_bytes": int(target.get("expected_reclaim_bytes", target.get("size_bytes", 0))),
                "classification": str(target.get("classification", entry.get("recommendation", "needs_verification"))),
                "rebuild_entrypoints": target.get(
                    "rebuild_entrypoints",
                    entry.get("required_rebuild_commands", []),
                ),
                "post_cleanup_verification_commands": target.get(
                    "post_cleanup_verification_commands",
                    entry.get("post_cleanup_verification_commands", []),
                ),
                "apply_serial_only": bool(target.get("apply_serial_only", entry.get("apply_serial_only", False))),
            }
        )

    return {
        "wave": wave,
        "gate_errors": [],
        "validated_targets": validated_targets,
        "rejected_targets": rejected_targets,
    }


def annotate_summary_membership(*, entries: list[dict[str, Any]]) -> None:
    ambiguous_paths: set[str] = set()
    entries_by_canonical: dict[str, set[str]] = {}
    rollup_roots: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        canonical = str(entry.get("canonical_path", entry.get("resolved_path", entry.get("path", ""))))
        layer_bucket = canonical_summary_bucket(str(entry.get("layer", "")))
        entries_by_canonical.setdefault(canonical, set()).add(layer_bucket)
        if str(entry.get("summary_role", "leaf")) == "rollup_root":
            rollup_roots.setdefault(layer_bucket, []).append(entry)
    for canonical, buckets in entries_by_canonical.items():
        if len({bucket for bucket in buckets if bucket != "needs_verification"}) > 1:
            ambiguous_paths.add(canonical)

    buckets: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in SUMMARY_BUCKETS}
    for entry in entries:
        canonical = str(entry.get("canonical_path", entry.get("resolved_path", entry.get("path", ""))))
        bucket = canonical_summary_bucket(str(entry.get("layer", "")))
        if canonical in ambiguous_paths or entry.get("shared_realpath_escape", False):
            bucket = "needs_verification"
        entry["summary_bucket"] = bucket
        entry["counted_in_summary"] = False
        entry["summary_exclusion_reason"] = "not-counted-yet"
        entry["exclusive_rollup_parent_id"] = find_rollup_parent_id(entry=entry, rollup_roots=rollup_roots, bucket=bucket)
        buckets[bucket].append(entry)

    for bucket_name, bucket_entries in buckets.items():
        effective_paths: list[Path] = []
        sortable_entries = sorted(
            bucket_entries,
            key=lambda entry: (
                summary_priority(str(entry.get("summary_role", "leaf"))),
                len(summary_path(entry).parts),
                str(entry.get("canonical_path", entry.get("path", ""))),
            ),
        )
        for entry in sortable_entries:
            if entry.get("summary_role", "leaf") == "breakdown_only":
                entry["summary_exclusion_reason"] = "breakdown-only"
                continue
            if int(entry.get("size_bytes", 0)) <= 0:
                entry["summary_exclusion_reason"] = "empty"
                continue
            current_path = summary_path(entry)
            if any(paths_overlap(current_path, existing) for existing in effective_paths):
                entry["summary_exclusion_reason"] = "overlap-deduped"
                continue
            entry["counted_in_summary"] = True
            entry["summary_exclusion_reason"] = ""
            effective_paths.append(current_path)


def find_rollup_parent_id(*, entry: dict[str, Any], rollup_roots: dict[str, list[dict[str, Any]]], bucket: str) -> str:
    if str(entry.get("summary_role", "leaf")) == "rollup_root":
        return ""
    current_path = summary_path(entry)
    for candidate in sorted(
        rollup_roots.get(bucket, []),
        key=lambda item: len(summary_path(item).parts),
    ):
        candidate_path = summary_path(candidate)
        if current_path == candidate_path:
            continue
        if is_within(current_path, candidate_path):
            return str(candidate.get("id", ""))
    return ""


def canonical_summary_bucket(layer_name: str) -> str:
    return SUMMARY_BUCKET_ALIASES.get(layer_name, layer_name)


def parse_iso_datetime(raw_value: str) -> datetime | None:
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return None


def policy_hash(policy: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_allowed_external_prefixes(*, entry: dict[str, Any]) -> list[Path]:
    prefixes = [summary_path(entry)]
    if entry.get("path_is_symlink") and entry.get("resolved_path"):
        prefixes.append(Path(str(entry["resolved_path"])))
    return dedupe_paths(prefixes)


def dedupe_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        raw = str(path)
        if raw in seen:
            continue
        seen.add(raw)
        result.append(path)
    return result
