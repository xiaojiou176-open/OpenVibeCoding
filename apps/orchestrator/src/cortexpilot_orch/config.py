from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from dotenv import load_dotenv
from cortexpilot_orch.runners.provider_resolution import (
    resolve_provider_credentials,
    resolve_runtime_base_url_from_env,
    resolve_runtime_model_from_env,
    resolve_runtime_provider_from_env,
)


@dataclass(frozen=True)
class RuntimeConfig:
    runtime_root: Path
    schema_root: Path
    contract_root: Path
    runtime_contract_root: Path
    machine_cache_root: Path
    toolchain_cache_root: Path
    worktree_root: Path
    runs_root: Path
    repo_root: Path
    logs_root: Path
    cache_root: Path
    contract_root_explicit: bool


@dataclass(frozen=True)
class SecurityConfig:
    api_auth_required: bool
    api_token: str


@dataclass(frozen=True)
class RetentionConfig:
    run_days: int
    max_runs: int
    log_days: int
    worktree_days: int
    log_max_files: int
    cache_hours: int
    codex_home_days: int
    max_codex_homes: int
    intake_days: int
    max_intakes: int
    machine_cache_cap_bytes: int


@dataclass(frozen=True)
class TracingConfig:
    enabled: bool
    endpoint: str
    headers: str
    protocol: str
    console_enabled: bool
    required: bool


@dataclass(frozen=True)
class LoggingConfig:
    max_bytes: int
    backup_count: int
    trace_id: str
    schema_version: str


@dataclass(frozen=True)
class ApiRuntimeConfig:
    dashboard_port: str
    canary_percent: float
    allowed_origins: tuple[str, ...]


@dataclass(frozen=True)
class RunnerConfig:
    provider: str
    agents_base_url: str
    agents_api: str
    agents_model: str
    codex_model: str
    agents_store: bool
    # Compatibility placeholders kept for existing call sites.
    equilibrium_api_key: str
    openai_api_key: str
    anthropic_api_key: str
    gemini_api_key: str
    mcp_timeout_seconds: float
    mcp_connect_timeout_seconds: float


@dataclass(frozen=True)
class CortexPilotConfig:
    runtime: RuntimeConfig
    security: SecurityConfig
    retention: RetentionConfig
    tracing: TracingConfig
    logging: LoggingConfig
    api_runtime: ApiRuntimeConfig
    runner: RunnerConfig

    @property
    def runtime_root(self) -> Path:
        return self.runtime.runtime_root

    @property
    def schema_root(self) -> Path:
        return self.runtime.schema_root

    @property
    def contract_root(self) -> Path:
        return self.runtime.contract_root

    @property
    def runtime_contract_root(self) -> Path:
        return self.runtime.runtime_contract_root

    @property
    def worktree_root(self) -> Path:
        return self.runtime.worktree_root

    @property
    def toolchain_cache_root(self) -> Path:
        return self.runtime.toolchain_cache_root

    @property
    def machine_cache_root(self) -> Path:
        return self.runtime.machine_cache_root

    @property
    def runs_root(self) -> Path:
        return self.runtime.runs_root

    @property
    def repo_root(self) -> Path:
        return self.runtime.repo_root

    @property
    def logs_root(self) -> Path:
        return self.runtime.logs_root

    @property
    def cache_root(self) -> Path:
        return self.runtime.cache_root

    @property
    def contract_root_explicit(self) -> bool:
        return self.runtime.contract_root_explicit

    @property
    def api_auth_required(self) -> bool:
        return self.security.api_auth_required

    @property
    def api_token(self) -> str:
        return self.security.api_token

    @property
    def retention_run_days(self) -> int:
        return self.retention.run_days

    @property
    def retention_max_runs(self) -> int:
        return self.retention.max_runs

    @property
    def retention_log_days(self) -> int:
        return self.retention.log_days

    @property
    def retention_worktree_days(self) -> int:
        return self.retention.worktree_days

    @property
    def retention_log_max_files(self) -> int:
        return self.retention.log_max_files

    @property
    def retention_cache_hours(self) -> int:
        return self.retention.cache_hours

    @property
    def retention_codex_home_days(self) -> int:
        return self.retention.codex_home_days

    @property
    def retention_max_codex_homes(self) -> int:
        return self.retention.max_codex_homes

    @property
    def retention_intake_days(self) -> int:
        return self.retention.intake_days

    @property
    def retention_max_intakes(self) -> int:
        return self.retention.max_intakes

    @property
    def retention_machine_cache_cap_bytes(self) -> int:
        return self.retention.machine_cache_cap_bytes


