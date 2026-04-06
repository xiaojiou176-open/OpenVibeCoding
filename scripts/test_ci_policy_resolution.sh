#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_SCRIPT="$ROOT_DIR/scripts/resolve_ci_pm_chat_env.sh"
SHADOW_RESOLVER="$ROOT_DIR/scripts/resolve_ci_policy.py"
declare -a TMP_DIRS=()

register_tmpdir() {
  local tmpdir="$1"
  [[ -z "$tmpdir" ]] && return 0
  TMP_DIRS+=("$tmpdir")
}

cleanup_tmpdirs() {
  local tmpdir
  for tmpdir in "${TMP_DIRS[@]-}"; do
    [[ -d "$tmpdir" ]] || continue
    rm -rf "$tmpdir"
  done
}

mktemp_dir() {
  local tmpdir
  local tmp_root="${RUNNER_TEMP:-$ROOT_DIR/.runtime-cache/cache/tmp}"
  mkdir -p "$tmp_root"
  tmpdir="$(TMPDIR="$tmp_root" command mktemp -d)"
  register_tmpdir "$tmpdir"
  printf '%s\n' "$tmpdir"
}

trap cleanup_tmpdirs EXIT INT TERM

info() {
  echo "🔎 [ci-policy-test] $*"
}

fail() {
  echo "❌ [ci-policy-test] $*" >&2
  exit 1
}

must_fail() {
  if "$@"; then
    fail "expected failure but command passed: $*"
  fi
}

assert_contains() {
  local output="$1"
  local expected="$2"
  if [[ "$output" != *"$expected"* ]]; then
    echo "----- output -----" >&2
    echo "$output" >&2
    echo "------------------" >&2
    fail "expected line missing: $expected"
  fi
}

run_case() {
  local tmp_home
  local tmp_env_root
  tmp_home="$(mktemp_dir)"
  tmp_env_root="$tmp_home/.cortexpilot-env"
  mkdir -p "$tmp_env_root"
  env -i \
    PATH="$PATH" \
    HOME="$tmp_home" \
    CORTEXPILOT_DEFAULT_ENV_ROOT="$tmp_env_root" \
    LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" \
    CORTEXPILOT_CI_PM_CHAT_DISABLE_CODEX_CONFIG=1 \
    CORTEXPILOT_CI_PM_CHAT_DISABLE_ZSH_ENV=1 \
    CORTEXPILOT_CI_PM_CHAT_DISABLE_DOTENV=1 \
    "$@" \
    bash "$TARGET_SCRIPT"
}

info "case: CI defaults to real/agents/prod and requires key when missing"
out="$(run_case CI=1)"
assert_contains "$out" "PM_CHAT_MODE=real"
assert_contains "$out" "PM_CHAT_RUNNER=agents"
assert_contains "$out" "PM_CHAT_WEB_MODE=prod"
assert_contains "$out" "PM_CHAT_REQUIRES_KEY=1"

info "case: local missing key defaults to mock and does not require key"
out="$(run_case)"
assert_contains "$out" "PM_CHAT_MODE=mock"
assert_contains "$out" "PM_CHAT_RUNNER=agents"
assert_contains "$out" "PM_CHAT_WEB_MODE=prod"
assert_contains "$out" "PM_CHAT_REQUIRES_KEY=0"

info "case: explicit mode=real with GEMINI key does not require key gate"
out="$(run_case CORTEXPILOT_CI_PM_CHAT_MODE=real GEMINI_API_KEY=dummy-gemini-key)"
assert_contains "$out" "PM_CHAT_MODE=real"
assert_contains "$out" "PM_CHAT_REQUIRES_KEY=0"

info "case: explicit mode=real with OPENAI key does not require key gate"
out="$(run_case CORTEXPILOT_CI_PM_CHAT_MODE=real OPENAI_API_KEY=dummy-openai-key)"
assert_contains "$out" "PM_CHAT_MODE=real"
assert_contains "$out" "PM_CHAT_REQUIRES_KEY=0"

info "case: explicit mode=real with ANTHROPIC key does not require key gate"
out="$(run_case CORTEXPILOT_CI_PM_CHAT_MODE=real ANTHROPIC_API_KEY=dummy-anthropic-key)"
assert_contains "$out" "PM_CHAT_MODE=real"
assert_contains "$out" "PM_CHAT_REQUIRES_KEY=0"

