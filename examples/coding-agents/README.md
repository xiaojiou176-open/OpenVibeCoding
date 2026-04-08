# Coding-agent integration examples

These examples package the current truthful CortexPilot adoption paths for
three host ecosystems:

- Codex: local marketplace plugin bundle example plus shared read-only MCP
  config
- Claude Code: project-local `.claude/` command/agent examples plus shared
  read-only MCP config
- OpenClaw: compatible local bundle example plus shared read-only MCP config

What these examples are for:

- make repo-owned skills and read-only MCP easier to wire into real tools
- give maintainers a copy-pasteable starting point that stays below hosted,
  write-capable, or official-listing claims
- keep ecosystem reality separate from CortexPilot publication state

What these examples are not:

- not a published Codex plugin directory listing
- not a Claude Code marketplace package
- not a published OpenClaw / ClawHub item
- not a hosted operator or write-capable MCP claim

## Fastest truthful order

If you want the shortest honest path instead of reading the whole repo map,
keep the order small:

1. Prove the repo-local path first:

```bash
npm run bootstrap:host
CORTEXPILOT_HOST_COMPAT=1 bash scripts/test_quick.sh --no-related
npm run dashboard:dev
```

2. Copy exactly one host-tool starter file or one local bundle seed.
3. Keep the first host-tool integration read-only and repo-root scoped.
4. Confirm success by routing back through the public proof-first loop:
   - `docs/use-cases/index.html`
   - Workflow Cases
   - Proof & Replay
   - the tracked `news_digest` proof assets

If you skip step 1, you risk pasting a config file before you have proved the
repo-local MCP/proof path is even healthy.

## Layout

```text
examples/coding-agents/
  codex/marketplace.example.json
  claude-code/
    README.md
    project.mcp.json
    .claude/commands/cortexpilot-proof.md
    .claude/agents/cortexpilot-reviewer.md
  mcp/readonly.mcp.json.example
  openclaw/README.md
  openclaw/cortexpilot-server.json
  openclaw/config.openclaw.example.toml
  plugin-bundles/cortexpilot-coding-agent-bundle/
    .codex-plugin/plugin.json
    .claude-plugin/plugin.json
    .mcp.json
    README.md
    skills/cortexpilot-adoption-router/SKILL.md
    skills/cortexpilot-adoption-router/manifest.yaml
```

## Shared read-only MCP wiring

All three ecosystems can reuse the same MCP example after you replace the
placeholder path:

1. Copy `examples/coding-agents/mcp/readonly.mcp.json.example` to the host
   tool's MCP config location.
2. Replace `__CORTEXPILOT_REPO_ROOT__` with the absolute path to your
   CortexPilot checkout.
3. Keep the command on the truthful stdio path:

```bash
bash /absolute/path/to/CortexPilot/scripts/run_readonly_mcp.sh
```

The public MCP contract stays read-only. Queue preview/cancel and the guarded
queue-only pilot remain outside the public promise.

## Codex

Use `codex/marketplace.example.json` together with
`plugin-bundles/cortexpilot-coding-agent-bundle/` when you want the smallest
local plugin-bundle installation that ships CortexPilot skills and the same
repo-aware read-only MCP wrapper.

That bundle is intended for:

- local marketplace installs
- repo-owned or vendored skill reuse
- pairing with the shared read-only MCP example above

It is intentionally not framed as a published Codex Plugin Directory entry.
What is now true, though, is that the shared bundle already carries a
registry-shaped `manifest.yaml` for the bundled `cortexpilot-adoption-router`
skill, so the repo can treat that skill as **publish-ready but deferred**
without pretending an official Codex listing already exists.

## Claude Code

Use `claude-code/` when you want a project-local `.claude` starter or a plugin
development seed without inventing a fake marketplace story.

The example shows:

- one slash-command style playbook
- one subagent prompt
- one tracked project-local `.mcp.json`
- the shared read-only MCP config path to pair with them
- one bundle-shipped `manifest.yaml` for the shared `cortexpilot-adoption-router`
  skill

## OpenClaw

OpenClaw can consume the same compatible bundle used for the Codex local plugin
example. Start with `openclaw/README.md`, `openclaw/cortexpilot-server.json`,
and `openclaw/config.openclaw.example.toml`.

The truthful story is:

- OpenClaw has native plugin and skills surfaces
- CortexPilot currently ships a compatible local bundle example, not a
  published registry item
- that bundle now includes a registry-shaped `manifest.yaml` for the shared
  `cortexpilot-adoption-router` skill
- pair the bundle with the shared read-only MCP config and repo-owned proof /
  replay surfaces
