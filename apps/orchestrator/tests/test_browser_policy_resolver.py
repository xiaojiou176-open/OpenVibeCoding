from __future__ import annotations

from pathlib import Path

from cortexpilot_orch.policy import browser_policy_resolver
from cortexpilot_orch.policy.browser_policy_resolver import resolve_browser_policy


def test_resolver_local_dev_defaults_to_allow_profile(monkeypatch, tmp_path: Path) -> None:
    browser_root = tmp_path / "browser-root"
    chrome_root = browser_root / "chrome-user-data"
    chrome_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CI_CONTAINER", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CLEAN_ROOM_MACHINE_TMP_ROOT", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CLEAN_ROOM_PRESERVE_ROOT", raising=False)
    monkeypatch.delenv("CORTEXPILOT_BROWSER_PROFILE_ALLOWLIST", raising=False)
    monkeypatch.setattr(browser_policy_resolver, "_default_chrome_profile_dir", lambda: chrome_root)
    monkeypatch.setattr(browser_policy_resolver, "default_repo_browser_root", lambda: browser_root)

    audit = resolve_browser_policy(
        contract_policy=None,
        task_policy=None,
        requested_by={"role": "PM"},
        source="browser",
        task_id="browser_local_default",
    )

    assert audit["requested_policy"]["profile_mode"] == "allow_profile"
    assert audit["requested_policy"]["profile_ref"]["profile_dir"] == str(chrome_root)
    assert audit["requested_policy"]["profile_ref"]["profile_name"] == "cortexpilot"
    assert audit["effective_policy"]["profile_mode"] == "allow_profile"
    assert audit["effective_policy"]["profile_ref"]["profile_dir"] == str(chrome_root)
    assert audit["effective_policy"]["profile_ref"]["profile_name"] == "cortexpilot"
    assert audit["policy_source"]["profile_mode"] == "env"
    assert audit["policy_source"]["profile_ref.profile_dir"] == "default"
    assert audit["policy_source"]["profile_ref.profile_name"] == "env"


def test_resolver_ci_defaults_to_ephemeral(monkeypatch, tmp_path: Path) -> None:
    chrome_root = tmp_path / "chrome-root"
    chrome_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("CORTEXPILOT_BROWSER_PROFILE_MODE", raising=False)
    monkeypatch.delenv("CORTEXPILOT_BROWSER_PROFILE_DIR", raising=False)
    monkeypatch.delenv("CORTEXPILOT_BROWSER_PROFILE_NAME", raising=False)
    monkeypatch.setattr(browser_policy_resolver, "_default_chrome_profile_dir", lambda: chrome_root)

    audit = resolve_browser_policy(
        contract_policy=None,
        task_policy=None,
        requested_by={"role": "PM"},
        source="browser",
        task_id="browser_ci_default",
    )

    assert audit["requested_policy"]["profile_mode"] == "ephemeral"
    assert audit["requested_policy"]["profile_ref"]["profile_dir"] == ""
    assert audit["requested_policy"]["profile_ref"]["profile_name"] == "Default"
    assert audit["effective_policy"]["profile_mode"] == "ephemeral"


def test_resolver_force_ephemeral_environment_blocks_explicit_allow_profile(monkeypatch, tmp_path: Path) -> None:
    chrome_root = tmp_path / "chrome-root"
    chrome_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CORTEXPILOT_CLEAN_ROOM_MACHINE_TMP_ROOT", str(tmp_path / "machine-tmp"))
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_ALLOWLIST", str(chrome_root))

    audit = resolve_browser_policy(
        contract_policy={
            "profile_mode": "allow_profile",
            "profile_ref": {"profile_dir": str(chrome_root), "profile_name": "cortexpilot"},
            "stealth_mode": "none",
            "human_behavior": {"enabled": False, "level": "low"},
        },
        task_policy=None,
        requested_by={"role": "PM"},
        source="browser",
        task_id="browser_force_ephemeral",
    )

    assert audit["requested_policy"]["profile_mode"] == "allow_profile"
    assert audit["effective_policy"]["profile_mode"] == "ephemeral"
    assert "allow_profile->ephemeral" in audit["fallback_chain"]
    assert any(
        item.get("meta", {}).get("rule") == "force_ephemeral_environment"
        for item in audit["events"]
        if item.get("event") == "BROWSER_POLICY_GUARD_BLOCK"
    )