info "case: runtime_options.provider allowed and exported"
out="$(run_case CORTEXPILOT_CI_PM_CHAT_RUNTIME_OPTIONS_PROVIDER=gemini)"
assert_contains "$out" "PM_CHAT_PROVIDER=gemini"
assert_contains "$out" "PM_CHAT_RUNTIME_OPTIONS_PROVIDER=gemini"

info "case: CI PM-chat provider-group keys are ignored after alias removal"
out="$(run_case \
  CORTEXPILOT_CI_PM_CHAT_PROVIDER_GROUP_PROVIDER=openai \
  CORTEXPILOT_CI_PM_CHAT_PROVIDER_GROUP_RUNTIME_OPTIONS_PROVIDER=openai \
  CORTEXPILOT_CI_PM_CHAT_PROVIDER_GROUP_BASE_URL=https://api.openai.com/v1 \
  CORTEXPILOT_CI_PM_CHAT_PROVIDER_GROUP_MODEL=gpt-4o-mini)"
assert_contains "$out" "PM_CHAT_PROVIDER=''"
assert_contains "$out" "PM_CHAT_RUNTIME_OPTIONS_PROVIDER=''"
assert_contains "$out" "PM_CHAT_CODEX_BASE_URL=''"
assert_contains "$out" "PM_CHAT_CODEX_MODEL=''"

info "case: E2E provider-group keys are ignored after alias removal"
out="$(run_case \
  CORTEXPILOT_E2E_PROVIDER_GROUP_PROVIDER=gemini \
  CORTEXPILOT_E2E_PROVIDER_GROUP_RUNTIME_OPTIONS_PROVIDER=gemini \
  CORTEXPILOT_E2E_PROVIDER_GROUP_BASE_URL=https://generativelanguage.googleapis.com/v1beta \
  CORTEXPILOT_E2E_PROVIDER_GROUP_MODEL=gemini-2.5-flash)"
assert_contains "$out" "PM_CHAT_PROVIDER=''"
assert_contains "$out" "PM_CHAT_RUNTIME_OPTIONS_PROVIDER=''"
assert_contains "$out" "PM_CHAT_CODEX_BASE_URL=''"
assert_contains "$out" "PM_CHAT_CODEX_MODEL=''"

info "case: custom runtime_options.provider with explicit base_url is allowed"
out="$(run_case CORTEXPILOT_CI_PM_CHAT_RUNTIME_OPTIONS_PROVIDER=cliproxyapi CORTEXPILOT_CI_PM_CHAT_BASE_URL=https://gateway.local/v1)"
assert_contains "$out" "PM_CHAT_PROVIDER=cliproxyapi"
assert_contains "$out" "PM_CHAT_RUNTIME_OPTIONS_PROVIDER=cliproxyapi"

info "case: explicit mode=real with unrelated key still requires key gate"
out="$(run_case CORTEXPILOT_CI_PM_CHAT_MODE=real CORTEXPILOT_EQUILIBRIUM_API_KEY=dummy-equilibrium-key)"
assert_contains "$out" "PM_CHAT_MODE=real"
assert_contains "$out" "PM_CHAT_REQUIRES_KEY=1"

info "case: explicit mode=real without key requires key gate"
out="$(run_case CORTEXPILOT_CI_PM_CHAT_MODE=real)"
assert_contains "$out" "PM_CHAT_MODE=real"
assert_contains "$out" "PM_CHAT_REQUIRES_KEY=1"

info "case: explicit allow-missing-key bypasses key requirement"
out="$(run_case CORTEXPILOT_CI_PM_CHAT_MODE=real CORTEXPILOT_CI_PM_CHAT_ALLOW_MISSING_KEY=1)"
assert_contains "$out" "PM_CHAT_MODE=real"
assert_contains "$out" "PM_CHAT_REQUIRES_KEY=0"

info "case: explicit overrides for runner and web mode are preserved"
out="$(run_case CORTEXPILOT_CI_PM_CHAT_MODE=mock CORTEXPILOT_CI_PM_CHAT_RUNNER=codex CORTEXPILOT_CI_PM_CHAT_WEB_MODE=dev)"
assert_contains "$out" "PM_CHAT_MODE=mock"
assert_contains "$out" "PM_CHAT_RUNNER=codex"
assert_contains "$out" "PM_CHAT_WEB_MODE=dev"

