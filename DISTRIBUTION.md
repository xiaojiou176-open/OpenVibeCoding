# CortexPilot Distribution Contract

This file is the canonical human-readable source for CortexPilot's current
official distribution story.

The public GitHub Pages mirror for this contract lives at
`docs/distribution/index.html`.

If README, Pages, examples, package metadata, or release notes ever appear to
say different things, this file wins and the drift should be fixed in the next
change set.

## One-sentence story

Today CortexPilot officially ships a public repo front door, a GitHub Pages
product front door, one proof-first public workflow baseline, a repo-local
read-only MCP server, a published PyPI package, a live Official MCP Registry
entry, and a live ClawHub skill.

It does not yet officially ship a hosted operator service, a public write-capable
MCP, a Docker distribution path, or standalone npm releases. OpenHands/extensions
and MCP.so submissions are filed, but they still depend on external review or
intake handling rather than repo-only publication.

Lane order today is:

1. `pure_mcp`
2. `pure_skills`
3. local starter/example bundle materials

## Status labels

- `shipped`: part of the official public distribution today
- `starter-only`: intentionally copy-paste or local-install material, not a
  registry item
- `bundle-compatible`: installable from a local path or local marketplace-like
  surface, but still not a published listing
- `submitted-externally`: the repo has filed the platform submission and holds a
  public receipt, but the host has not finished acceptance yet
- `publish-ready but deferred`: metadata and package contract are ready for a
  future public package release, but no registry release is live yet
- `not standalone distribution unit`: useful repo-owned surface, but not meant
  to be marketed or released on its own today
- `deferred`: real later-phase direction, but not part of current official
  distribution
- `not part of current official distribution`: out of scope for the current
  public story

## Current Distribution Matrix

