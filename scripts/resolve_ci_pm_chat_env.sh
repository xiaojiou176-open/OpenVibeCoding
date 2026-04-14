#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "${OPENVIBECODING_CI_PM_CHAT_DISABLE_ZSH_ENV:-0}" == "1" ]]; then
  export OPENVIBECODING_DISABLE_ZSH_ENV_FALLBACK=1
fi
if [[ "${OPENVIBECODING_CI_PM_CHAT_DISABLE_DOTENV:-0}" == "1" && -z "${OPENVIBECODING_DEFAULT_ENV_ROOT:-}" ]]; then
  export OPENVIBECODING_DEFAULT_ENV_ROOT="${TMPDIR:-/tmp}/openvibecoding-empty-env-root"
  mkdir -p "${OPENVIBECODING_DEFAULT_ENV_ROOT}"
fi

source "$ROOT_DIR/scripts/lib/env.sh"

codex_config_path="${OPENVIBECODING_CODEX_CONFIG_PATH:-$HOME/.codex/config.toml}"
codex_cfg_base_url=""
codex_cfg_provider=""
codex_cfg_model=""
codex_cfg_has_key="0"
codex_cfg_key_source="none"
PYTHON_BIN="${OPENVIBECODING_CI_PM_CHAT_PYTHON_BIN:-}"

load_env_var_from_dotenv_if_missing() {
  local key="$1"
  if is_mainline_context; then
    return 0
  fi
  if [[ "${OPENVIBECODING_CI_PM_CHAT_DISABLE_DOTENV:-0}" == "1" ]]; then
    return 0
  fi
  if [[ -n "${!key:-}" ]]; then
    return 0
  fi
  for env_file in ".env.local" ".env"; do
    if [[ ! -f "$env_file" ]]; then
      continue
    fi
    local raw
    raw="$(awk -F= -v k="$key" '
      $0 ~ "^[[:space:]]*#" { next }
      $1 ~ "^[[:space:]]*$" { next }
      {
        lhs=$1
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", lhs)
        if (lhs == k) {
          sub(/^[^=]*=/, "", $0)
          print $0
          exit 0
        }
      }
    ' "$env_file")"
    if [[ -z "$raw" ]]; then
      continue
    fi
    raw="${raw%\"}"
    raw="${raw#\"}"
    raw="${raw%\'}"
    raw="${raw#\'}"
    export "$key=$raw"
    return 0
  done
}

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

resolve_with_precedence() {
  local normalize_fn="$1"
  shift
  local candidate_var raw normalized
  for candidate_var in "$@"; do
    raw="${!candidate_var:-}"
    normalized="$($normalize_fn "$raw")"
    if [[ -n "$normalized" ]]; then
      printf '%s\t%s\t%s\n' "$candidate_var" "$raw" "$normalized"
      return 0
    fi
  done
  printf '\t\t\n'
}

