# Documentation

This repository keeps its public documentation intentionally small.

`docs/README.md` is the summary for the active **public docs inventory only**.
Anything outside that active inventory should be treated as
**implementation/archive reference**, not as front-door navigation.

## Repository Entry

1. [../README.md](../README.md)

## Primary Registered Docs

1. [index.html](index.html)
2. [ecosystem/index.html](ecosystem/index.html)
3. [compatibility/index.html](compatibility/index.html)
4. [distribution/index.html](distribution/index.html)
5. [agent-starters/index.html](agent-starters/index.html)
6. [use-cases/index.html](use-cases/index.html)
7. [ai-surfaces/index.html](ai-surfaces/index.html)
8. [integrations/index.html](integrations/index.html)
9. [skills/index.html](skills/index.html)
10. [mcp/index.html](mcp/index.html)
11. [api/index.html](api/index.html)
12. [builders/index.html](builders/index.html)

## Supplemental Registered Docs

1. [robots.txt](robots.txt)
2. [sitemap.xml](sitemap.xml)

## Inventory Rule

`configs/docs_nav_registry.json` is the machine source of truth for the active
public docs inventory.

This file is not the public proof router.
keep machine-readable proof ledgers in repo-owned machine paths instead of
turning `docs/README.md` into a human path toward raw proof metadata.

Keep this tree limited to:

- public route pages
- crawler surfaces
- storefront assets used by active route pages
- public API artifacts that belong to the external contract

Keep maintainer contracts, ledgers, runbooks, incident notes, scratch receipts,
and runtime evidence outside `docs/` in repo-owned internal paths such as
`.agents/` or machine-owned paths such as `configs/**` and `.runtime-cache/**`.
