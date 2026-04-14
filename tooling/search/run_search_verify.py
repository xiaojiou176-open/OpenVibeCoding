from __future__ import annotations

import argparse
import json
import re
import sys
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ORCH_SRC = ROOT / "apps" / "orchestrator" / "src"
if str(ORCH_SRC) not in sys.path:
    sys.path.append(str(ORCH_SRC))

from tooling.search.search_engine import search_verify
from tooling.search_pipeline import write_search_results, write_verification, write_purified_summary
from openvibecoding_orch.store.run_store import RunStore

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run search + verification and record artifacts.")
    parser.add_argument("--run-id", required=True, help="Run ID to record artifacts")
    parser.add_argument("--query", action="append", required=True, help="Query string")
    parser.add_argument("--provider", action="append", help="Search provider name")
    parser.add_argument("--repeat", type=int, default=2, help="Repeat each query N times")
    parser.add_argument("--parallel", type=int, default=2, help="Parallel worker count")
    parser.add_argument("--verify-provider", action="append", help="Verification provider name")
    parser.add_argument("--verify-repeat", type=int, default=1, help="Repeat verification runs")
    return parser.parse_args()


def _require_safe_run_id(run_id: str) -> str:
    normalized = run_id.strip()
    if not normalized:
        raise SystemExit("run_id must not be empty")
    if not _RUN_ID_RE.fullmatch(normalized) or ".." in normalized:
        raise SystemExit("run_id contains illegal path characters")
    return normalized


def _run_one(job: tuple[str, str]) -> dict[str, Any]:
    query, provider = job
    return search_verify(query, provider=provider)


def _safe_slug(value: str) -> str:
    if not value:
        return "item"
    cleaned: list[str] = []
    for ch in value:
        if ch.isalnum() or ch in {"-", "_"}:
            cleaned.append(ch)
        else:
            cleaned.append("_")
    slug = "".join(cleaned).strip("_")
    return slug[:40] or "item"


def _sync_search_artifacts(store: RunStore, run_id: str, query: str, provider: str, result: dict[str, Any]) -> dict[str, Any]:
    meta = result.get("meta")
    if not isinstance(meta, dict):
        return result
    artifacts = meta.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        return result
    store._ensure_bundle(run_id)
    task_key = f"search_{_safe_slug(provider)}_{_safe_slug(query)}"
    dest_dir = store._run_dir(run_id) / "artifacts" / "search" / task_key
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    for name, src in artifacts.items():
        if not src:
            continue
        try:
            src_path = Path(str(src))
            if not src_path.exists() or not src_path.is_file():
                continue
            dest_path = dest_dir / src_path.name
            shutil.copy2(src_path, dest_path)
            copied[str(name)] = str(dest_path)
        except Exception:  # noqa: BLE001
            continue
    if copied:
        meta["artifacts_original"] = artifacts
        meta["artifacts"] = copied
        meta["artifacts_root"] = str(dest_dir)
        result["meta"] = meta
    return result


def main() -> int:
    args = _parse_args()
    safe_run_id = _require_safe_run_id(args.run_id)
    queries = [q for q in args.query if q.strip()]
    if not queries:
        raise SystemExit("no queries provided")

    providers = [p for p in (args.provider or []) if p.strip()] or ["gemini_web", "grok_web"]
    tasks: list[tuple[str, str]] = []
    for query in queries:
        for provider in providers:
            for _ in range(max(1, args.repeat)):
                tasks.append((query, provider))

    store = RunStore()
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        for job, item in zip(tasks, pool.map(_run_one, tasks)):
            query, provider = job
            results.append(_sync_search_artifacts(store, safe_run_id, query=query, provider=provider, result=item))

    verify_results: list[dict[str, Any]] = []
    verify_providers = [p for p in (args.verify_provider or []) if p.strip()]
    if verify_providers:
        verify_tasks: list[tuple[str, str]] = []
        for query in queries:
            for provider in verify_providers:
                for _ in range(max(1, args.verify_repeat)):
                    verify_tasks.append((query, provider))
        with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
            for job, item in zip(verify_tasks, pool.map(_run_one, verify_tasks)):
                query, provider = job
                verify_results.append(
                    _sync_search_artifacts(store, safe_run_id, query=query, provider=provider, result=item)
                )

    verification = {
        "queries": queries,
        "runs": len(results),
        "verification_runs": len(verify_results),
        "all_consistent": all(r.get("verification", {}).get("consistent") for r in results),
    }

    write_search_results(safe_run_id, results)
    write_verification(safe_run_id, verification)
    write_purified_summary(safe_run_id, results, verification)

    print(json.dumps({"ok": True, "runs": len(results)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
