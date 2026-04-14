#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${OPENVIBECODING_SECURITY_SCAN_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "$ROOT_DIR"
source "${SCRIPT_DIR}/lib/release_tool_helpers.sh"

echo "🔐 [security] start secret scanning"

is_truthy() {
  case "${1:-}" in
    1 | true | TRUE | yes | YES | y | Y | on | ON)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_mainline_context() {
  if is_truthy "${CI:-0}"; then
    return 0
  fi
  if [[ "${OPENVIBECODING_CI_PROFILE:-}" == "strict" ]]; then
    return 0
  fi
  if [[ "${GITHUB_REF_NAME:-}" == "main" || "${GITHUB_BASE_REF:-}" == "main" ]]; then
    return 0
  fi
  return 1
}

make_temp_report_file() {
  # BSD mktemp only expands the placeholder when the X suffix is at the end.
  # Keep the content-type hint before the random suffix so temp reports stay
  # easy to inspect without breaking macOS/BSD compatibility.
  mktemp "${TMPDIR:-/tmp}/$1.XXXXXX"
}

require_scanner_default="0"
if is_mainline_context; then
  require_scanner_default="1"
fi
REQUIRE_SCANNER="${OPENVIBECODING_SECURITY_REQUIRE_SCANNER:-$require_scanner_default}"

TRUFFLEHOG_BIN=""
if command -v trufflehog >/dev/null 2>&1; then
  TRUFFLEHOG_BIN="$(command -v trufflehog)"
else
  TRUFFLEHOG_BIN="$(openvibecoding_trufflehog_bin "$ROOT_DIR" 2>/dev/null || true)"
fi

if [[ -n "$TRUFFLEHOG_BIN" && -x "$TRUFFLEHOG_BIN" ]]; then
  echo "🚀 [security] scanning git history with trufflehog"
  tmp_output="$(make_temp_report_file openvibecoding-trufflehog.jsonl)"
  filtered_output="$(make_temp_report_file openvibecoding-trufflehog.filtered.jsonl)"
  cleanup_tmp_output() {
    rm -f "$tmp_output"
    rm -f "$filtered_output"
  }
  trap cleanup_tmp_output EXIT
  set +e
  "$TRUFFLEHOG_BIN" git "file://$ROOT_DIR" \
    --json \
    --results=verified,unknown,unverified \
    --filter-unverified \
    --fail-on-scan-errors \
    >"$tmp_output"
  trufflehog_status=$?
  set -e
  if [[ $trufflehog_status -ne 0 ]]; then
    echo "❌ [security] trufflehog scan failed (exit=$trufflehog_status)" >&2
    cat "$tmp_output" >&2 || true
    exit "$trufflehog_status"
  fi
  ignored_count="$(
    python3 - "$tmp_output" "$filtered_output" <<'PY'
import json
import pathlib
import sys
from urllib.parse import urlsplit

source = pathlib.Path(sys.argv[1])
dest = pathlib.Path(sys.argv[2])


def is_placeholder_example_uri(raw: str) -> bool:
    parsed = urlsplit(raw)
    return (
        parsed.scheme == "https"
        and parsed.username == "user"
        and parsed.password == "pass"
        and parsed.hostname == "example.com"
        and parsed.port is None
    )


def is_allowed(record: dict) -> bool:
    if record.get("Verified") is True:
        return False

    git_meta = (
        record.get("SourceMetadata", {})
        .get("Data", {})
        .get("Git", {})
    )
    path = git_meta.get("file", "")
    detector = record.get("DetectorName", "")
    raw = record.get("RawV2") or record.get("Raw") or ""

    if (
        path == "apps/orchestrator/tests/test_e2e_external_web_probe.py"
        and detector == "URI"
        and is_placeholder_example_uri(raw)
    ):
        return True

    if (
        path == "scripts/security_scan.sh"
        and detector == "URI"
        and is_placeholder_example_uri(raw)
    ):
        return True

    if (
        path == "scripts/README.md"
        and detector == "URI"
        and is_placeholder_example_uri(raw)
    ):
        return True

    if (
        path in {
            "infra/docker/langfuse/.env.example",
            "infra/docker/langfuse/docker-compose.yml",
            "infra/docker/langfuse/README.md",
        }
        and detector == "Postgres"
        and raw.startswith("postgresql://postgres:")
        and "@postgres:5432" in raw
    ):
        return True

    return False


ignored = 0
kept: list[str] = []
for line in source.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    record = json.loads(line)
    if is_allowed(record):
        ignored += 1
        continue
    kept.append(line)

dest.write_text(("".join(f"{line}\n" for line in kept)), encoding="utf-8")
print(ignored)
PY
  )"
  if [[ "$ignored_count" != "0" ]]; then
    echo "ℹ️ [security] ignored ${ignored_count} known synthetic placeholder findings from test/example git history"
  fi
  if [[ -s "$filtered_output" ]]; then
    echo "❌ [security] trufflehog findings detected:" >&2
    cat "$filtered_output" >&2
    exit 1
  fi
  echo "✅ [security] trufflehog scan passed"
  exit 0
fi

GITLEAKS_BIN=""
if command -v gitleaks >/dev/null 2>&1; then
  GITLEAKS_BIN="$(command -v gitleaks)"
else
  GITLEAKS_BIN="$(openvibecoding_gitleaks_bin "$ROOT_DIR" 2>/dev/null || true)"
fi

if [[ -n "$GITLEAKS_BIN" && -x "$GITLEAKS_BIN" ]]; then
  echo "🚀 [security] scanning git repository with gitleaks"
  "$GITLEAKS_BIN" git "$ROOT_DIR" --redact --verbose -c "$ROOT_DIR/.gitleaks.toml"
  echo "✅ [security] gitleaks scan passed"
  exit 0
fi

echo "⚠️ [security] trufflehog/gitleaks not found, using built-in regex gate"

if [[ "$REQUIRE_SCANNER" == "1" ]]; then
  echo "❌ [security] OPENVIBECODING_SECURITY_REQUIRE_SCANNER=1 but trufflehog/gitleaks is unavailable" >&2
  exit 1
fi

PATTERN_1='sk-[A-Za-z0-9]{24,}'
PATTERN_2='(?i)bearer[[:space:]]+[A-Za-z0-9._\-]{24,}'
PATTERN_3='(?i)(api[_-]?key|token|secret|password)[[:space:]]*[:=][[:space:]]*["'"''][A-Za-z0-9._\-]{16,}["'"'']'

matches="$({
  rg -n --hidden --no-messages -g '!**/.git/**' -g '!**/.venv/**' -g '!**/node_modules/**' -g '!**/.runtime-cache/**' -g '!**/*.lock' -g '!**/pnpm-lock.yaml' -e "$PATTERN_1" . || true
  rg -n --hidden --no-messages -g '!**/.git/**' -g '!**/.venv/**' -g '!**/node_modules/**' -g '!**/.runtime-cache/**' -g '!**/*.lock' -g '!**/pnpm-lock.yaml' -e "$PATTERN_2" . || true
  rg -n --hidden --no-messages -g '!**/.git/**' -g '!**/.venv/**' -g '!**/node_modules/**' -g '!**/.runtime-cache/**' -g '!**/*.lock' -g '!**/pnpm-lock.yaml' -e "$PATTERN_3" . || true
} | sort -u)"

if [[ -n "$matches" ]]; then
  echo "❌ [security] suspected sensitive data found; remediate immediately:" >&2
  echo "$matches" >&2
  exit 1
fi

echo "✅ [security] built-in secret scan passed"