info "case: codex config provider token is accepted as llm credential"
tmpdir="$(mktemp_dir)"
cat >"$tmpdir/config.toml" <<'TOML'
model_provider = "gemini"
model = "gemini-2.5-flash"
[model_providers.gemini]
base_url = "https://generativelanguage.googleapis.com/v1beta"
experimental_bearer_token = "local-proxy-token"
TOML
out="$(env -i PATH="$PATH" HOME="${HOME:-/tmp}" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" CORTEXPILOT_CI_PM_CHAT_DISABLE_ZSH_ENV=1 CORTEXPILOT_CI_PM_CHAT_DISABLE_DOTENV=1 CORTEXPILOT_CODEX_CONFIG_PATH="$tmpdir/config.toml" bash "$TARGET_SCRIPT")"
assert_contains "$out" "PM_CHAT_MODE=real"
assert_contains "$out" "PM_CHAT_REQUIRES_KEY=0"
assert_contains "$out" "PM_CHAT_USE_CODEX_CONFIG=1"
assert_contains "$out" "PM_CHAT_CODEX_BASE_URL=https://generativelanguage.googleapis.com/v1beta"
assert_contains "$out" "PM_CHAT_CODEX_PROVIDER=gemini"
assert_contains "$out" "PM_CHAT_CODEX_MODEL=gemini-2.5-flash"
assert_contains "$out" "PM_CHAT_CODEX_KEY_SOURCE=inline"
rm -rf "$tmpdir"

info "case: codex config token supports \${ENV_VAR} indirection"
tmpdir="$(mktemp_dir)"
cat >"$tmpdir/config.toml" <<'TOML'
model_provider = "openai"
model = "gemini-2.5-flash"
[model_providers.openai]
base_url = "https://api.openai.com/v1"
experimental_bearer_token = "${LOCAL_PROXY_TOKEN}"
TOML
out="$(env -i PATH="$PATH" HOME="${HOME:-/tmp}" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" CORTEXPILOT_CI_PM_CHAT_DISABLE_ZSH_ENV=1 CORTEXPILOT_CI_PM_CHAT_DISABLE_DOTENV=1 CORTEXPILOT_CODEX_CONFIG_PATH="$tmpdir/config.toml" LOCAL_PROXY_TOKEN=proxy-token-from-env bash "$TARGET_SCRIPT")"
assert_contains "$out" "PM_CHAT_MODE=real"
assert_contains "$out" "PM_CHAT_REQUIRES_KEY=0"
assert_contains "$out" "PM_CHAT_USE_CODEX_CONFIG=1"
assert_contains "$out" "PM_CHAT_CODEX_PROVIDER=openai"
assert_contains "$out" "PM_CHAT_CODEX_KEY_SOURCE=env:LOCAL_PROXY_TOKEN"
rm -rf "$tmpdir"

info "case: disable codex config forces missing-key mock fallback in local mode"
tmpdir="$(mktemp_dir)"
cat >"$tmpdir/config.toml" <<'TOML'
model_provider = "anthropic"
[model_providers.anthropic]
base_url = "https://api.anthropic.com/v1"
experimental_bearer_token = "token-should-be-ignored-when-disabled"
TOML
out="$(env -i PATH="$PATH" HOME="${HOME:-/tmp}" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" CORTEXPILOT_CI_PM_CHAT_DISABLE_ZSH_ENV=1 CORTEXPILOT_CI_PM_CHAT_DISABLE_DOTENV=1 CORTEXPILOT_CODEX_CONFIG_PATH="$tmpdir/config.toml" CORTEXPILOT_CI_PM_CHAT_DISABLE_CODEX_CONFIG=1 bash "$TARGET_SCRIPT")"
assert_contains "$out" "PM_CHAT_MODE=mock"
assert_contains "$out" "PM_CHAT_REQUIRES_KEY=0"
assert_contains "$out" "PM_CHAT_USE_CODEX_CONFIG=0"
rm -rf "$tmpdir"

info "case: env/codex provider mismatch fail-closed"
tmpdir="$(mktemp_dir)"
cat >"$tmpdir/config.toml" <<'TOML'
model_provider = "gemini"
model = "gemini-2.5-flash"
[model_providers.gemini]
base_url = "https://generativelanguage.googleapis.com/v1beta"
TOML
must_fail env -i PATH="$PATH" HOME="${HOME:-/tmp}" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" CORTEXPILOT_CI_PM_CHAT_DISABLE_ZSH_ENV=1 CORTEXPILOT_CI_PM_CHAT_DISABLE_DOTENV=1 CORTEXPILOT_CODEX_CONFIG_PATH="$tmpdir/config.toml" CORTEXPILOT_CI_PM_CHAT_PROVIDER=openai bash "$TARGET_SCRIPT" >/dev/null
rm -rf "$tmpdir"

