# Tooling Module

## Module Responsibility
- Utility modules and adapters used by orchestrator flows (search, browser, tampermonkey, registry).

## Key Entrypoints
- `tooling/search_pipeline.py`
- `tooling/tampermonkey/`
- `tooling/mcp/`
- `tooling/registry.json`

## Maintenance Notes
- Keep tool contracts schema-aligned with orchestrator artifacts.
- Prefer deterministic outputs; avoid hidden state outside `.runtime-cache/`.
