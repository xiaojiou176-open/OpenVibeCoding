from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import cortexpilot_orch.config as config_module


def _reset_config_state() -> None:
    config_module._ENV_LOADED = False
    config_module.reset_cached_config()


def test_round4_config_properties_and_public_getters(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _reset_config_state()

    runtime_root = tmp_path / "runtime"
    schema_root = tmp_path / "schemas"
    contract_root = tmp_path / "contracts"
    logs_root = tmp_path / "logs"
    cache_root = tmp_path / "cache"
    schema_root.mkdir(parents=True, exist_ok=True)
    contract_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv("CORTEXPILOT_ENV_FILE", raising=False)
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_SCHEMA_ROOT", str(schema_root))
    monkeypatch.setenv("CORTEXPILOT_CONTRACT_ROOT", str(contract_root))
    monkeypatch.setenv("CORTEXPILOT_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("CORTEXPILOT_LOGS_ROOT", str(logs_root))
    monkeypatch.setenv("CORTEXPILOT_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("CORTEXPILOT_MACHINE_CACHE_ROOT", str(tmp_path / "machine-cache"))
    monkeypatch.setenv("CORTEXPILOT_RETENTION_MACHINE_CACHE_CAP_BYTES", "4096")

    cfg = config_module.load_config()

    assert cfg.schema_root == schema_root
    assert cfg.repo_root == tmp_path
    assert cfg.contract_root_explicit is True
    assert cfg.runtime_contract_root == tmp_path / ".runtime-cache" / "cortexpilot" / "contracts"
    assert cfg.machine_cache_root == tmp_path / "machine-cache"
    assert cfg.retention_machine_cache_cap_bytes == 4096

    assert config_module.get_security_config() == cfg.security
    assert config_module.get_retention_config() == cfg.retention
    assert config_module.get_runner_config() == cfg.runner


def test_round4_config_env_helpers_and_runtime_path_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _reset_config_state()

    monkeypatch.setenv("CORTEXPILOT_ENV_FILE", "custom.env")
    candidates = config_module._explicit_env_candidates(tmp_path)
    assert candidates == [Path("custom.env")]

    assert config_module._normalize_env_field_value("provider", " OPENAI ") == "openai"
    assert config_module._normalize_env_field_value("base_url", "https://example.local/v1///") == "https://example.local/v1"
    assert config_module.describe_env_override_order() == dict(config_module._ENV_OVERRIDE_ORDER)

    monkeypatch.setenv("ROUND4_INT", "not-a-number")
    assert config_module._env_int("ROUND4_INT", 7, min_value=3) == 7
    monkeypatch.setenv("ROUND4_INT", "1")
    assert config_module._env_int("ROUND4_INT", 7, min_value=3) == 3

    monkeypatch.setenv("ROUND4_FLOAT", "bad-float")
    assert config_module._env_float("ROUND4_FLOAT", 1.5, min_value=0.2) == 1.5
    monkeypatch.setenv("ROUND4_FLOAT", "0.1")
    assert config_module._env_float("ROUND4_FLOAT", 1.5, min_value=0.2) == 0.2

    monkeypatch.setenv("ROUND4_PERCENT", "nan-text")
    assert config_module._env_percent("ROUND4_PERCENT", 12.5) == 12.5
    monkeypatch.setenv("ROUND4_PERCENT", "-30")
    assert config_module._env_percent("ROUND4_PERCENT", 12.5) == 0.0
    monkeypatch.setenv("ROUND4_PERCENT", "130")
    assert config_module._env_percent("ROUND4_PERCENT", 12.5) == 100.0

    default_schema = tmp_path / "fallback-schemas"
    default_schema.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ROUND4_SCHEMA_ROOT", str(tmp_path / "missing-explicit"))
    resolved, explicit = config_module._resolve_runtime_path("ROUND4_SCHEMA_ROOT", str(default_schema))
    assert resolved == default_schema
    assert explicit is False


def test_round4_config_machine_cache_cap_defaults_from_space_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _reset_config_state()

    policy_path = tmp_path / "configs" / "space_governance_policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        """{
  "version": 1,
  "recent_activity_hours": 24,
  "apply_gate_max_age_minutes": 15,
  "machine_cache_retention_policy": {
    "default_cap_bytes": 7777,
    "auto_prune_interval_sec": 1800
  },
  "shared_realpath_prefixes": [],
  "layers": {
    "repo_internal": [],
    "repo_external_related": [],
    "shared_observation": []
  },
  "wave_targets": {},
  "process_groups": {
    "node": {
      "patterns": ["\\\\bnode\\\\b"]
    }
  },
  "rebuild_commands": [
    {
      "id": "bootstrap",
      "kind": "npm_script",
      "script": "bootstrap",
      "description": "bootstrap"
    }
  ]
}""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CORTEXPILOT_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("CORTEXPILOT_RETENTION_MACHINE_CACHE_CAP_BYTES", raising=False)

    cfg = config_module.load_config()

    assert cfg.retention_machine_cache_cap_bytes == 7777


def test_round4_config_prefers_cortexpilot_aliases_for_core_runtime_inputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _reset_config_state()

    runtime_root = tmp_path / "runtime-new"
    repo_root = tmp_path / "repo-new"
    logs_root = tmp_path / "logs-new"
    cache_root = tmp_path / "cache-new"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("CORTEXPILOT_LOGS_ROOT", str(logs_root))
    monkeypatch.setenv("CORTEXPILOT_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("CORTEXPILOT_API_AUTH_REQUIRED", "false")
    monkeypatch.setenv("CORTEXPILOT_API_TOKEN", "cp-token")
    monkeypatch.setenv("CORTEXPILOT_DASHBOARD_PORT", "4100")

    cfg = config_module.load_config()

    assert cfg.runtime_root == runtime_root
    assert cfg.repo_root == repo_root
    assert cfg.logs_root == logs_root
    assert cfg.cache_root == cache_root
    assert cfg.api_auth_required is False
    assert cfg.api_token == "cp-token"
    assert cfg.api_runtime.dashboard_port == "4100"


def test_round4_config_default_relative_runtime_paths_anchor_to_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _reset_config_state()

    repo_root = tmp_path / "repo"
    work_dir = repo_root / "apps" / "orchestrator"
    work_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.chdir(work_dir)
    monkeypatch.delenv("CORTEXPILOT_ENV_FILE", raising=False)
    monkeypatch.delenv("CORTEXPILOT_RUNTIME_ROOT", raising=False)
    monkeypatch.delenv("CORTEXPILOT_SCHEMA_ROOT", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CONTRACT_ROOT", raising=False)
    monkeypatch.delenv("CORTEXPILOT_RUNTIME_CONTRACT_ROOT", raising=False)
    monkeypatch.delenv("CORTEXPILOT_WORKTREE_ROOT", raising=False)
    monkeypatch.delenv("CORTEXPILOT_RUNS_ROOT", raising=False)
    monkeypatch.delenv("CORTEXPILOT_LOGS_ROOT", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CACHE_ROOT", raising=False)
    monkeypatch.delenv("CORTEXPILOT_REPO_ROOT", raising=False)
    monkeypatch.setattr(config_module, "_repo_root", lambda: repo_root)

    cfg = config_module.load_config()

    assert cfg.repo_root == repo_root
    assert cfg.runtime_root == repo_root / ".runtime-cache" / "cortexpilot"
    assert cfg.schema_root == repo_root / "schemas"
    assert cfg.contract_root == repo_root / "contracts"
    assert cfg.runtime_contract_root == repo_root / ".runtime-cache" / "cortexpilot" / "contracts"
    assert cfg.worktree_root == repo_root / ".runtime-cache" / "cortexpilot" / "worktrees"
    assert cfg.runs_root == repo_root / ".runtime-cache" / "cortexpilot" / "runs"
    assert cfg.logs_root == repo_root / ".runtime-cache" / "logs"
    assert cfg.cache_root == repo_root / ".runtime-cache" / "cache"


def test_round4_config_shadowed_env_and_explicit_env_loading(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _reset_config_state()

    original_override_order = dict(config_module._ENV_OVERRIDE_ORDER)
    monkeypatch.setattr(
        config_module,
        "_ENV_OVERRIDE_ORDER",
        {"base_url": ("CORTEXPILOT_PROVIDER_BASE_URL", "CORTEXPILOT_PROVIDER_MODEL")},
    )
    monkeypatch.setenv("CORTEXPILOT_PROVIDER_BASE_URL", "https://api.primary.local/v1")
    monkeypatch.setenv("CORTEXPILOT_PROVIDER_MODEL", "https://api.shadow.local/v1")
    with pytest.raises(RuntimeError, match="env effective-chain breakpoint"):
        config_module._assert_no_shadowed_env_values()

    _reset_config_state()
    monkeypatch.setattr(config_module, "_ENV_OVERRIDE_ORDER", original_override_order)
    monkeypatch.delenv("CORTEXPILOT_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("CORTEXPILOT_PROVIDER_MODEL", raising=False)

    class _FlipLoadedLock:
        def __enter__(self):
            config_module._ENV_LOADED = True
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(config_module, "_ENV_LOAD_LOCK", _FlipLoadedLock())
    config_module._load_explicit_env_files()
    assert config_module._ENV_LOADED is True

    _reset_config_state()
    monkeypatch.setattr(config_module, "_ENV_LOAD_LOCK", config_module.RLock())
    repo_root = tmp_path / "repo"
    env_file = repo_root / "envs" / "local.env"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("CORTEXPILOT_PROVIDER=gemini\n", encoding="utf-8")

    monkeypatch.setattr(config_module, "_repo_root", lambda: repo_root)
    monkeypatch.setenv("CORTEXPILOT_ENV_FILE", "envs/local.env")
    config_module._load_explicit_env_files()
    assert config_module._ENV_LOADED is True

    _reset_config_state()
    monkeypatch.setattr(config_module, "_repo_root", lambda: repo_root)
    monkeypatch.setenv("CORTEXPILOT_ENV_FILE", "envs/missing.env")
    with pytest.raises(RuntimeError, match="CORTEXPILOT_ENV_FILE not found"):
        config_module._load_explicit_env_files()


def test_round4_config_cache_force_reload_and_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    config_module._CONFIG_CACHE = None

    load_count = {"n": 0}

    def _fake_load_config() -> SimpleNamespace:
        load_count["n"] += 1
        return SimpleNamespace(version=load_count["n"])

    monkeypatch.setattr(config_module, "load_config", _fake_load_config)

    first = config_module.get_cached_config(force_reload=True)
    second = config_module.get_cached_config()
    assert first is second
    assert first.version == 1

    config_module.reset_cached_config()
    third = config_module.get_cached_config()
    assert third.version == 2

    fourth = config_module.get_cached_config(force_reload=True)
    assert fourth.version == 3
    assert load_count["n"] == 3