info "case: env/codex base_url mismatch fail-closed"
tmpdir="$(mktemp_dir)"
cat >"$tmpdir/config.toml" <<'TOML'
model_provider = "openai"
model = "gpt-4o-mini"
[model_providers.openai]
base_url = "https://api.openai.com/v1"
TOML
must_fail env -i PATH="$PATH" HOME="${HOME:-/tmp}" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" CORTEXPILOT_CI_PM_CHAT_DISABLE_ZSH_ENV=1 CORTEXPILOT_CI_PM_CHAT_DISABLE_DOTENV=1 CORTEXPILOT_CODEX_CONFIG_PATH="$tmpdir/config.toml" CORTEXPILOT_CI_PM_CHAT_PROVIDER=openai CORTEXPILOT_CI_PM_CHAT_BASE_URL="https://api.openai.com/v1/alt" bash "$TARGET_SCRIPT" >/dev/null
rm -rf "$tmpdir"

info "case: env/codex model mismatch fail-closed"
tmpdir="$(mktemp_dir)"
cat >"$tmpdir/config.toml" <<'TOML'
model_provider = "anthropic"
model = "claude-3-7-sonnet-latest"
[model_providers.anthropic]
base_url = "https://api.anthropic.com/v1"
TOML
must_fail env -i PATH="$PATH" HOME="${HOME:-/tmp}" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" CORTEXPILOT_CI_PM_CHAT_DISABLE_ZSH_ENV=1 CORTEXPILOT_CI_PM_CHAT_DISABLE_DOTENV=1 CORTEXPILOT_CODEX_CONFIG_PATH="$tmpdir/config.toml" CORTEXPILOT_CI_PM_CHAT_PROVIDER=anthropic CORTEXPILOT_CI_PM_CHAT_MODEL="claude-3-5-sonnet-latest" bash "$TARGET_SCRIPT" >/dev/null
rm -rf "$tmpdir"

info "case: custom runtime_options.provider without base_url fail-closed"
must_fail run_case CORTEXPILOT_CI_PM_CHAT_RUNTIME_OPTIONS_PROVIDER=cliproxyapi >/dev/null

info "case: runtime_options.provider mismatches env provider fail-closed"
must_fail run_case CORTEXPILOT_CI_PM_CHAT_PROVIDER=openai CORTEXPILOT_CI_PM_CHAT_RUNTIME_OPTIONS_PROVIDER=gemini >/dev/null

info "case: runtime_options.provider mismatches codex provider fail-closed"
tmpdir="$(mktemp_dir)"
cat >"$tmpdir/config.toml" <<'TOML'
model_provider = "anthropic"
model = "claude-3-7-sonnet-latest"
[model_providers.anthropic]
base_url = "https://api.anthropic.com/v1"
TOML
must_fail env -i PATH="$PATH" HOME="${HOME:-/tmp}" LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" CORTEXPILOT_CI_PM_CHAT_DISABLE_ZSH_ENV=1 CORTEXPILOT_CI_PM_CHAT_DISABLE_DOTENV=1 CORTEXPILOT_CODEX_CONFIG_PATH="$tmpdir/config.toml" CORTEXPILOT_CI_PM_CHAT_RUNTIME_OPTIONS_PROVIDER=openai bash "$TARGET_SCRIPT" >/dev/null
rm -rf "$tmpdir"

info "case: lower-priority provider env is shadowed by higher-priority provider env"
must_fail run_case CORTEXPILOT_CI_PM_CHAT_PROVIDER=gemini CORTEXPILOT_PROVIDER=openai >/dev/null

info "case: provider-group alias cannot shadow canonical provider"
out="$(run_case \
  CORTEXPILOT_CI_PM_CHAT_PROVIDER=gemini \
  CORTEXPILOT_CI_PM_CHAT_RUNTIME_OPTIONS_PROVIDER=gemini \
  CORTEXPILOT_CI_PM_CHAT_PROVIDER_GROUP_PROVIDER=openai)"
assert_contains "$out" "PM_CHAT_PROVIDER=gemini"
assert_contains "$out" "PM_CHAT_RUNTIME_OPTIONS_PROVIDER=gemini"

