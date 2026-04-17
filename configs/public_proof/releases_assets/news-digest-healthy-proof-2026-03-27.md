# news_digest Healthy Proof - 2026-03-27

This file records the first repo-tracked successful backend-backed
`news_digest` proof bundle for the public release path.

It supersedes the older healthy-proof route receipt, which now lives only in
the maintainer-only internal docs bundle as a historical blocker record.

This is repo-side proof only. It is not proof that a live GitHub Release has
already been published.

## Run Snapshot

- run id: `run_20260327_102651_8274cd4519324674a3ddd67506febd83`
- commit: `03b8bf9`
- generated at: `2026-03-27T10:27:20.898375+00:00`
- task template: `news_digest`
- topic: `Seattle AI`
- requested source allowlist: `theverge.com`
- max results: `3`
- pipeline result: `ok=true`, `runs=4`, `verification_runs=1`

## Tracked Proof Assets

- `docs/releases/assets/news-digest-healthy-proof-gemini-2026-03-27.png`
- `docs/releases/assets/news-digest-healthy-proof-grok-2026-03-27.png`
- `configs/public_proof/releases_assets/news-digest-healthy-proof-summary-2026-03-27.json`
- `configs/public_proof/releases_assets/news-digest-benchmark-summary-2026-03-27.md`

## Provider Outcome Summary

| Provider | Attempts | Successes | Session mode | Duration summary |
| --- | --- | --- | --- | --- |
| `gemini_web` | 2 | 2 | `allow_profile` | `9532 ms` average |
| `grok_web` | 2 | 2 | `allow_profile` | `10317-10346 ms`, `10331.5 ms` average |

## Result Summary

- `reports/news_digest_result.json` ended in `SUCCESS`
- the generated digest recorded 2 public source entries
- both required providers (`gemini_web`, `grok_web`) completed successfully
- no provider failure was recorded in the successful run

## Reproduction Command

Use a managed Python toolchain and expose an allowlisted local browser profile
through environment variables.

```bash
bash -lc 'source scripts/lib/env.sh >/dev/null 2>&1
export PYTHONPATH="$PWD/apps/orchestrator/src:$PWD"
export CORTEXPILOT_RUNTIME_ROOT="$PWD/.runtime-cache/w3-news-digest-attempt-profile-allowlist-v2"
export CORTEXPILOT_RUNS_ROOT="$CORTEXPILOT_RUNTIME_ROOT/runs"
export CORTEXPILOT_WEB_HEADLESS=1
export CORTEXPILOT_BROWSER_PROFILE_MODE=allow_profile
export CORTEXPILOT_BROWSER_PROFILE_NAME=Default
export CORTEXPILOT_BROWSER_PROFILE_DIR="<chrome-profile-root>"
export CORTEXPILOT_BROWSER_PROFILE_ALLOWLIST="<chrome-profile-root>"
"$CORTEXPILOT_PYTHON" - <<'"'"'PY'"'"'
import json
from openvibecoding_orch.store.run_store import RunStore
from openvibecoding_orch.runners.tool_runner import ToolRunner
from openvibecoding_orch.scheduler.tool_execution_pipeline import run_search_pipeline

store = RunStore()
run_id = store.create_run("w3-news-digest-profile-allowlist-v2")
request = {
    "queries": ["Seattle AI site:theverge.com"],
    "providers": ["gemini_web", "grok_web"],
    "verify": {"providers": ["gemini_web"], "repeat": 1},
    "task_template": "news_digest",
    "template_payload": {
        "topic": "Seattle AI",
        "sources": ["theverge.com"],
        "time_range": "24h",
        "max_results": 3,
    },
}
result = run_search_pipeline(
    run_id,
    ToolRunner(run_id=run_id, store=store),
    store,
    request,
    requested_by={"role": "PM", "agent_id": "pm-w3"},
)
print(json.dumps({"run_id": run_id, "result": result}, ensure_ascii=False))
PY'
```

## Copied Machine Summary

The tracked machine-readable summary lives at:

- `configs/public_proof/releases_assets/news-digest-healthy-proof-summary-2026-03-27.json`

The original runtime root was:

- `.runtime-cache/w3-news-digest-attempt-profile-allowlist-v2/runs/run_20260327_102651_8274cd4519324674a3ddd67506febd83`

That transient runtime directory was cleaned after the tracked summaries and
screenshots were copied, so repository hygiene could return to green.

## Truth Boundary

- This proof bundle was generated from a real local run, not a dry run or mock
  path.
- The repo tracks copied screenshots and a written summary, not the live GitHub
  Release page.
- The local browser profile root used by the run is intentionally not written
  into git; only the required environment variable names are documented here.
- the earlier healthy-proof route receipt remains archived in the maintainer-only
  internal docs bundle, not on the default public docs surface.
