import pytest

from openvibecoding_orch.planning import intake_policy_helpers


def test_normalize_browser_policy_fail_closed_defaults() -> None:
    normalized = intake_policy_helpers._normalize_browser_policy(
        {
            "profile_mode": "bad-mode",
            "stealth_mode": "bad-stealth",
            "human_behavior": {"enabled": 1, "level": "unknown"},
            "profile_ref": "bad",
            "cookie_ref": "bad",
        }
    )

    assert normalized["profile_mode"] == "ephemeral"
    assert normalized["stealth_mode"] == "none"
    assert normalized["human_behavior"] == {"enabled": True, "level": "low"}
    assert normalized["profile_ref"] == {"profile_dir": "", "profile_name": ""}
    assert normalized["cookie_ref"] == {"cookie_path": ""}


def test_compact_browser_policy_keeps_only_non_empty_refs() -> None:
    compact = intake_policy_helpers._compact_browser_policy(
        {
            "profile_mode": "allow_profile",
            "stealth_mode": "lite",
            "human_behavior": {"enabled": True, "level": "high"},
            "profile_ref": {"profile_dir": "profiles/dev", "profile_name": "dev"},
            "cookie_ref": {"cookie_path": "cookies/state.json"},
        }
    )
    assert compact["profile_mode"] == "allow_profile"
    assert compact["profile_ref"] == {"profile_dir": "profiles/dev", "profile_name": "dev"}
    assert compact["cookie_ref"] == {"cookie_path": "cookies/state.json"}


def test_resolve_intake_browser_policy_custom_and_preset_paths() -> None:
    with pytest.raises(ValueError, match="privileged requester role"):
        intake_policy_helpers._resolve_intake_browser_policy(
            {
                "browser_policy_preset": "custom",
                "requester_role": "pm",
                "browser_policy": {},
            }
        )

    with pytest.raises(ValueError, match="browser_policy payload"):
        intake_policy_helpers._resolve_intake_browser_policy(
            {
                "browser_policy_preset": "custom",
                "requester_role": "owner",
            }
        )

    preset, policy, message = intake_policy_helpers._resolve_intake_browser_policy(
        {
            "browser_policy_preset": "custom",
            "requester_role": "TECH_LEAD",
            "browser_policy": {
                "profile_mode": "cookie_file",
                "stealth_mode": "plugin",
                "human_behavior": {"enabled": True, "level": "medium"},
                "cookie_ref": {"cookie_path": "cookies/custom.json"},
            },
        }
    )
    assert preset == "custom"
    assert policy["profile_mode"] == "cookie_file"
    assert policy["cookie_ref"]["cookie_path"] == "cookies/custom.json"
    assert message == "custom policy accepted"

    preset2, policy2, message2 = intake_policy_helpers._resolve_intake_browser_policy(
        {"browser_policy_preset": "not-supported"}
    )
    assert preset2 == "safe"
    assert policy2["profile_mode"] == "ephemeral"
    assert message2 == "preset applied: safe"