assert_no_shadowed_lower_values() {
  local field_name="$1"
  local effective_source="$2"
  local effective_value="$3"
  local normalize_fn="$4"
  shift 4
  local ordered_vars=("$@")
  local source_idx=-1
  local i
  for i in "${!ordered_vars[@]}"; do
    if [[ "${ordered_vars[$i]}" == "$effective_source" ]]; then
      source_idx="$i"
      break
    fi
  done
  if [[ "$source_idx" -lt 0 ]]; then
    return 0
  fi
  local j
  for ((j=source_idx + 1; j<${#ordered_vars[@]}; j++)); do
    local shadowed_var="${ordered_vars[$j]}"
    local shadowed_raw="${!shadowed_var:-}"
    local shadowed_norm="$($normalize_fn "$shadowed_raw")"
    if [[ -n "$shadowed_norm" && "$shadowed_norm" != "$effective_value" ]]; then
      echo "❌ [ci-policy] ${field_name} set by ${shadowed_var} (${shadowed_raw}) but overridden by ${effective_source}" >&2
      exit 1
    fi
  done
}

is_known_provider() {
  local provider_norm
  provider_norm="$(normalize_provider "$1")"
  [[ "$provider_norm" == "gemini" || "$provider_norm" == "openai" || "$provider_norm" == "anthropic" ]]
}

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -n "${OPENVIBECODING_PYTHON:-}" ]] && [[ -x "${OPENVIBECODING_PYTHON}" ]] && "${OPENVIBECODING_PYTHON}" -c "pass" >/dev/null 2>&1; then
    PYTHON_BIN="${OPENVIBECODING_PYTHON}"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    PYTHON_BIN=""
  fi
fi

# Live-test key resolution chain: process env > repo .env.local/.env.
for key in GEMINI_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY; do
  load_env_var_from_dotenv_if_missing "$key"
done

if [[ -n "$PYTHON_BIN" ]] && [[ "${OPENVIBECODING_CI_PM_CHAT_DISABLE_CODEX_CONFIG:-0}" != "1" ]] && ! is_mainline_context && [[ -f "$codex_config_path" ]]; then
  codex_cfg_rows="$(
    "$PYTHON_BIN" - "$codex_config_path" <<'PY'
import pathlib
import sys
try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 fallback when tomli is installed
    try:
        import tomli as tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        tomllib = None

def parse_fallback_toml(raw: str) -> dict:
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
            if key in {"base_url", "model", "experimental_bearer_token", "api_key"}:
                provider_entry[key] = value
    if providers:
        data["model_providers"] = providers
    return data

path = pathlib.Path(sys.argv[1])
base_url = ""
provider_name = ""
model_name = ""
has_key = False
key_source = "none"

try:
    raw_text = path.read_text(encoding="utf-8")
    if tomllib is not None:
        data = tomllib.loads(raw_text)
    else:
        data = parse_fallback_toml(raw_text)
except Exception:
    data = {}

provider_name = str(data.get("model_provider") or "").strip()
providers = data.get("model_providers") if isinstance(data.get("model_providers"), dict) else {}
provider = providers.get(provider_name) if isinstance(providers, dict) else {}
provider = provider if isinstance(provider, dict) else {}

base_url = str(provider.get("base_url") or "").strip()
model_name = str(data.get("model") or provider.get("model") or "").strip()
token_raw = str(provider.get("experimental_bearer_token") or provider.get("api_key") or "").strip()
token_candidate = token_raw
if token_raw:
    key_source = "inline"

if token_candidate.startswith("${") and token_candidate.endswith("}") and len(token_candidate) > 3:
    env_name = token_candidate[2:-1].strip()
    token_candidate = str(__import__("os").environ.get(env_name, "")).strip()
    key_source = f"env:{env_name}" if env_name else "env"

has_key = bool(token_candidate)
if not has_key:
    key_source = "none"

print(f"codex_cfg_base_url\t{base_url}")
print(f"codex_cfg_provider\t{provider_name}")
print(f"codex_cfg_model\t{model_name}")
print(f"codex_cfg_has_key\t{'1' if has_key else '0'}")
print(f"codex_cfg_key_source\t{key_source}")
PY
  )"

  while IFS=$'\t' read -r cfg_key cfg_value; do
    [[ -z "${cfg_key:-}" ]] && continue
    case "$cfg_key" in
      codex_cfg_base_url|codex_cfg_provider|codex_cfg_model|codex_cfg_has_key|codex_cfg_key_source) ;;
      *)
        echo "❌ [ci-policy] unexpected codex-config key: ${cfg_key}" >&2
        exit 1
        ;;
    esac
    printf -v "$cfg_key" '%s' "$cfg_value"
  done <<<"$codex_cfg_rows"
fi

PROVIDER_ENV_CHAIN=(
  OPENVIBECODING_CI_PM_CHAT_PROVIDER
  OPENVIBECODING_E2E_CODEX_PROVIDER
  OPENVIBECODING_PROVIDER
)
RUNTIME_PROVIDER_ENV_CHAIN=(
  OPENVIBECODING_CI_PM_CHAT_RUNTIME_OPTIONS_PROVIDER
  OPENVIBECODING_RUNTIME_OPTIONS_PROVIDER
  OPENVIBECODING_E2E_RUNTIME_OPTIONS_PROVIDER
)
BASE_URL_ENV_CHAIN=(
  OPENVIBECODING_CI_PM_CHAT_BASE_URL
  OPENVIBECODING_E2E_CODEX_BASE_URL
)
MODEL_ENV_CHAIN=(
  OPENVIBECODING_CI_PM_CHAT_MODEL
  OPENVIBECODING_E2E_CODEX_MODEL
  OPENVIBECODING_MODEL
)