info "case: lower-priority model env is shadowed by higher-priority model env"
must_fail run_case CORTEXPILOT_CI_PM_CHAT_MODEL=gemini-2.5-flash CORTEXPILOT_MODEL=gpt-4o-mini >/dev/null

info "case: lower-priority base_url env is shadowed by higher-priority base_url env"
must_fail run_case CORTEXPILOT_CI_PM_CHAT_BASE_URL=https://gateway.primary/v1 CORTEXPILOT_E2E_CODEX_BASE_URL=https://gateway.shadow/v1 >/dev/null

info "case: shadow resolver writes default snapshot with expected schema"
snapshot_path="$ROOT_DIR/.runtime-cache/test_output/ci/ci_policy_snapshot.json"
rm -f "$snapshot_path"
python3 "$SHADOW_RESOLVER" >/dev/null
if [[ ! -f "$snapshot_path" ]]; then
  fail "shadow resolver did not write snapshot: $snapshot_path"
fi
python3 - <<'PY' "$snapshot_path"
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
data = json.loads(p.read_text(encoding="utf-8"))
if data.get("profile") != "pr":
    raise SystemExit(f"expected profile=pr, got {data.get('profile')!r}")
if data.get("mode") != "shadow":
    raise SystemExit(f"expected mode=shadow, got {data.get('mode')!r}")
if "source_map" not in data or not isinstance(data["source_map"], dict):
    raise SystemExit("missing source_map object")
PY

info "case: shadow resolver merge order core < profile < advanced.overrides and source_map"
tmpdir="$(mktemp_dir)"
custom_core="$tmpdir/ci_policy.core.json"
custom_profile="$tmpdir/ci_policy.profiles.json"
custom_advanced="$tmpdir/ci_policy.advanced.json"
custom_out="$tmpdir/snapshot.json"
cat >"$custom_core" <<'JSON'
{
  "metadata": {
    "name": "ci_policy_core",
    "version": "1.0.0",
    "layer": "core",
    "schema": "schemas/ci_policy.schema.json"
  },
  "audit": {
    "enabled": true
  },
  "core": {
    "gates": {
      "ui_regression_flake": true
    },
    "execution": {},
    "defaults": {},
    "pm_chat": {
      "runner": "agents",
      "web_mode": "prod",
      "mode_on_ci": "core-mode",
      "mode_local_without_key": "mock",
      "allow_mock_on_ci": false,
      "allow_missing_key": false
    }
  }
}
JSON
cat >"$custom_profile" <<'JSON'
{
  "metadata": {
    "name": "ci_policy_profiles",
    "version": "1.0.0",
    "layer": "profile",
    "schema": "schemas/ci_policy.schema.json"
  },
  "audit": {
    "enabled": true
  },
  "profile": {
    "default": "pr",
    "profiles": {
      "pr": {
        "ui_flake": {
          "p0_iterations": 8,
          "p1_iterations": 8,
          "p0_threshold_percent": 0.5,
          "p1_threshold_percent": 1.0
        },
        "ui_truth": {
          "p0_min_iterations": 8,
          "p1_min_iterations": 8,
          "p0_max_threshold_percent": 0.5,
          "p1_max_threshold_percent": 1.0
        }
      },
      "nightly": {
        "ui_flake": {
          "p0_iterations": 20,
          "p1_iterations": 20,
          "p0_threshold_percent": 0.4,
          "p1_threshold_percent": 0.8
        },
        "ui_truth": {
          "p0_min_iterations": 10,
          "p1_min_iterations": 12,
          "p0_max_threshold_percent": 0.4,
          "p1_max_threshold_percent": 0.8
        }
      },
      "weekly": {
        "ui_flake": {
          "p0_iterations": 50,
          "p1_iterations": 50,
          "p0_threshold_percent": 0.5,
          "p1_threshold_percent": 1.0
        },
        "ui_truth": {
          "p0_min_iterations": 8,
          "p1_min_iterations": 8,
          "p0_max_threshold_percent": 0.5,
          "p1_max_threshold_percent": 1.0
        }
      }
    }
  }
}
JSON
cat >"$custom_advanced" <<'JSON'
{
  "metadata": {
    "name": "ci_policy_advanced",
    "version": "1.0.0",
    "layer": "advanced",
    "schema": "schemas/ci_policy.schema.json"
  },
  "audit": {
    "enabled": true
  },
  "advanced": {
    "fail_closed": {
      "gate_skip_requires_break_glass": true
    },
    "overrides": {
      "CORTEXPILOT_CI_PM_CHAT_MODE": "advanced-final",
      "CORTEXPILOT_CI_SAMPLE_BREAK_GLASS": "1"
    },
    "break_glass": {
      "ci_gate": {
        "switch": "CORTEXPILOT_CI_SAMPLE_BREAK_GLASS",
        "reason": "",
        "ticket": "OPS-123"
      }
    }
  }
}
JSON
CORTEXPILOT_CI_POLICY_CORE_CONFIG="$custom_core" \
CORTEXPILOT_CI_POLICY_PROFILE_CONFIG="$custom_profile" \
CORTEXPILOT_CI_POLICY_ADVANCED_CONFIG="$custom_advanced" \
python3 "$SHADOW_RESOLVER" --profile nightly --output-json "$custom_out" >/dev/null
python3 - <<'PY' "$custom_out"
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
data = json.loads(p.read_text(encoding="utf-8"))
env = data["resolved_env"]
src = data["source_map"]
warns = data["warnings"]
assert env["CORTEXPILOT_CI_PM_CHAT_MODE"] == "advanced-final", env
assert env["CORTEXPILOT_CI_UI_FLAKE_P0_ITER"] == "20", env
assert env["CORTEXPILOT_CI_UI_TRUTH_P1_MIN_ITERATIONS"] == "12", env
assert src["CORTEXPILOT_CI_PM_CHAT_MODE"] == "advanced.overrides", src
assert src["CORTEXPILOT_CI_UI_FLAKE_P0_ITER"] == "profile:nightly", src
assert src["CORTEXPILOT_CI_PM_CHAT_RUNNER"] == "core", src
assert any("CORTEXPILOT_CI_SAMPLE_BREAK_GLASS_REASON" in w for w in warns), warns
assert any("advanced.break_glass.ci_gate.reason" in w for w in warns), warns
PY

