from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cortexpilot_orch.contract.validator import ContractValidator
from cortexpilot_orch.store.run_store import RunStore


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _extract_user_request(contract: dict[str, Any]) -> str:
    inputs = contract.get("inputs")
    if isinstance(inputs, dict):
        spec = inputs.get("spec")
        if isinstance(spec, str) and spec.strip():
            return spec.strip()
    return ""


def hash_events(path: Path) -> str:
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


def collect_evidence_hashes(run_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}

    def _add(path: Path) -> None:
        if not path.exists():
            return
        rel = path.relative_to(run_dir).as_posix()
        if rel == "events.jsonl":
            hashes[rel] = hash_events(path)
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


def build_evidence_report(run_dir: Path, extra_required: list[str] | None = None) -> dict[str, Any]:
    required = [
        "contract.json",
        "events.jsonl",
        "patch.diff",
        "reports/task_result.json",
        "reports/test_report.json",
        "reports/review_report.json",
    ]
    if extra_required:
        required.extend(extra_required)
    missing = [key for key in required if not (run_dir / key).exists()]
    return {"status": "ok" if not missing else "fail", "missing": missing}


def placeholder_evidence_bundle(contract: dict[str, Any], reason: str) -> dict[str, Any]:
    raw_question = _extract_user_request(contract) or "missing spec"
    refined_prompt = raw_question
    requested_by = contract.get("assigned_agent", {}) if isinstance(contract, dict) else {}
    role = str(requested_by.get("role") or "").strip()
    agent_id = str(requested_by.get("agent_id") or "").strip()
    if role not in {"PM", "TECH_LEAD", "SEARCHER", "ORCHESTRATOR"}:
        role = "ORCHESTRATOR"
    if not agent_id:
        agent_id = "orchestrator"
    source = {
        "source_id": "src-0",
        "kind": "other",
        "title": reason,
        "retrieved_at": _now_ts(),
        "content_sha256": _sha256_text(reason),
    }
    claim = {
        "claim_id": "claim-0",
        "text": reason,
        "status": "UNVERIFIED",
        "confidence": 0.0,
        "supporting_source_ids": ["src-0"],
        "contradicting_source_ids": [],
        "verification_notes": "auto-generated placeholder",
        "risk_if_wrong": "LOW",
    }
    return {
        "bundle_id": uuid.uuid4().hex,
        "created_at": _now_ts(),
        "requested_by": {"role": role, "agent_id": agent_id},
        "query": {"raw_question": raw_question, "refined_prompt": refined_prompt},
        "sources": [source],
        "claims": [claim],
        "limitations": [reason],
    }


def ensure_evidence_bundle_placeholder(store: RunStore, run_id: str, contract: dict[str, Any], reason: str) -> None:
    run_dir_getter = getattr(store, "run_dir", None)
    if callable(run_dir_getter):
        run_dir = run_dir_getter(run_id)
    else:
        run_dir = store._run_dir(run_id)  # type: ignore[attr-defined]

    bundle_path = run_dir / "reports" / "evidence_bundle.json"
    if bundle_path.exists():
        return

    bundle = placeholder_evidence_bundle(contract, reason)
    validator = ContractValidator()
    try:
        validator.validate_report(bundle, "evidence_bundle.v1.json")
        store.write_report(run_id, "evidence_bundle", bundle)
    except Exception:  # noqa: BLE001
        store.write_report(run_id, "evidence_bundle", bundle)
