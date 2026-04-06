# Task Packs

`contracts/packs/` is the source-of-truth workspace for task-pack manifests.

These manifests do not replace runtime run truth. They define:

- which task templates are officially registered
- which input fields the operator surface must render for each pack
- which intake surface group they belong to
- which primary report the pack is expected to emit
- whether the pack expects search or browser request artifacts

Runtime execution must never write back into `contracts/packs/`.

## Current public packs

- `news_digest`: topic + sources + time range + max results, primary report `news_digest_result.json`
- `topic_brief`: topic + time range + max results, primary report `topic_brief_result.json`
- `page_brief`: page URL + focus, primary report `page_brief_result.json`

The Dashboard PM workspace and the desktop first-session bootstrap both read
these pack manifests as registry metadata. The runtime still validates and
derives objective/search behavior inside the orchestrator; `contracts/packs/`
is source-owned intake metadata, not runtime output.