IFS=$'\t' read -r ENV_PROVIDER_SOURCE ENV_PROVIDER_RAW ENV_PROVIDER_NORM <<<"$(resolve_with_precedence normalize_provider "${PROVIDER_ENV_CHAIN[@]}")"
IFS=$'\t' read -r ENV_RUNTIME_PROVIDER_SOURCE ENV_RUNTIME_PROVIDER_RAW ENV_RUNTIME_PROVIDER_NORM <<<"$(resolve_with_precedence normalize_provider "${RUNTIME_PROVIDER_ENV_CHAIN[@]}")"
IFS=$'\t' read -r ENV_BASE_URL_SOURCE ENV_BASE_URL_RAW ENV_BASE_URL_NORM <<<"$(resolve_with_precedence normalize_base_url "${BASE_URL_ENV_CHAIN[@]}")"
IFS=$'\t' read -r ENV_MODEL_SOURCE ENV_MODEL_RAW ENV_MODEL_NORM <<<"$(resolve_with_precedence normalize_model "${MODEL_ENV_CHAIN[@]}")"

CFG_PROVIDER_NORM="$(normalize_provider "$codex_cfg_provider")"
CFG_BASE_URL_NORM="$(normalize_base_url "$codex_cfg_base_url")"
CFG_MODEL_NORM="$(normalize_model "$codex_cfg_model")"

if [[ -n "$ENV_RUNTIME_PROVIDER_NORM" && -n "$ENV_PROVIDER_NORM" && "$ENV_RUNTIME_PROVIDER_NORM" != "$ENV_PROVIDER_NORM" ]]; then
  echo "❌ [ci-policy] provider mismatch between runtime_options.provider (${ENV_RUNTIME_PROVIDER_RAW}) and env (${ENV_PROVIDER_RAW})" >&2
  exit 1
fi
if [[ -n "$ENV_RUNTIME_PROVIDER_NORM" && -n "$CFG_PROVIDER_NORM" && "$ENV_RUNTIME_PROVIDER_NORM" != "$CFG_PROVIDER_NORM" ]]; then
  echo "❌ [ci-policy] provider mismatch between runtime_options.provider (${ENV_RUNTIME_PROVIDER_RAW}) and codex config (${codex_cfg_provider})" >&2
  exit 1
fi
if [[ -n "$ENV_PROVIDER_NORM" && -n "$CFG_PROVIDER_NORM" && "$ENV_PROVIDER_NORM" != "$CFG_PROVIDER_NORM" ]]; then
  echo "❌ [ci-policy] provider mismatch between env (${ENV_PROVIDER_RAW}) and codex config (${codex_cfg_provider})" >&2
  exit 1
fi
if [[ -n "$ENV_BASE_URL_NORM" && -n "$CFG_BASE_URL_NORM" && "$ENV_BASE_URL_NORM" != "$CFG_BASE_URL_NORM" ]]; then
  echo "❌ [ci-policy] base_url mismatch between env (${ENV_BASE_URL_RAW}) and codex config (${codex_cfg_base_url})" >&2
  exit 1
fi
if [[ -n "$ENV_MODEL_NORM" && -n "$CFG_MODEL_NORM" && "$ENV_MODEL_NORM" != "$CFG_MODEL_NORM" ]]; then
  echo "❌ [ci-policy] model mismatch between env (${ENV_MODEL_RAW}) and codex config (${codex_cfg_model})" >&2
  exit 1
fi

RESOLVED_PROVIDER="${ENV_RUNTIME_PROVIDER_NORM:-${ENV_PROVIDER_NORM:-$CFG_PROVIDER_NORM}}"
RESOLVED_BASE_URL="${ENV_BASE_URL_NORM:-$CFG_BASE_URL_NORM}"
RESOLVED_MODEL="${ENV_MODEL_NORM:-$CFG_MODEL_NORM}"

assert_no_shadowed_lower_values "provider" "${ENV_PROVIDER_SOURCE:-}" "$ENV_PROVIDER_NORM" normalize_provider \
  "${PROVIDER_ENV_CHAIN[@]}"
assert_no_shadowed_lower_values "runtime_options.provider" "${ENV_RUNTIME_PROVIDER_SOURCE:-}" "$ENV_RUNTIME_PROVIDER_NORM" normalize_provider \
  "${RUNTIME_PROVIDER_ENV_CHAIN[@]}"
assert_no_shadowed_lower_values "base_url" "${ENV_BASE_URL_SOURCE:-}" "$ENV_BASE_URL_NORM" normalize_base_url \
  "${BASE_URL_ENV_CHAIN[@]}"