_ENV_LOAD_LOCK = RLock()
_ENV_LOADED = False
_CONFIG_CACHE_LOCK = RLock()
_CONFIG_CACHE: CortexPilotConfig | None = None
_ENV_OVERRIDE_ORDER = {
    "provider": ("CORTEXPILOT_PROVIDER",),
    "base_url": ("CORTEXPILOT_PROVIDER_BASE_URL",),
    "model": ("CORTEXPILOT_PROVIDER_MODEL",),
}


def _env_value(raw: str | None, default: str = "") -> str:
    if raw is None:
        return default
    stripped = raw.strip()
    return stripped or default


def _env_csv(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    values: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        normalized = item.strip().rstrip("/")
        if not normalized or normalized in seen:
            continue
        values.append(normalized)
        seen.add(normalized)
    return tuple(values)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _resolve_repo_relative_path(path: Path, repo_root: Path) -> Path:
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _explicit_env_candidates(repo_root: Path) -> list[Path]:
    explicit_path = os.getenv("CORTEXPILOT_ENV_FILE", "").strip()
    if explicit_path:
        return [Path(explicit_path)]
    env_root = Path(os.getenv("CORTEXPILOT_DEFAULT_ENV_ROOT", "~/.config/cortexpilot")).expanduser()
    return [
        env_root / ".env.local",
        env_root / ".env",
    ]


def _normalize_env_value(raw: str | None) -> str:
    return str(raw or "").strip()


def _normalize_env_field_value(field_name: str, raw: str | None) -> str:
    value = _normalize_env_value(raw)
    if field_name == "provider":
        return value.lower()
    if field_name == "base_url":
        while value.endswith("/"):
            value = value[:-1]
        return value
    return value


def describe_env_override_order() -> dict[str, tuple[str, ...]]:
    return dict(_ENV_OVERRIDE_ORDER)


def _assert_no_shadowed_env_values() -> None:
    env_values = {
        "CORTEXPILOT_PROVIDER": os.getenv("CORTEXPILOT_PROVIDER"),
        "CORTEXPILOT_PROVIDER_BASE_URL": os.getenv("CORTEXPILOT_PROVIDER_BASE_URL"),
        "CORTEXPILOT_PROVIDER_MODEL": os.getenv("CORTEXPILOT_PROVIDER_MODEL"),
    }
    for field_name, keys in _ENV_OVERRIDE_ORDER.items():
        resolved_idx = -1
        resolved_value = ""
        for idx, key in enumerate(keys):
            candidate = _normalize_env_field_value(field_name, env_values.get(key))
            if candidate:
                resolved_idx = idx
                resolved_value = candidate
                break
        if resolved_idx < 0:
            continue
        for shadow_key in keys[resolved_idx + 1 :]:
            shadow_value = _normalize_env_field_value(field_name, env_values.get(shadow_key))
            if shadow_value and shadow_value != resolved_value:
                raise RuntimeError(
                    f"env effective-chain breakpoint: {field_name} uses {keys[resolved_idx]}={resolved_value} "
                    f"but {shadow_key}={shadow_value} is shadowed"
                )


def _load_explicit_env_files() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    with _ENV_LOAD_LOCK:
        if _ENV_LOADED:
            return
        explicit_path = _normalize_env_value(os.getenv("CORTEXPILOT_ENV_FILE"))
        if explicit_path:
            explicit_candidate = Path(explicit_path).expanduser()
            if not explicit_candidate.is_absolute():
                explicit_candidate = (_repo_root() / explicit_candidate).resolve()
            if not explicit_candidate.exists() or not explicit_candidate.is_file():
                raise RuntimeError(f"env effective-chain breakpoint: CORTEXPILOT_ENV_FILE not found: {explicit_candidate}")
        for candidate in _explicit_env_candidates(_repo_root()):
            if candidate.exists() and candidate.is_file():
                load_dotenv(dotenv_path=candidate, override=False)
        _assert_no_shadowed_env_values()
        _ENV_LOADED = True


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, min_value: int = 0) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < min_value:
        return min_value
    return value


def _env_float(name: str, default: float, min_value: float = 0.0) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError:
        return default
    if value < min_value:
        return min_value
    return value


