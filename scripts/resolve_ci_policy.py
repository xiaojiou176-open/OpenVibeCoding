#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CORE_PATH = Path("configs/ci_policy.core.json")
DEFAULT_PROFILE_PATH = Path("configs/ci_policy.profiles.json")
DEFAULT_ADVANCED_PATH = Path("configs/ci_policy.advanced.json")
DEFAULT_OUTPUT_PATH = Path(".runtime-cache/test_output/ci/ci_policy_snapshot.json")

LayerMap = dict[str, Any]


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "y"}
    return bool(value)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"❌ [ci-policy-shadow] {label} config not found: {path}") from exc
    except OSError as exc:
        raise SystemExit(f"❌ [ci-policy-shadow] cannot read {label} config: {path} ({exc})") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"❌ [ci-policy-shadow] invalid json in {label} config: {path} ({exc})") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"❌ [ci-policy-shadow] {label} config root must be object")
    return data


def _normalize_env_layer(raw: Any, layer_name: str) -> LayerMap:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SystemExit(f"❌ [ci-policy-shadow] {layer_name} must be object")
    normalized: LayerMap = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key:
            raise SystemExit(f"❌ [ci-policy-shadow] {layer_name} contains invalid key: {key!r}")
        if value is None:
            normalized[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            normalized[key] = str(value)
        else:
            raise SystemExit(
                f"❌ [ci-policy-shadow] {layer_name}.{key} must be scalar (str/int/float/bool/null)"
            )
    return normalized


def _validate_break_glass_shape(
    merged_env: LayerMap,
    config: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []

    # 1) Validate conventional *_BREAK_GLASS tuple shape in resolved env.
    for key, raw_value in merged_env.items():
        if not key.endswith("_BREAK_GLASS"):
            continue
        if not _is_truthy(raw_value):
            continue
        reason_key = f"{key}_REASON"
        ticket_key = f"{key}_TICKET"
        if not merged_env.get(reason_key):
            warnings.append(f"break-glass key '{key}' enabled but missing '{reason_key}'")
        if not merged_env.get(ticket_key):
            warnings.append(f"break-glass key '{key}' enabled but missing '{ticket_key}'")

    # 2) Validate optional advanced.break_glass object structure when present.
    advanced = config.get("advanced")
    if isinstance(advanced, dict) and "break_glass" in advanced:
        bg = advanced.get("break_glass")
        if not isinstance(bg, dict):
            warnings.append("advanced.break_glass must be an object")
        else:
            for name, rule in bg.items():
                if name == "template":
                    if not isinstance(rule, dict):
                        warnings.append("advanced.break_glass.template must be an object")
                        continue
                    if "enabled" in rule and not isinstance(rule.get("enabled"), bool):
                        warnings.append("advanced.break_glass.template.enabled must be boolean")
                    for field in ("reason", "ticket", "expires_on"):
                        value = rule.get(field)
                        if not isinstance(value, str):
                            warnings.append(f"advanced.break_glass.template.{field} must be string")
                    continue

                if name == "required_fields":
                    if not isinstance(rule, list):
                        warnings.append("advanced.break_glass.required_fields must be an array")
                    else:
                        required_min = {"reason", "ticket"}
                        if not required_min.issubset({str(x) for x in rule}):
                            warnings.append(
                                "advanced.break_glass.required_fields should include reason/ticket"
                            )
                    continue

                if name == "scopes":
                    if not isinstance(rule, list):
                        warnings.append("advanced.break_glass.scopes must be an array")
                    elif any(not isinstance(item, str) or not item.strip() for item in rule):
                        warnings.append("advanced.break_glass.scopes must contain non-empty strings")
                    continue

                if not isinstance(rule, dict):
                    warnings.append(f"advanced.break_glass.{name} must be an object")
                    continue
                for field in ("switch", "reason", "ticket"):
                    value = rule.get(field)
                    if not isinstance(value, str) or not value.strip():
                        warnings.append(
                            f"advanced.break_glass.{name}.{field} must be non-empty string"
                        )

    return warnings


def _merge_layers(*layers: tuple[str, LayerMap]) -> tuple[LayerMap, dict[str, str]]:
    merged: LayerMap = {}
    source_map: dict[str, str] = {}
    for layer_name, layer in layers:
        for key, value in layer.items():
            merged[key] = value
            source_map[key] = layer_name
    return merged, source_map


def _emit_env_lines(resolved_env: LayerMap) -> None:
    for key in sorted(resolved_env.keys()):
        value = resolved_env[key]
        print(f"{key}={value}")


def _bool_env(value: Any) -> str:
    return "1" if bool(value) else "0"


def _resolve_core_env(core_cfg: dict[str, Any]) -> LayerMap:
    core_root = core_cfg.get("core")
    if not isinstance(core_root, dict):
        return {}
    pm_chat = core_root.get("pm_chat") if isinstance(core_root.get("pm_chat"), dict) else {}
    defaults = core_root.get("defaults") if isinstance(core_root.get("defaults"), dict) else {}
    gates = core_root.get("gates") if isinstance(core_root.get("gates"), dict) else {}
    env: LayerMap = {}

    if "mode_on_ci" in pm_chat:
        env["OPENVIBECODING_CI_PM_CHAT_MODE"] = str(pm_chat["mode_on_ci"])
    if "runner" in pm_chat:
        env["OPENVIBECODING_CI_PM_CHAT_RUNNER"] = str(pm_chat["runner"])
    if "web_mode" in pm_chat:
        env["OPENVIBECODING_CI_PM_CHAT_WEB_MODE"] = str(pm_chat["web_mode"])
    if "allow_mock_on_ci" in pm_chat:
        env["OPENVIBECODING_CI_PM_CHAT_ALLOW_MOCK_ON_CI"] = _bool_env(pm_chat["allow_mock_on_ci"])
    if "allow_missing_key" in pm_chat:
        env["OPENVIBECODING_CI_PM_CHAT_ALLOW_MISSING_KEY"] = _bool_env(pm_chat["allow_missing_key"])

    if "ui_truth_disable_auto_latest" in defaults:
        env["OPENVIBECODING_CI_UI_TRUTH_DISABLE_AUTO_LATEST"] = _bool_env(defaults["ui_truth_disable_auto_latest"])
    if "ui_truth_require_run_id_match" in defaults:
        env["OPENVIBECODING_CI_UI_TRUTH_REQUIRE_RUN_ID_MATCH"] = _bool_env(defaults["ui_truth_require_run_id_match"])
    if "ui_truth_enforce_flake_policy" in defaults:
        env["OPENVIBECODING_CI_UI_TRUTH_ENFORCE_FLAKE_POLICY"] = _bool_env(defaults["ui_truth_enforce_flake_policy"])
    if "ui_strict_require_gemini_verdict" in defaults:
        env["OPENVIBECODING_CI_UI_STRICT_REQUIRE_GEMINI_VERDICT"] = _bool_env(
            defaults["ui_strict_require_gemini_verdict"]
        )

    if "ui_regression_flake" in gates:
        env["OPENVIBECODING_CI_UI_REGRESSION_FLAKE_GATE"] = _bool_env(gates["ui_regression_flake"])

    return env


def _resolve_profile_env(profile_cfg: dict[str, Any], profile: str) -> LayerMap:
    profile_root = profile_cfg.get("profile")
    if not isinstance(profile_root, dict):
        return {}
    profiles = profile_root.get("profiles")
    if not isinstance(profiles, dict):
        return {}
    selected = profiles.get(profile)
    if not isinstance(selected, dict):
        return {}

    ui_flake = selected.get("ui_flake") if isinstance(selected.get("ui_flake"), dict) else {}
    ui_truth = selected.get("ui_truth") if isinstance(selected.get("ui_truth"), dict) else {}

    env: LayerMap = {}
    mapping = {
        "p0_iterations": "OPENVIBECODING_CI_UI_FLAKE_P0_ITER",
        "p1_iterations": "OPENVIBECODING_CI_UI_FLAKE_P1_ITER",
        "p0_threshold_percent": "OPENVIBECODING_CI_UI_FLAKE_P0_THRESHOLD",
        "p1_threshold_percent": "OPENVIBECODING_CI_UI_FLAKE_P1_THRESHOLD",
    }
    for source_key, env_key in mapping.items():
        if source_key in ui_flake:
            env[env_key] = str(ui_flake[source_key])

    truth_mapping = {
        "p0_min_iterations": "OPENVIBECODING_CI_UI_TRUTH_P0_MIN_ITERATIONS",
        "p1_min_iterations": "OPENVIBECODING_CI_UI_TRUTH_P1_MIN_ITERATIONS",
        "p0_max_threshold_percent": "OPENVIBECODING_CI_UI_TRUTH_P0_MAX_THRESHOLD_PERCENT",
        "p1_max_threshold_percent": "OPENVIBECODING_CI_UI_TRUTH_P1_MAX_THRESHOLD_PERCENT",
    }
    for source_key, env_key in truth_mapping.items():
        if source_key in ui_truth:
            env[env_key] = str(ui_truth[source_key])

    return env


def _resolve_advanced_overrides(advanced_cfg: dict[str, Any]) -> LayerMap:
    advanced_root = advanced_cfg.get("advanced")
    if not isinstance(advanced_root, dict):
        return {}
    return _normalize_env_layer(advanced_root.get("overrides"), "advanced.overrides")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve CI policy in shadow mode and emit auditable environment snapshot."
    )
    parser.add_argument(
        "--profile",
        default="pr",
        help="UI policy profile name: hosted PR subprofile (`pr`), nightly, or manual",
    )
    parser.add_argument(
        "--output-json",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Snapshot output path (default: .runtime-cache/test_output/ci_policy_snapshot.json)",
    )
    parser.add_argument(
        "--emit-env",
        action="store_true",
        help="Print resolved KEY=VALUE environment lines to stdout",
    )

    args = parser.parse_args()

    core_path = Path(os.environ.get("OPENVIBECODING_CI_POLICY_CORE_CONFIG", str(DEFAULT_CORE_PATH)))
    profile_path = Path(os.environ.get("OPENVIBECODING_CI_POLICY_PROFILE_CONFIG", str(DEFAULT_PROFILE_PATH)))
    advanced_path = Path(os.environ.get("OPENVIBECODING_CI_POLICY_ADVANCED_CONFIG", str(DEFAULT_ADVANCED_PATH)))

    core_cfg = _load_json(core_path, "core")
    profile_cfg = _load_json(profile_path, "profile")
    advanced_cfg = _load_json(advanced_path, "advanced")

    core = _resolve_core_env(core_cfg)
    profile_layer = _resolve_profile_env(profile_cfg, args.profile)
    overrides = _resolve_advanced_overrides(advanced_cfg)

    resolved_env, source_map = _merge_layers(
        ("core", core),
        (f"profile:{args.profile}", profile_layer),
        ("advanced.overrides", overrides),
    )

    warnings = _validate_break_glass_shape(resolved_env, advanced_cfg)
    for warning in warnings:
        print(f"⚠️ [ci-policy-shadow] {warning}", file=sys.stderr)

    snapshot = {
        "profile": args.profile,
        "config_path": {
            "core": str(core_path),
            "profile": str(profile_path),
            "advanced": str(advanced_path),
        },
        "layers_applied": ["core", f"profile:{args.profile}", "advanced.overrides"],
        "resolved_env": resolved_env,
        "source_map": source_map,
        "warnings": warnings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "shadow",
    }

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.emit_env:
        _emit_env_lines(resolved_env)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