def test_resolver_default_allowlist_includes_repo_browser_root(monkeypatch, tmp_path: Path) -> None:
    browser_root = tmp_path / "repo-browser"
    browser_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("CORTEXPILOT_BROWSER_PROFILE_ALLOWLIST", raising=False)
    monkeypatch.setattr(browser_policy_resolver, "default_repo_browser_root", lambda: browser_root)

    assert browser_root in browser_policy_resolver._profile_allowlist_roots()


def test_resolver_priority_and_task_override(monkeypatch, tmp_path: Path) -> None:
    allow_root = tmp_path / "profiles"
    allow_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_ALLOWLIST", str(allow_root))
    monkeypatch.setenv("CORTEXPILOT_BROWSER_STEALTH_MODE", "none")
    monkeypatch.setenv("CORTEXPILOT_BROWSER_HUMAN_BEHAVIOR", "0")

    contract_policy = {
        "profile_mode": "ephemeral",
        "stealth_mode": "lite",
        "human_behavior": {"enabled": False, "level": "low"},
    }
    task_policy = {
        "stealth_mode": "plugin",
        "human_behavior": {"enabled": True, "level": "high"},
    }

    audit = resolve_browser_policy(
        contract_policy=contract_policy,
        task_policy=task_policy,
        requested_by={"role": "SEARCHER"},
        source="search",
        task_id="search_1",
    )

    effective = audit["effective_policy"]
    assert effective["stealth_mode"] == "plugin"
    assert effective["human_behavior"]["enabled"] is True
    assert effective["human_behavior"]["level"] == "high"
    assert audit["policy_source"]["stealth_mode"] == "task"


def test_resolver_rejects_task_profile_override(monkeypatch) -> None:
    monkeypatch.delenv("CORTEXPILOT_BROWSER_BREAK_GLASS", raising=False)
    audit = resolve_browser_policy(
        contract_policy={"profile_mode": "ephemeral", "stealth_mode": "none", "human_behavior": {"enabled": False, "level": "low"}},
        task_policy={"profile_mode": "allow_profile", "stealth_mode": "lite"},
        requested_by={"role": "PM"},
        source="browser",
        task_id="browser_0",
    )

    events = audit["events"]
    assert any(item.get("event") == "BROWSER_POLICY_FIELD_REJECTED" for item in events)
    assert audit["effective_policy"]["profile_mode"] == "ephemeral"


def test_resolver_guard_blocks_non_allowlisted_profile(monkeypatch, tmp_path: Path) -> None:
    allow_root = tmp_path / "automation-profiles"
    allow_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_ALLOWLIST", str(allow_root))
    monkeypatch.delenv("CORTEXPILOT_BROWSER_BREAK_GLASS", raising=False)

    contract_policy = {
        "profile_mode": "allow_profile",
        "profile_ref": {"profile_dir": str(tmp_path / "daily-profile"), "profile_name": "Default"},
        "stealth_mode": "plugin",
        "human_behavior": {"enabled": True, "level": "high"},
    }

    audit = resolve_browser_policy(
        contract_policy=contract_policy,
        task_policy=None,
        requested_by={"role": "PM"},
        source="browser",
        task_id="browser_1",
    )

    assert audit["effective_policy"]["profile_mode"] == "ephemeral"
    assert "allow_profile->ephemeral" in audit["fallback_chain"]
    assert any(item.get("event") == "BROWSER_POLICY_GUARD_BLOCK" for item in audit["events"])


