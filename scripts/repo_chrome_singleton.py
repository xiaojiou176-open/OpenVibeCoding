from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tooling.browser.repo_chrome_singleton import (
    DEFAULT_PROFILE_DIRECTORY,
    default_cdp_host,
    default_cdp_port,
    default_repo_chrome_user_data_dir,
    default_source_chrome_root,
    ensure_repo_chrome_singleton,
    migrate_default_chrome_profile,
    repo_chrome_status,
    resolve_real_chrome_executable_path,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the OpenVibeCoding repo-owned Chrome singleton root and CDP instance."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate = subparsers.add_parser("migrate", help="Copy the named Chrome profile into the repo-owned root once.")
    migrate.add_argument("--source-root", default=str(default_source_chrome_root()))
    migrate.add_argument("--source-profile-name", default="openvibecoding")
    migrate.add_argument("--target-root", default=str(default_repo_chrome_user_data_dir()))
    migrate.add_argument("--target-profile-directory", default=DEFAULT_PROFILE_DIRECTORY)
    migrate.add_argument("--target-display-name", default="openvibecoding")
    migrate.add_argument("--reseed", action="store_true")

    launch = subparsers.add_parser("launch", help="Attach to or launch the repo-owned Chrome singleton.")
    launch.add_argument("--target-root", default=str(default_repo_chrome_user_data_dir()))
    launch.add_argument("--profile-name", default="openvibecoding")
    launch.add_argument("--cdp-host", default=default_cdp_host())
    launch.add_argument("--cdp-port", type=int, default=default_cdp_port())
    launch.add_argument("--chrome-path", default="")
    launch.add_argument("--timeout-sec", type=float, default=15.0)

    status = subparsers.add_parser("status", help="Report the repo-owned Chrome singleton state.")
    status.add_argument("--target-root", default=str(default_repo_chrome_user_data_dir()))
    status.add_argument("--profile-name", default="openvibecoding")
    status.add_argument("--cdp-host", default=default_cdp_host())
    status.add_argument("--cdp-port", type=int, default=default_cdp_port())

    return parser


def _print_payload(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "migrate":
        payload = migrate_default_chrome_profile(
            source_root=Path(args.source_root).expanduser(),
            source_profile_name=args.source_profile_name,
            target_root=Path(args.target_root).expanduser(),
            target_profile_directory=args.target_profile_directory,
            target_display_name=args.target_display_name,
            reseed=bool(args.reseed),
        )
        _print_payload(payload)
        return 0

    if args.command == "launch":
        chrome_path = args.chrome_path.strip() or resolve_real_chrome_executable_path()
        payload = ensure_repo_chrome_singleton(
            chrome_executable_path=chrome_path,
            user_data_dir=Path(args.target_root).expanduser(),
            profile_name=args.profile_name,
            cdp_host=args.cdp_host,
            cdp_port=int(args.cdp_port),
            requested_headless=False,
            cdp_timeout_sec=float(args.timeout_sec),
        ).to_metadata()
        _print_payload(payload)
        return 0

    if args.command == "status":
        payload = repo_chrome_status(
            user_data_dir=Path(args.target_root).expanduser(),
            profile_name=args.profile_name,
            cdp_host=args.cdp_host,
            cdp_port=int(args.cdp_port),
        )
        _print_payload(payload)
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
