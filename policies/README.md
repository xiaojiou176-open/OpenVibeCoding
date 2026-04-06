# Policies

Policy files define repository-level allowlists and governance constraints.

## Files

- `mcp_allowlist.json` — allowed and denied MCP tools.
- `command_allowlist.json` — allowed shell command policy.
- `packs/` — policy packs and profile-level policy bundles.

## Governance Rules

- Policy changes should be reviewed alongside matching updates in `docs/README.md` or other active public docs.
- If a policy changes behavior, update related tests and mention the change in `CHANGELOG.md`.