def test_resolver_break_glass_allows_privileged_override(monkeypatch, tmp_path: Path) -> None:
    allow_root = tmp_path / "automation-profiles"
    allow_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CI_CONTAINER", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CLEAN_ROOM_MACHINE_TMP_ROOT", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CLEAN_ROOM_PRESERVE_ROOT", raising=False)
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_ALLOWLIST", str(allow_root))
    monkeypatch.setenv("CORTEXPILOT_BROWSER_BREAK_GLASS", "1")

    contract_policy = {
        "profile_mode": "allow_profile",
        "profile_ref": {"profile_dir": str(tmp_path / "daily-profile"), "profile_name": "Default"},
        "stealth_mode": "plugin",
        "human_behavior": {"enabled": True, "level": "high"},
    }

    audit = resolve_browser_policy(
        contract_policy=contract_policy,
        task_policy=None,
        requested_by={"role": "OPS"},
        source="browser",
        task_id="browser_2",
    )

    assert audit["effective_policy"]["profile_mode"] == "allow_profile"
    events = [item.get("event") for item in audit["events"]]
    assert "BROWSER_BREAK_GLASS_ENABLED" in events
    assert "BROWSER_POLICY_OVERRIDE_APPROVED" in events


def test_resolver_explicit_env_profile_override_beats_contract(monkeypatch, tmp_path: Path) -> None:
    allow_root = tmp_path / "profiles"
    allow_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CI_CONTAINER", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CLEAN_ROOM_MACHINE_TMP_ROOT", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CLEAN_ROOM_PRESERVE_ROOT", raising=False)
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_ALLOWLIST", str(allow_root))
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_MODE", "allow_profile")
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_DIR", str(allow_root))
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_NAME", "Default")

    audit = resolve_browser_policy(
        contract_policy={
            "profile_mode": "ephemeral",
            "stealth_mode": "none",
            "human_behavior": {"enabled": False, "level": "low"},
        },
        task_policy=None,
        requested_by={"role": "PM"},
        source="search",
        task_id="search_env_override",
    )

    assert audit["effective_policy"]["profile_mode"] == "allow_profile"
    assert audit["effective_policy"]["profile_ref"]["profile_dir"] == str(allow_root)
    assert audit["effective_policy"]["profile_ref"]["profile_name"] == "Default"
    assert audit["policy_source"]["profile_mode"] == "env"
    assert audit["policy_source"]["profile_ref.profile_name"] == "env"


def test_resolver_env_profile_survives_missing_contract(monkeypatch, tmp_path: Path) -> None:
    allow_root = tmp_path / "profiles"
    allow_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CI_CONTAINER", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CLEAN_ROOM_MACHINE_TMP_ROOT", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CLEAN_ROOM_PRESERVE_ROOT", raising=False)
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_ALLOWLIST", str(allow_root))
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_MODE", "allow_profile")
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_DIR", str(allow_root))
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_NAME", "Default")

    audit = resolve_browser_policy(
        contract_policy=None,
        task_policy=None,
        requested_by={"role": "PM"},
        source="search",
        task_id="search_env_only",
    )

    assert audit["requested_policy"]["profile_mode"] == "allow_profile"
    assert audit["effective_policy"]["profile_mode"] == "allow_profile"
    assert audit["policy_source"]["profile_mode"] == "env"


def test_resolver_defaults_profile_dir_before_allowlist_guard(monkeypatch, tmp_path: Path) -> None:
    allow_root = tmp_path / "profiles"
    allow_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CI_CONTAINER", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CLEAN_ROOM_MACHINE_TMP_ROOT", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CLEAN_ROOM_PRESERVE_ROOT", raising=False)
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_ALLOWLIST", str(allow_root))
    monkeypatch.setattr(browser_policy_resolver, "_default_chrome_profile_dir", lambda: allow_root)

    audit = resolve_browser_policy(
        contract_policy={
            "profile_mode": "allow_profile",
            "profile_ref": {"profile_dir": "", "profile_name": "Default"},
            "stealth_mode": "none",
            "human_behavior": {"enabled": False, "level": "low"},
        },
        task_policy=None,
        requested_by={"role": "PM"},
        source="search",
        task_id="search_default_dir",
    )

    assert audit["effective_policy"]["profile_mode"] == "allow_profile"
    assert audit["effective_policy"]["profile_ref"]["profile_dir"] == str(allow_root)
    assert audit["policy_source"]["profile_ref.profile_dir"] == "default"
