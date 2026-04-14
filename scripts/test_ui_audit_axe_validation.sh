#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

info() {
  echo "🔎 [ui-audit-axe-test] $*"
}

fail() {
  echo "❌ [ui-audit-axe-test] $*" >&2
  exit 1
}

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

valid_a="$tmpdir/valid_dashboard_axe.json"
valid_b="$tmpdir/valid_desktop_axe.json"
invalid_payload="$tmpdir/invalid_axe.json"
violating_payload="$tmpdir/violating_axe.json"

cat >"$valid_a" <<'JSON'
[
  {
    "url": "http://127.0.0.1:3211/command-tower",
    "violations": [],
    "passes": [],
    "incomplete": [],
    "inapplicable": []
  }
]
JSON

cat >"$valid_b" <<'JSON'
[
  {
    "url": "http://127.0.0.1:4311/",
    "violations": [],
    "passes": [],
    "incomplete": [],
    "inapplicable": []
  }
]
JSON

cat >"$invalid_payload" <<'JSON'
[
  {
    "violations": [],
    "passes": [],
    "incomplete": [],
    "inapplicable": []
  }
]
JSON

cat >"$violating_payload" <<'JSON'
[
  {
    "url": "http://127.0.0.1:3211/command-tower",
    "violations": [{"id": "color-contrast"}],
    "passes": [],
    "incomplete": [],
    "inapplicable": []
  }
]
JSON

verify_axe_payloads() {
  local max_violations="$1"
  shift
  OPENVIBECODING_UI_AUDIT_AXE_MAX_VIOLATIONS="$max_violations" node -e '
const fs = require("node:fs");
const maxViolations = Number(process.env.OPENVIBECODING_UI_AUDIT_AXE_MAX_VIOLATIONS ?? "0");
if (!Number.isFinite(maxViolations) || maxViolations < 0) {
  console.error("invalid max violations");
  process.exit(1);
}
let totalViolations = 0;
for (const reportPath of process.argv.slice(1)) {
  if (!fs.existsSync(reportPath)) {
    console.error(`missing: ${reportPath}`);
    process.exit(1);
  }
  const content = fs.readFileSync(reportPath, "utf8").trim();
  if (!content) {
    console.error(`empty: ${reportPath}`);
    process.exit(1);
  }
  const parsed = JSON.parse(content);
  const results = Array.isArray(parsed) ? parsed : [parsed];
  if (
    results.length === 0 ||
    !results.every(
      (entry) =>
        entry &&
        typeof entry.url === "string" &&
        Array.isArray(entry.violations) &&
        Array.isArray(entry.passes) &&
        Array.isArray(entry.incomplete) &&
        Array.isArray(entry.inapplicable),
    )
  ) {
    console.error(`invalid payload: ${reportPath}`);
    process.exit(1);
  }
  totalViolations += results.reduce((acc, entry) => acc + entry.violations.length, 0);
}
if (totalViolations > maxViolations) {
  console.error(`violations exceeded: ${totalViolations} > ${maxViolations}`);
  process.exit(1);
}
' "$@"
}

info "case: valid axe payloads should pass"
verify_axe_payloads 0 "$valid_a" "$valid_b"

info "case: invalid axe payload should fail"
if verify_axe_payloads 0 "$invalid_payload" >/dev/null 2>&1; then
  fail "invalid axe payload unexpectedly passed"
fi

info "case: violations over threshold should fail"
if verify_axe_payloads 0 "$violating_payload" >/dev/null 2>&1; then
  fail "violating axe payload unexpectedly passed"
fi

info "all axe validation cases passed"
