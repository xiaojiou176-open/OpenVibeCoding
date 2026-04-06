#!/usr/bin/env bash
set -euo pipefail

codex_config_path="${CORTEXPILOT_CODEX_CONFIG_PATH:-$HOME/.codex/config.toml}"
PYTHON_BIN="${CORTEXPILOT_PROVIDER_HARDCUT_PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    PYTHON_BIN=""
  fi
fi

violations=()
provider_sources=()
base_url_sources=()
model_sources=()

normalize_provider() {
  local raw="${1:-}"
  printf '%s' "$raw" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]'
}

normalize_base_url() {
  local raw="${1:-}"
  local trimmed="${raw%"${raw##*[![:space:]]}"}"
  trimmed="${trimmed#"${trimmed%%[![:space:]]*}"}"
  while [[ "$trimmed" == */ ]]; do
    trimmed="${trimmed%/}"
  done
  printf '%s' "$trimmed"
}

normalize_model() {
  local raw="${1:-}"
  local trimmed="${raw%"${raw##*[![:space:]]}"}"
  trimmed="${trimmed#"${trimmed%%[![:space:]]*}"}"
  printf '%s' "$trimmed"
}

is_known_provider() {
  local normalized
  normalized="$(normalize_provider "$1")"
  [[ "$normalized" == "gemini" || "$normalized" == "openai" || "$normalized" == "anthropic" ]]
}

append_unique_source() {
  local target_name="$1"
  local value="$2"
  local source="$3"
  eval "local target_len=\${#$target_name[@]}"
  local i
  for (( i=0; i<target_len; i+=2 )); do
    eval "local current_value=\${$target_name[$i]}"
    if [[ "$current_value" == "$value" ]]; then
      eval "$target_name[$((i+1))]=\${$target_name[$((i+1))]},\${source}"
      return 0
    fi
  done
  eval "$target_name+=(\"\$value\" \"\$source\")"
}

check_provider_env_var() {
  local var_name="$1"
  local value="${!var_name:-}"
  if [[ -z "$value" ]]; then
    return 0
  fi
  local normalized
  normalized="$(normalize_provider "$value")"
  append_unique_source provider_sources "$normalized" "$var_name"
}

check_base_url_env_var() {
  local var_name="$1"
  local value="${!var_name:-}"
  if [[ -z "$value" ]]; then
    return 0
  fi
  append_unique_source base_url_sources "$(normalize_base_url "$value")" "$var_name"
}

check_model_env_var() {
  local var_name="$1"
  local value="${!var_name:-}"
  if [[ -z "$value" ]]; then
    return 0
  fi
  append_unique_source model_sources "$(normalize_model "$value")" "$var_name"
}

check_consistency_or_fail() {
  local dim_name="$1"
  local dim_ref_name="$2"
  eval "local dim_len=\${#$dim_ref_name[@]}"
  if (( dim_len <= 2 )); then
    return 0
  fi
  violations+=("${dim_name} conflict detected")
  local i
  for (( i=0; i<dim_len; i+=2 )); do
    eval "local conflict_value=\${$dim_ref_name[$i]}"
    eval "local conflict_sources=\${$dim_ref_name[$((i+1))]}"
    violations+=("  - ${dim_name}=${conflict_value} from ${conflict_sources}")
  done
}

check_provider_env_var "CORTEXPILOT_E2E_CODEX_PROVIDER"
check_provider_env_var "CORTEXPILOT_CI_PM_CHAT_PROVIDER"
check_provider_env_var "CORTEXPILOT_CI_PM_CHAT_RUNTIME_OPTIONS_PROVIDER"
check_provider_env_var "CORTEXPILOT_CI_DEFAULT_PROVIDER"
check_provider_env_var "CORTEXPILOT_MODEL_PROVIDER"
check_provider_env_var "PM_CHAT_CODEX_PROVIDER"
check_provider_env_var "PM_CHAT_RUNTIME_OPTIONS_PROVIDER"
check_provider_env_var "CORTEXPILOT_RUNTIME_OPTIONS_PROVIDER"
check_provider_env_var "CORTEXPILOT_PROVIDER"

check_base_url_env_var "CORTEXPILOT_E2E_CODEX_BASE_URL"
check_base_url_env_var "CORTEXPILOT_CI_PM_CHAT_BASE_URL"
check_base_url_env_var "CORTEXPILOT_CI_DEFAULT_BASE_URL"
check_base_url_env_var "CORTEXPILOT_MODEL_BASE_URL"
check_base_url_env_var "PM_CHAT_CODEX_BASE_URL"

check_model_env_var "CORTEXPILOT_E2E_CODEX_MODEL"
check_model_env_var "CORTEXPILOT_CI_PM_CHAT_MODEL"
check_model_env_var "CORTEXPILOT_CI_DEFAULT_MODEL"
check_model_env_var "CORTEXPILOT_MODEL_NAME"
check_model_env_var "CORTEXPILOT_MODEL"
check_model_env_var "PM_CHAT_CODEX_MODEL"

if [[ "${CORTEXPILOT_PROVIDER_HARDCUT_SKIP_CODEX_CONFIG:-0}" != "1" ]] && [[ -n "$PYTHON_BIN" ]] && [[ -f "$codex_config_path" ]]; then
  eval "$("$PYTHON_BIN" - "$codex_config_path" <<'PY'
import pathlib
import shlex
import sys

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py<3.11 fallback
    try:
        import tomli as tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        tomllib = None

path = pathlib.Path(sys.argv[1])
def parse_fallback_toml(raw: str) -> dict:
    # Minimal parser for the keys used by this gate:
    # model_provider/model and [model_providers.<name>] base_url/model.
    data: dict = {}
    providers: dict = {}
    current_section = ""
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].strip()
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.split("#", 1)[0].strip()
        if len(value) >= 2 and (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        ):
            value = value[1:-1]
        if current_section == "":
            if key in {"model_provider", "model"}:
                data[key] = value
            continue
        if current_section.startswith("model_providers."):
            provider_name = current_section.split(".", 1)[1].strip()
            if not provider_name:
                continue
            provider_entry = providers.setdefault(provider_name, {})
            if key in {"base_url", "model"}:
                provider_entry[key] = value
    if providers:
        data["model_providers"] = providers
    return data

try:
    raw_text = path.read_text(encoding="utf-8")
    if tomllib is not None:
        data = tomllib.loads(raw_text)
    else:
        data = parse_fallback_toml(raw_text)
except Exception:
    print("codex_cfg_provider=''")
    print("codex_cfg_base_url=''")
    print("codex_cfg_model=''")
    raise SystemExit(0)

provider_name = str(data.get("model_provider") or "").strip()
providers = data.get("model_providers") if isinstance(data.get("model_providers"), dict) else {}
provider = providers.get(provider_name) if isinstance(providers, dict) else {}
provider = provider if isinstance(provider, dict) else {}
base_url = str(provider.get("base_url") or "").strip()
model_name = str(data.get("model") or provider.get("model") or "").strip()

print(f"codex_cfg_provider={shlex.quote(provider_name)}")
print(f"codex_cfg_base_url={shlex.quote(base_url)}")
print(f"codex_cfg_model={shlex.quote(model_name)}")
PY
  )"

  if [[ -n "${codex_cfg_provider:-}" ]]; then
    local_provider="$(normalize_provider "$codex_cfg_provider")"
    append_unique_source provider_sources "$local_provider" "codex:${codex_config_path}"
  fi
  if [[ -n "${codex_cfg_base_url:-}" ]]; then
    append_unique_source base_url_sources "$(normalize_base_url "$codex_cfg_base_url")" "codex:${codex_config_path}"
  fi
  if [[ -n "${codex_cfg_model:-}" ]]; then
    append_unique_source model_sources "$(normalize_model "$codex_cfg_model")" "codex:${codex_config_path}"
  fi
fi

check_consistency_or_fail "provider" provider_sources
check_consistency_or_fail "base_url" base_url_sources
check_consistency_or_fail "model" model_sources

# Custom provider is allowed, but it must be paired with an explicit base_url
# so OpenAI-compatible routing remains deterministic and auditable.
if (( ${#provider_sources[@]} >= 2 )); then
  provider_candidate="${provider_sources[0]}"
  if ! is_known_provider "$provider_candidate" && (( ${#base_url_sources[@]} == 0 )); then
    violations+=("custom provider '${provider_candidate}' requires explicit base_url (env or codex config)")
  fi
fi

if (( ${#violations[@]} > 0 )); then
  echo "❌ [provider-hardcut] blocked: provider legality/consistency check failed"
  for item in "${violations[@]}"; do
    echo " - ${item}"
  done
  echo "💡 [provider-hardcut] provider may be custom, but env/codex/runtime_options must stay consistent; custom provider requires explicit base_url"
  exit 1
fi

echo "✅ [provider-hardcut] pass: provider legality/consistency check passed"