info "case: shadow resolver --emit-env outputs resolved env lines"
emit_out="$(CORTEXPILOT_CI_POLICY_CORE_CONFIG="$custom_core" CORTEXPILOT_CI_POLICY_PROFILE_CONFIG="$custom_profile" CORTEXPILOT_CI_POLICY_ADVANCED_CONFIG="$custom_advanced" python3 "$SHADOW_RESOLVER" --profile nightly --output-json "$custom_out" --emit-env)"
assert_contains "$emit_out" "CORTEXPILOT_CI_PM_CHAT_MODE=advanced-final"
assert_contains "$emit_out" "CORTEXPILOT_CI_UI_FLAKE_P0_ITER=20"
assert_contains "$emit_out" "CORTEXPILOT_CI_UI_TRUTH_P1_MIN_ITERATIONS=12"
rm -rf "$tmpdir"

info "case: shadow resolver validates advanced.break_glass required_fields/scopes/template shape"
tmpdir="$(mktemp_dir)"
custom_core="$tmpdir/ci_policy.core.json"
custom_profile="$tmpdir/ci_policy.profiles.json"
custom_advanced="$tmpdir/ci_policy.advanced.json"
custom_out="$tmpdir/snapshot.json"
cat >"$custom_core" <<'JSON'
{
  "core": {
    "pm_chat": {
      "mode_on_ci": "real"
    }
  }
}
JSON
cat >"$custom_profile" <<'JSON'
{
  "profile": {
    "profiles": {
      "pr": {}
    }
  }
}
JSON
cat >"$custom_advanced" <<'JSON'
{
  "advanced": {
    "break_glass": {
      "template": {
        "enabled": "yes",
        "reason": 1,
        "ticket": 2,
        "expires_on": 3
      },
      "required_fields": ["ticket"],
      "scopes": ["", "ci"]
    }
  }
}
JSON
python3 - <<'PY' "$custom_core" "$custom_profile" "$custom_advanced" "$custom_out"
import json
import pathlib
import subprocess
import sys