def _env_percent(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(0.0, min(100.0, value))


def _resolve_runtime_path(name: str, default: str, repo_root: Path | None = None) -> tuple[Path, bool]:
    if repo_root is None:
        repo_root = _repo_root()
    raw = os.getenv(name)
    explicit = raw is not None and raw.strip() != ""
    configured = (raw or "").strip() or default
    configured_path = _resolve_repo_relative_path(Path(configured), repo_root)
    if explicit and not configured_path.exists():
        default_path = _resolve_repo_relative_path(Path(default), repo_root)
        if default_path.exists():
            return default_path, False
    return configured_path, explicit


def _default_machine_cache_root() -> Path:
    explicit = os.getenv("CORTEXPILOT_MACHINE_CACHE_ROOT", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    runner_temp = os.getenv("RUNNER_TEMP", "").strip()
    ci = os.getenv("CI", "").strip().lower() in {"1", "true", "yes", "on"} or os.getenv("GITHUB_ACTIONS", "").strip().lower() == "true"
    if ci and runner_temp:
        return Path(runner_temp) / "cortexpilot-machine-cache"
    xdg_cache_home = os.getenv("XDG_CACHE_HOME", "").strip()
    if xdg_cache_home:
        return Path(xdg_cache_home) / "cortexpilot"
    return Path.home() / ".cache" / "cortexpilot"


def _default_machine_cache_cap_bytes(repo_root: Path) -> int:
    policy_path = repo_root / "configs" / "space_governance_policy.json"
    fallback = 20 * 1024 * 1024 * 1024
    if not policy_path.exists():
        return fallback
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    machine_cache_policy = payload.get("machine_cache_retention_policy", {})
    raw_value = machine_cache_policy.get("default_cap_bytes")
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def load_config() -> CortexPilotConfig:
    _load_explicit_env_files()

    repo_root = _resolve_repo_relative_path(
        Path(_env_value(os.getenv("CORTEXPILOT_REPO_ROOT"), str(_repo_root()))),
        _repo_root(),
    )
    runtime_root = _resolve_repo_relative_path(
        Path(
            _env_value(
                os.getenv("CORTEXPILOT_RUNTIME_ROOT"),
                ".runtime-cache/cortexpilot",
            )
        ),
        repo_root,
    )
    schema_root, _ = _resolve_runtime_path("CORTEXPILOT_SCHEMA_ROOT", "schemas", repo_root)
    contract_root, contract_root_explicit = _resolve_runtime_path(
        "CORTEXPILOT_CONTRACT_ROOT", "contracts", repo_root
    )
    runtime_contract_root = _resolve_repo_relative_path(
        Path(os.getenv("CORTEXPILOT_RUNTIME_CONTRACT_ROOT", ".runtime-cache/cortexpilot/contracts")),
        repo_root,
    )
    machine_cache_root = _default_machine_cache_root()
    toolchain_cache_root = Path(os.getenv("CORTEXPILOT_TOOLCHAIN_CACHE_ROOT", str(machine_cache_root / "toolchains")))
    worktree_root = _resolve_repo_relative_path(
        Path(os.getenv("CORTEXPILOT_WORKTREE_ROOT", ".runtime-cache/cortexpilot/worktrees")),
        repo_root,
    )
    runs_root = _resolve_repo_relative_path(
        Path(os.getenv("CORTEXPILOT_RUNS_ROOT", ".runtime-cache/cortexpilot/runs")),
        repo_root,
    )
    logs_root = _resolve_repo_relative_path(
        Path(
            _env_value(
                os.getenv("CORTEXPILOT_LOGS_ROOT"),
                ".runtime-cache/logs",
            )
        ),
        repo_root,
    )
    cache_root = _resolve_repo_relative_path(
        Path(
            _env_value(
                os.getenv("CORTEXPILOT_CACHE_ROOT"),
                ".runtime-cache/cache",
            )
        ),
        repo_root,
    )

    runtime = RuntimeConfig(
        runtime_root=runtime_root,
        schema_root=schema_root,
        contract_root=contract_root,
        runtime_contract_root=runtime_contract_root,
        machine_cache_root=machine_cache_root,
        toolchain_cache_root=toolchain_cache_root,
        worktree_root=worktree_root,
        runs_root=runs_root,
        repo_root=repo_root,
        logs_root=logs_root,
        cache_root=cache_root,
        contract_root_explicit=contract_root_explicit,
    )

    security = SecurityConfig(
        api_auth_required=_env_flag("CORTEXPILOT_API_AUTH_REQUIRED", True),
        api_token=_env_value(os.getenv("CORTEXPILOT_API_TOKEN")),
    )

    retention = RetentionConfig(
        run_days=_env_int("CORTEXPILOT_RETENTION_RUN_DAYS", 7, min_value=1),
        max_runs=_env_int("CORTEXPILOT_RETENTION_MAX_RUNS", 200, min_value=1),
        log_days=_env_int("CORTEXPILOT_RETENTION_LOG_DAYS", 7, min_value=1),
        worktree_days=_env_int("CORTEXPILOT_RETENTION_WORKTREE_DAYS", 2, min_value=1),
        log_max_files=_env_int("CORTEXPILOT_RETENTION_LOG_MAX_FILES", 5, min_value=1),
        cache_hours=_env_int("CORTEXPILOT_RETENTION_CACHE_HOURS", 24, min_value=1),
        codex_home_days=_env_int("CORTEXPILOT_RETENTION_CODEX_HOME_DAYS", 3, min_value=1),
        max_codex_homes=_env_int("CORTEXPILOT_RETENTION_MAX_CODEX_HOMES", 500, min_value=1),
        intake_days=_env_int("CORTEXPILOT_RETENTION_INTAKE_DAYS", 7, min_value=1),
        max_intakes=_env_int("CORTEXPILOT_RETENTION_MAX_INTAKES", 500, min_value=1),
        machine_cache_cap_bytes=_env_int(
            "CORTEXPILOT_RETENTION_MACHINE_CACHE_CAP_BYTES",
            _default_machine_cache_cap_bytes(repo_root),
            min_value=1,
        ),
    )

    tracing = TracingConfig(
        enabled=_env_flag("CORTEXPILOT_TRACING_ENABLED", True),
        endpoint=os.getenv("CORTEXPILOT_OTLP_ENDPOINT", "").strip(),
        headers=os.getenv("CORTEXPILOT_OTLP_HEADERS", "").strip(),
        protocol=os.getenv("CORTEXPILOT_OTLP_PROTOCOL", "grpc").strip().lower() or "grpc",
        console_enabled=_env_flag("CORTEXPILOT_ENABLE_CONSOLE_TRACE", False),
        required=_env_flag("CORTEXPILOT_OTEL_REQUIRED", False),
    )

    logging = LoggingConfig(
        max_bytes=_env_int("CORTEXPILOT_LOG_MAX_BYTES", 100 * 1024 * 1024, min_value=1024),
        backup_count=_env_int("CORTEXPILOT_LOG_BACKUP_COUNT", 5, min_value=1),
        trace_id=os.getenv("CORTEXPILOT_TRACE_ID", "").strip(),
        schema_version=os.getenv("CORTEXPILOT_LOG_SCHEMA_VERSION", "log_event.v2").strip() or "log_event.v2",
    )

    api_runtime = ApiRuntimeConfig(
        dashboard_port=(
            _env_value(
                os.getenv("CORTEXPILOT_DASHBOARD_PORT"),
                "3100",
            )
            or "3100"
        ),
        canary_percent=_env_percent("CORTEXPILOT_CANARY_PERCENT", 0.0),
        allowed_origins=_env_csv("CORTEXPILOT_API_ALLOWED_ORIGINS"),
    )

    provider_credentials = resolve_provider_credentials()
    runtime_provider = resolve_runtime_provider_from_env()
    runtime_base_url = resolve_runtime_base_url_from_env()
    runtime_model = resolve_runtime_model_from_env(provider=runtime_provider)

    runner = RunnerConfig(
        provider=runtime_provider,
        agents_base_url=runtime_base_url,
        agents_api=os.getenv("CORTEXPILOT_AGENTS_API", "").strip(),
        agents_model=runtime_model,
        codex_model=os.getenv("CORTEXPILOT_CODEX_MODEL", "").strip() or runtime_model,
        agents_store=_env_flag("CORTEXPILOT_AGENTS_STORE", False),
        equilibrium_api_key=provider_credentials.equilibrium_api_key,
        openai_api_key=provider_credentials.openai_api_key,
        anthropic_api_key=provider_credentials.anthropic_api_key,
        gemini_api_key=provider_credentials.gemini_api_key,
        mcp_timeout_seconds=_env_float("CORTEXPILOT_MCP_SERVER_TIMEOUT_SEC", 30.0, min_value=0.1),
        mcp_connect_timeout_seconds=_env_float("CORTEXPILOT_MCP_SERVER_CONNECT_TIMEOUT_SEC", 10.0, min_value=0.1),
    )

    return CortexPilotConfig(
        runtime=runtime,
        security=security,
        retention=retention,
        tracing=tracing,
        logging=logging,
        api_runtime=api_runtime,
        runner=runner,
    )


def get_cached_config(force_reload: bool = False) -> CortexPilotConfig:
    global _CONFIG_CACHE
    if force_reload:
        with _CONFIG_CACHE_LOCK:
            _CONFIG_CACHE = None
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    with _CONFIG_CACHE_LOCK:
        if _CONFIG_CACHE is None:
            _CONFIG_CACHE = load_config()
        return _CONFIG_CACHE


def reset_cached_config() -> None:
    global _CONFIG_CACHE
    with _CONFIG_CACHE_LOCK:
        _CONFIG_CACHE = None


def get_runtime_config() -> RuntimeConfig:
    return load_config().runtime


def get_security_config() -> SecurityConfig:
    return load_config().security


def get_retention_config() -> RetentionConfig:
    return load_config().retention


def get_runner_config() -> RunnerConfig:
    return load_config().runner


def get_tracing_config() -> TracingConfig:
    return load_config().tracing


def get_logging_config() -> LoggingConfig:
    return load_config().logging


def get_api_runtime_config() -> ApiRuntimeConfig:
    return load_config().api_runtime