| Surface | Current status | Official claim | Install path | Protocol / Auth | Next action |
| --- | --- | --- | --- | --- | --- |
| GitHub repo | `shipped` | Canonical public source, docs, code, and release front door | `https://github.com/xiaojiou176-open/CortexPilot-public` | none | keep sharp and truthful |
| GitHub Pages | `shipped` | Canonical public product front door | `https://xiaojiou176-open.github.io/CortexPilot-public/` | none | keep first screen compressed |
| First proven workflow (`news_digest`) | `shipped` | Official public proof-first baseline | `docs/use-cases/index.html` and tracked proof assets | read-only proof / replay story | keep as the only release-proven public workflow |
| Read-only MCP | `shipped` | Repo-owned stdio JSON-RPC MCP for machine-readable inspection only | bootstrapped repo checkout + `bash __CORTEXPILOT_REPO_ROOT__/scripts/run_readonly_mcp.sh` or the tracked starter templates | `stdio`, JSON-RPC 2.0, read-only, repo-local, no hosted auth, no OAuth | keep artifactized through `configs/mcp_public_manifest.json` |
| PyPI package (`cortexpilot-orchestrator`) | `shipped` | Published package for the public read-only MCP runtime | `https://pypi.org/project/cortexpilot-orchestrator/0.1.0a4/` | package install only | keep package README, entrypoints, and version markers aligned with registry truth |
| Official MCP Registry entry | `shipped` | Public MCP discovery entry for the read-only CortexPilot server | `https://registry.modelcontextprotocol.io/v0/servers?search=io.github.xiaojiou176-open/cortexpilot-readonly` | registry discovery only, stdio package install | keep `server.json` aligned with PyPI and the public MCP docs |
| Codex starter | `starter-only` | Local marketplace seed plus shared read-only MCP template | `examples/coding-agents/codex/` | local path wiring only | keep truthful; do not relabel as official directory listing |
| Claude Code starter | `starter-only` | Project-local `.claude` and `.mcp.json` starter | `examples/coding-agents/claude-code/` | local project wiring only | keep truthful; do not relabel as marketplace package |
| OpenClaw starter | `starter-only` | Local config seed for the same read-only MCP and compatible bundle | `examples/coding-agents/openclaw/` | local config + local plugin path | keep truthful; do not relabel as ClawHub publication |
| Cross-tool coding-agent bundle | `bundle-compatible` | Local bundle compatible with Codex local marketplace installs, Claude plugin-dir development, and OpenClaw local plugin loading | `examples/coding-agents/plugin-bundles/cortexpilot-coding-agent-bundle/` | local bundle metadata + repo-aware MCP wrapper | keep local-install contract; no published listing claim |
| Repo-owned adoption-router skill | `shipped` | Cross-tool routing skill with `SKILL.md` + `manifest.yaml`, shared between the public skill packet, the repo bundle, and external skill distribution | `public-skills/cortexpilot-adoption-router/` | repo-owned skill contract, public skill packet plus local bundle example | keep the public packet, repo bundle, and published skill receipts aligned |
| ClawHub skill (`cortexpilot-adoption-router`) | `shipped` | Published OpenClaw skill for honest CortexPilot adoption routing | `https://www.clawhub.ai/skills/cortexpilot-adoption-router` | skill registry, no hosted CortexPilot account, no write-capable MCP | keep the skill copy aligned with the repo bundle and public boundary |
| OpenHands/extensions submission | `submitted-externally` | Public skill submission receipt for the same adoption-router artifact | `https://github.com/OpenHands/extensions/pull/151` | host review flow, not live until merged | track review without overclaiming a merged listing |
| MCP.so submission | `submitted-externally` | Directory submission for the public read-only MCP server | `https://github.com/chatmcp/mcpso/issues/1559` | directory intake flow, not live until accepted | keep the issue body aligned with current package + registry truth |
| `@cortexpilot/frontend-api-client` | `publish-ready but deferred` | Thin JS/TS client for control-plane reads and guarded operator add-ons | package metadata + README are publish-ready, but the official install story is still clone / vendor reuse until the first npm release exists | HTTP API with token / mutation-role expectations | publish later only after the first public package release is intentionally cut |
| `@cortexpilot/frontend-api-contract` | `publish-ready but deferred` | Generated route / query / type boundary for frontend consumers | package metadata + README are publish-ready, but the official install story is still clone / vendor reuse until the first npm release exists | typed contract layer only | publish later only after the first public package release is intentionally cut |
| `@cortexpilot/frontend-shared` | `not standalone distribution unit` | Repo-owned presentation substrate for dashboard / desktop / future web surfaces | repo-local package only | frontend presentation helpers only | keep repo-owned for now |
| Docker image / Dockerfile | `deferred` | No official container distribution today; existing Dockerfiles are CI-only infrastructure | none | n/a | add only when a real container story exists |
| Hosted Render pilot | `deferred` | Repo-side pilot blueprint exists, but no live hosted operator claim | `render.yaml` + runbook only | hosted HTTP / token boundary remains later | keep truthful; no live hosted claim |
| Write-capable MCP | `not part of current official distribution` | Public MCP is still read-only | none | owner-only preview groundwork exists separately | keep gated and out of public claim |

## Version And Release Truth

- The latest live GitHub release is `v0.1.0-alpha.3`.
- `v0.1.0-alpha.3` is the current published prerelease baseline, but it is no
  longer the current `main` snapshot.
- The latest published public package for the read-only MCP is
  `cortexpilot-orchestrator==0.1.0a4`.
- The latest Official MCP Registry entry points to
  `io.github.xiaojiou176-open/cortexpilot-readonly@0.1.0a4`.
- `v0.1.0-alpha.1` remains the historical first public baseline, not the latest
  release truth.
- README, Pages, and manifest surfaces must keep explicit lag wording whenever
  the published release tag trails `main`.

## Canonical MCP Truth

- Human-readable MCP quickstart: `docs/mcp/index.html`
- Machine-readable MCP distribution manifest: `configs/mcp_public_manifest.json`
- Public mirror of this contract: `docs/distribution/index.html`
- Implementation: `apps/orchestrator/src/cortexpilot_orch/mcp_readonly_server.py`
- Canonical startup wrapper: `scripts/run_readonly_mcp.sh`
- Canonical starter template: `examples/coding-agents/mcp/readonly.mcp.json.example`
- Root `DISTRIBUTION.md` stays authoritative; the public mirror at
  `docs/distribution/index.html` must match it and route readers back here

## External / Owner-only Actions Left Out On Purpose

These are intentionally outside repo-side completion:

- publish npm packages
- wait for OpenHands/extensions review on PR `#151`
- wait for MCP.so intake handling on issue `#1559`
- publish a Docker image
- deploy a live hosted operator service
- promote a public write-capable MCP

Those actions require external platform writes or owner decisions and are not
part of the current official shipped contract.