core, profile, advanced, out = sys.argv[1:]
cmd = [
    "python3",
    "scripts/resolve_ci_policy.py",
    "--output-json",
    out,
]
env = {
    "PATH": str(pathlib.Path("/usr/bin")) + ":" + str(pathlib.Path("/bin")) + ":" + str(pathlib.Path("/usr/sbin")) + ":" + str(pathlib.Path("/sbin")),
    "CORTEXPILOT_CI_POLICY_CORE_CONFIG": core,
    "CORTEXPILOT_CI_POLICY_PROFILE_CONFIG": profile,
    "CORTEXPILOT_CI_POLICY_ADVANCED_CONFIG": advanced,
}
result = subprocess.run(cmd, capture_output=True, text=True, env=env, check=True)
stderr = result.stderr
required = [
    "advanced.break_glass.template.enabled must be boolean",
    "advanced.break_glass.template.reason must be string",
    "advanced.break_glass.template.ticket must be string",
    "advanced.break_glass.template.expires_on must be string",
    "advanced.break_glass.required_fields should include reason/ticket",
    "advanced.break_glass.scopes must contain non-empty strings",
]
for item in required:
    if item not in stderr:
        raise SystemExit(f"missing warning: {item}\nstderr={stderr}")
data = json.loads(pathlib.Path(out).read_text(encoding="utf-8"))
warnings = data.get("warnings", [])
for item in required:
    if not any(item in w for w in warnings):
        raise SystemExit(f"missing snapshot warning: {item}\nwarnings={warnings}")
PY
rm -rf "$tmpdir"

info "case: shadow resolver normalizes advanced overrides scalars and null"
tmpdir="$(mktemp_dir)"
custom_core="$tmpdir/ci_policy.core.json"
custom_profile="$tmpdir/ci_policy.profiles.json"
custom_advanced="$tmpdir/ci_policy.advanced.json"
custom_out="$tmpdir/snapshot.json"
cat >"$custom_core" <<'JSON'
{
  "core": {}
}
JSON
cat >"$custom_profile" <<'JSON'
{
  "profile": {
    "profiles": {
      "pr": {}
    }
  }
}
JSON
cat >"$custom_advanced" <<'JSON'
{
  "advanced": {
    "overrides": {
      "CORTEXPILOT_SAMPLE_NULL": null,
      "CORTEXPILOT_SAMPLE_BOOL": true,
      "CORTEXPILOT_SAMPLE_INT": 7,
      "CORTEXPILOT_SAMPLE_FLOAT": 0.5
    }
  }
}
JSON
CORTEXPILOT_CI_POLICY_CORE_CONFIG="$custom_core" \
CORTEXPILOT_CI_POLICY_PROFILE_CONFIG="$custom_profile" \
CORTEXPILOT_CI_POLICY_ADVANCED_CONFIG="$custom_advanced" \
python3 "$SHADOW_RESOLVER" --output-json "$custom_out" --emit-env >/dev/null
python3 - <<'PY' "$custom_out"
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
data = json.loads(p.read_text(encoding="utf-8"))
env = data["resolved_env"]
src = data["source_map"]
assert env["CORTEXPILOT_SAMPLE_NULL"] == "", env
assert env["CORTEXPILOT_SAMPLE_BOOL"] == "True", env
assert env["CORTEXPILOT_SAMPLE_INT"] == "7", env
assert env["CORTEXPILOT_SAMPLE_FLOAT"] == "0.5", env
assert src["CORTEXPILOT_SAMPLE_NULL"] == "advanced.overrides", src
assert src["CORTEXPILOT_SAMPLE_BOOL"] == "advanced.overrides", src
assert src["CORTEXPILOT_SAMPLE_INT"] == "advanced.overrides", src
assert src["CORTEXPILOT_SAMPLE_FLOAT"] == "advanced.overrides", src
PY
rm -rf "$tmpdir"

info "case: env governance gate rejects deprecated ratio > 1"
must_fail python3 "$ROOT_DIR/scripts/check_env_governance.py" --mode gate --max-deprecated-ratio 1.01 >/dev/null

info "case: env governance report rejects deprecated ratio > 1"
tmpdir="$(mktemp_dir)"
must_fail python3 "$ROOT_DIR/scripts/report_env_governance.py" --output-dir "$tmpdir" --max-deprecated-ratio 1.01 >/dev/null
rm -rf "$tmpdir"

info "case: env governance gate/report reject deprecated ratio < 0"
must_fail python3 "$ROOT_DIR/scripts/check_env_governance.py" --mode gate --max-deprecated-ratio -0.01 >/dev/null
tmpdir="$(mktemp_dir)"
must_fail python3 "$ROOT_DIR/scripts/report_env_governance.py" --output-dir "$tmpdir" --max-deprecated-ratio -0.01 >/dev/null
rm -rf "$tmpdir"