assert_no_shadowed_lower_values "model" "${ENV_MODEL_SOURCE:-}" "$ENV_MODEL_NORM" normalize_model \
  "${MODEL_ENV_CHAIN[@]}"

# We allow custom providers when using OpenAI-compatible gateways, but a custom
# provider must declare base_url so the route is explicit and deterministic.
if [[ -n "$RESOLVED_PROVIDER" ]] && ! is_known_provider "$RESOLVED_PROVIDER" && [[ -z "$RESOLVED_BASE_URL" ]]; then
  echo "❌ [ci-policy] custom provider requires explicit base_url: provider=${RESOLVED_PROVIDER}" >&2
  exit 1
fi

has_llm_key="0"
if [[ -n "${GEMINI_API_KEY:-}" ]] || [[ -n "${OPENAI_API_KEY:-}" ]] || [[ -n "${ANTHROPIC_API_KEY:-}" ]] || [[ "$codex_cfg_has_key" == "1" ]]; then
  has_llm_key="1"
fi
has_gemini_key="0"
if [[ -n "${GEMINI_API_KEY:-}" ]] || [[ -n "${GOOGLE_API_KEY:-}" ]] || [[ "$codex_cfg_has_key" == "1" ]]; then
  has_gemini_key="1"
fi

pm_chat_mode_default="real"
if ! is_mainline_context && [[ "$has_llm_key" != "1" ]] && [[ -z "${OPENVIBECODING_CI_PM_CHAT_MODE:-}" ]]; then
  pm_chat_mode_default="mock"
fi

pm_chat_mode="${OPENVIBECODING_CI_PM_CHAT_MODE:-$pm_chat_mode_default}"
pm_chat_runner="${OPENVIBECODING_CI_PM_CHAT_RUNNER:-agents}"
pm_chat_web_mode="${OPENVIBECODING_CI_PM_CHAT_WEB_MODE:-prod}"
pm_chat_runtime_provider="${ENV_RUNTIME_PROVIDER_NORM:-$RESOLVED_PROVIDER}"

pm_chat_requires_key="0"
pm_chat_requires_gemini_key="0"
if [[ "$pm_chat_mode" == "real" ]] && [[ "$has_llm_key" != "1" ]] && [[ "${OPENVIBECODING_CI_PM_CHAT_ALLOW_MISSING_KEY:-0}" != "1" ]]; then
  pm_chat_requires_key="1"
fi
if [[ "$pm_chat_mode" == "real" ]] && [[ "$pm_chat_runtime_provider" == "gemini" ]] && [[ "$has_gemini_key" != "1" ]] && [[ "${OPENVIBECODING_CI_PM_CHAT_ALLOW_MISSING_KEY:-0}" != "1" ]]; then
  pm_chat_requires_key="1"
  pm_chat_requires_gemini_key="1"
fi

pm_chat_use_codex_config="0"
if [[ "$codex_cfg_has_key" == "1" ]] || [[ -n "$codex_cfg_base_url" ]] || [[ -n "$codex_cfg_model" ]]; then
  pm_chat_use_codex_config="1"
fi

printf 'PM_CHAT_MODE=%s\n' "$pm_chat_mode"
printf 'PM_CHAT_RUNNER=%s\n' "$pm_chat_runner"
printf 'PM_CHAT_WEB_MODE=%s\n' "$pm_chat_web_mode"
printf 'PM_CHAT_PROVIDER=%q\n' "$RESOLVED_PROVIDER"
printf 'PM_CHAT_RUNTIME_OPTIONS_PROVIDER=%q\n' "$pm_chat_runtime_provider"
printf 'PM_CHAT_REQUIRES_KEY=%s\n' "$pm_chat_requires_key"
printf 'PM_CHAT_REQUIRES_GEMINI_KEY=%s\n' "$pm_chat_requires_gemini_key"
printf 'PM_CHAT_USE_CODEX_CONFIG=%s\n' "$pm_chat_use_codex_config"
printf 'PM_CHAT_CODEX_BASE_URL=%q\n' "$RESOLVED_BASE_URL"
printf 'PM_CHAT_CODEX_PROVIDER=%q\n' "$RESOLVED_PROVIDER"
printf 'PM_CHAT_CODEX_MODEL=%q\n' "$RESOLVED_MODEL"
printf 'PM_CHAT_CODEX_KEY_SOURCE=%q\n' "$codex_cfg_key_source"
printf 'PM_CHAT_HAS_LLM_KEY=%s\n' "$has_llm_key"
