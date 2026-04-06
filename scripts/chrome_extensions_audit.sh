#!/usr/bin/env bash
set -euo pipefail

CHROME_ROOT="${1:-$HOME/Library/Application Support/Google/Chrome}"
TARGET_PROFILE="${2:-}"
OUT_DIR="${3:-$PWD/.runtime-cache/test_output/chrome_extensions_audit}"

if [[ ! -d "$CHROME_ROOT" ]]; then
  echo "❌ Chrome root not found: $CHROME_ROOT" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

python3 - "$CHROME_ROOT" "$TARGET_PROFILE" "$OUT_DIR" <<'PY'
import json
import os
import pathlib
import re
import sys
from collections import Counter
from datetime import datetime

chrome_root = pathlib.Path(sys.argv[1]).expanduser()
target_profile_arg = (sys.argv[2] or "").strip()
out_dir = pathlib.Path(sys.argv[3]).expanduser()
out_dir.mkdir(parents=True, exist_ok=True)

id_re = re.compile(r"^[a-p]{32}$")


def load_json(path: pathlib.Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def profile_dirs(root: pathlib.Path):
    return sorted(
        [
            directory
            for directory in root.iterdir()
            if directory.is_dir()
            and (directory.name == "Default" or directory.name.startswith("Profile "))
        ],
        key=lambda item: (item.name != "Default", item.name),
    )


def extension_ids_from_dir(ext_dir: pathlib.Path):
    if not ext_dir.exists():
        return set()
    return {
        child.name
        for child in ext_dir.iterdir()
        if child.is_dir() and id_re.match(child.name)
    }


local_state_path = chrome_root / "Local State"
local_state = load_json(local_state_path) if local_state_path.exists() else {}
last_used = (
    local_state.get("profile", {}).get("last_used")
    if isinstance(local_state, dict)
    else None
)

profiles = profile_dirs(chrome_root)
if not profiles:
    raise SystemExit(f"No profile directories found under: {chrome_root}")

if target_profile_arg:
    target_profile_name = target_profile_arg
else:
    target_profile_name = last_used or "Default"

target_profile = chrome_root / target_profile_name
if not target_profile.exists():
    available = ", ".join(profile.name for profile in profiles)
    raise SystemExit(
        f"Target profile not found: {target_profile_name}. Available: {available}"
    )

all_union_ids = set()
for profile in profiles:
    all_union_ids |= extension_ids_from_dir(profile / "Extensions")

target_fs_ids = extension_ids_from_dir(target_profile / "Extensions")

secure_preferences = load_json(target_profile / "Secure Preferences")
secure_settings = (
    (secure_preferences.get("extensions") or {}).get("settings")
    if isinstance(secure_preferences, dict)
    else {}
)
if not isinstance(secure_settings, dict):
    secure_settings = {}

target_secure_ids = {key for key in secure_settings.keys() if id_re.match(key)}

missing_vs_union = sorted(all_union_ids - target_fs_ids)
missing_vs_secure = sorted(target_secure_ids - target_fs_ids)

disable_reason_counter = Counter()
disable_reason_by_id = {}
for extension_id in missing_vs_secure:
    node = secure_settings.get(extension_id, {})
    reasons = node.get("disable_reasons") if isinstance(node, dict) else None
    if isinstance(reasons, list):
        cleaned = [int(value) for value in reasons if isinstance(value, int)]
    else:
        cleaned = []
    disable_reason_by_id[extension_id] = cleaned
    for reason in cleaned:
        disable_reason_counter[reason] += 1

info_cache = local_state.get("profile", {}).get("info_cache", {})
if not isinstance(info_cache, dict):
    info_cache = {}

profile_table = []
for profile in profiles:
    extensions_count = len(extension_ids_from_dir(profile / "Extensions"))
    local_ext_settings = profile / "Local Extension Settings"
    local_ext_settings_count = (
        len([x for x in local_ext_settings.iterdir() if x.is_dir()])
        if local_ext_settings.exists()
        else 0
    )
    cookies_path = profile / "Network" / "Cookies"
    if not cookies_path.exists():
        cookies_path = profile / "Cookies"
    cookies_mtime = (
        datetime.fromtimestamp(cookies_path.stat().st_mtime).isoformat()
        if cookies_path.exists()
        else None
    )
    profile_info = info_cache.get(profile.name, {}) if isinstance(info_cache, dict) else {}
    profile_table.append(
        {
            "profile": profile.name,
            "fs_extension_count": extensions_count,
            "local_extension_settings_count": local_ext_settings_count,
            "cookies_mtime": cookies_mtime,
            "user_name": profile_info.get("user_name", ""),
            "gaia_name": profile_info.get("gaia_name", ""),
            "is_primary": bool(profile_info.get("is_consented_primary_account", False)),
        }
    )

summary = {
    "timestamp": datetime.now().isoformat(),
    "chrome_root": str(chrome_root),
    "target_profile": target_profile_name,
    "local_state_last_used": last_used,
    "counts": {
        "union_fs_all_profiles": len(all_union_ids),
        "target_fs_extensions": len(target_fs_ids),
        "target_secure_preferences_extensions": len(target_secure_ids),
        "missing_vs_union": len(missing_vs_union),
        "missing_vs_secure_preferences": len(missing_vs_secure),
    },
    "disable_reason_counter": dict(disable_reason_counter),
    "profile_table": profile_table,
}

(out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
(out_dir / "missing_vs_union.txt").write_text("\n".join(missing_vs_union) + ("\n" if missing_vs_union else ""))
(out_dir / "missing_vs_secure_preferences.txt").write_text(
    "\n".join(missing_vs_secure) + ("\n" if missing_vs_secure else "")
)

with (out_dir / "missing_vs_secure_with_disable_reasons.tsv").open("w", encoding="utf-8") as file:
    file.write("extension_id\tdisable_reasons\n")
    for extension_id in missing_vs_secure:
        reasons = disable_reason_by_id.get(extension_id, [])
        file.write(f"{extension_id}\t{','.join(map(str, reasons))}\n")

print("✅ Chrome extension reconciliation complete")
print(f"Chrome root: {chrome_root}")
print(f"Target profile: {target_profile_name}")
print(f"last_used: {last_used}")
print(f"All-profile extension union: {len(all_union_ids)}")
print(f"Target profile filesystem extensions: {len(target_fs_ids)}")
print(f"Target profile Secure Preferences registry extensions: {len(target_secure_ids)}")
print(f"Missing (vs. all-profile union): {len(missing_vs_union)}")
print(f"Missing (vs. target profile registry): {len(missing_vs_secure)}")
if disable_reason_counter:
    reason_line = ", ".join(f"{key}:{value}" for key, value in sorted(disable_reason_counter.items()))
    print(f"disable_reasons summary: {reason_line}")
print(f"Output directory: {out_dir}")

if missing_vs_union:
    print("\n[Missing from target profile (vs. all-profile union)]")
    for extension_id in missing_vs_union:
        print(extension_id)

if missing_vs_secure:
    print("\n[Missing from target profile (vs. Secure Preferences registry)]")
    for extension_id in missing_vs_secure:
        reasons = disable_reason_by_id.get(extension_id, [])
        print(f"{extension_id}\tdisable_reasons={reasons}")
PY