info "case: env governance gate/report accept deprecated ratio boundary = 1"
python3 "$ROOT_DIR/scripts/check_env_governance.py" --mode warn --max-deprecated-count 99999 --max-deprecated-ratio 1 >/dev/null
tmpdir="$(mktemp_dir)"
python3 "$ROOT_DIR/scripts/report_env_governance.py" --output-dir "$tmpdir" --max-deprecated-count 99999 --max-deprecated-ratio 1 >/dev/null
rm -rf "$tmpdir"

info "case: ci env governance budgets are centralized and shared by report+gate steps"
ci_text="$(cat "$ROOT_DIR/scripts/ci.sh")"
assert_contains "$ci_text" "ENV_GOV_MAX_DEPRECATED_COUNT"
assert_contains "$ci_text" "ENV_GOV_MAX_DEPRECATED_RATIO"
assert_contains "$ci_text" "--max-deprecated-count \"\${ENV_GOV_MAX_DEPRECATED_COUNT}\""
assert_contains "$ci_text" "--max-deprecated-ratio \"\${ENV_GOV_MAX_DEPRECATED_RATIO}\""

info "case: env governance convergence_status=merged suppresses timeout mergeable/deletable candidates"
tmpdir="$(mktemp_dir)"
registry_json="$tmpdir/registry.json"
tiers_json="$tmpdir/tiers.json"
cat >"$registry_json" <<'JSON'
[
  {
    "name": "CORTEXPILOT_CI_STEP8_4_TIMEOUT_SEC",
    "consumers": ["scripts/ci.sh"]
  },
  {
    "name": "CORTEXPILOT_CI_STEP8_4_INVENTORY_TIMEOUT_SEC",
    "consumers": ["scripts/ci.sh"],
    "convergence_target": "CORTEXPILOT_CI_STEP8_4_TIMEOUT_SEC",
    "convergence_status": "merged"
  }
]
JSON
cat >"$tiers_json" <<'JSON'
{
  "default_tier": "core",
  "prefix_rules": [],
  "overrides": {
    "CORTEXPILOT_CI_STEP8_4_TIMEOUT_SEC": "core",
    "CORTEXPILOT_CI_STEP8_4_INVENTORY_TIMEOUT_SEC": "advanced"
  }
}
JSON
python3 "$ROOT_DIR/scripts/report_env_governance.py" \
  --registry "$registry_json" \
  --tiers-config "$tiers_json" \
  --output-dir "$tmpdir" >/dev/null
python3 - <<'PY' "$tmpdir/report.json"
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
conv = report["metrics"]["convergence_candidates"]
assert conv["mergeable_count"] == 0, conv
assert conv["deletable_count"] == 0, conv
PY
rm -rf "$tmpdir"

info "case: env governance convergence_status=planned keeps timeout leaf as mergeable+deletable candidate"
tmpdir="$(mktemp_dir)"
registry_json="$tmpdir/registry.json"
tiers_json="$tmpdir/tiers.json"
cat >"$registry_json" <<'JSON'
[
  {
    "name": "CORTEXPILOT_CI_STEP8_4_TIMEOUT_SEC",
    "consumers": ["scripts/ci.sh"]
  },
  {
    "name": "CORTEXPILOT_CI_STEP8_4_INVENTORY_TIMEOUT_SEC",
    "consumers": ["scripts/ci.sh"],
    "convergence_target": "CORTEXPILOT_CI_STEP8_4_TIMEOUT_SEC",
    "convergence_status": "planned"
  }
]
JSON
cat >"$tiers_json" <<'JSON'
{
  "default_tier": "core",
  "prefix_rules": [],
  "overrides": {
    "CORTEXPILOT_CI_STEP8_4_TIMEOUT_SEC": "core",
    "CORTEXPILOT_CI_STEP8_4_INVENTORY_TIMEOUT_SEC": "advanced"
  }
}
JSON
python3 "$ROOT_DIR/scripts/report_env_governance.py" \
  --registry "$registry_json" \
  --tiers-config "$tiers_json" \
  --output-dir "$tmpdir" >/dev/null
python3 - <<'PY' "$tmpdir/report.json"
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
conv = report["metrics"]["convergence_candidates"]
assert conv["mergeable_count"] == 1, conv
assert conv["deletable_count"] == 1, conv
item = conv["mergeable_keys"][0]
assert item["name"] == "CORTEXPILOT_CI_STEP8_4_INVENTORY_TIMEOUT_SEC", item
assert item["target_group_key"] == "CORTEXPILOT_CI_STEP8_4_TIMEOUT_SEC", item
PY
rm -rf "$tmpdir"

info "all ci policy resolution cases passed"
