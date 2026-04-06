#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / ".runtime-cache" / "cortexpilot" / "reports" / "space_governance" / "docker_runtime.json"
DEFAULT_IMAGE = os.environ.get("CORTEXPILOT_DOCKER_RUNTIME_IMAGE", "cortexpilot-ci-core:local")
DEFAULT_DESKTOP_IMAGE = os.environ.get("CORTEXPILOT_DOCKER_DESKTOP_NATIVE_IMAGE", "cortexpilot-ci-desktop-native:local")
DEFAULT_VOLUME_PREFIX = os.environ.get("CORTEXPILOT_DOCKER_VOLUME_PREFIX", "cortexpilot")


def _human_size(num_bytes: int) -> str:
    value = float(max(num_bytes, 0))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{int(num_bytes)} B"


def _machine_cache_root() -> Path:
    explicit = os.environ.get("CORTEXPILOT_MACHINE_CACHE_ROOT", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    runner_temp = os.environ.get("RUNNER_TEMP", "").strip()
    ci = os.environ.get("CI", "").strip().lower() in {"1", "true", "yes", "on"} or os.environ.get(
        "GITHUB_ACTIONS", ""
    ).strip().lower() == "true"
    if ci and runner_temp:
        return Path(runner_temp) / "cortexpilot-machine-cache"
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME", "").strip()
    if xdg_cache_home:
        return Path(xdg_cache_home).expanduser() / "cortexpilot"
    return Path.home() / ".cache" / "cortexpilot"


def _docker_buildx_cache_root() -> Path:
    return _machine_cache_root() / "docker-buildx-cache"


def _sanitize_image_key(image_name: str) -> str:
    sanitized = image_name.translate(str.maketrans({":": "-", "/": "-", "@": "-"}))
    sanitized = "".join(ch for ch in sanitized if ch.isalnum() or ch in "._-").strip()
    return sanitized or "image-cache"


def _docker_buildx_cache_dir(image_name: str) -> Path:
    return _docker_buildx_cache_root() / _sanitize_image_key(image_name)


def _run(
    args: list[str],
    *,
    check: bool = False,
    capture_output: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, check=check, capture_output=capture_output, text=text)


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _docker_daemon_available() -> bool:
    if not _docker_available():
        return False
    return _run(["docker", "info"]).returncode == 0


def _bytes_from_du(path: Path) -> int:
    if not path.exists():
        return 0
    proc = _run(["du", "-sk", str(path)])
    if proc.returncode != 0:
        return 0
    first = (proc.stdout.strip().split() or ["0"])[0]
    try:
        return int(first) * 1024
    except ValueError:
        return 0


def _split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _docker_lines(args: list[str]) -> list[str]:
    proc = _run(args)
    if proc.returncode != 0:
        return []
    return _split_lines(proc.stdout)


def _docker_image_info(image_name: str) -> dict[str, Any]:
    inspect = _run(["docker", "image", "inspect", image_name, "--format", "{{.Id}}\t{{.Size}}"])
    image_id = ""
    size_bytes = 0
    if inspect.returncode == 0:
        parts = inspect.stdout.strip().split("\t")
        if parts:
            image_id = parts[0]
        if len(parts) > 1:
            try:
                size_bytes = int(parts[1])
            except ValueError:
                size_bytes = 0
    active_ids = _docker_lines(["docker", "ps", "-q", "--filter", f"ancestor={image_name}"])
    stopped_ids = _docker_lines(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            f"ancestor={image_name}",
            "--filter",
            "status=created",
            "--filter",
            "status=exited",
            "--filter",
            "status=dead",
        ]
    )
    return {
        "name": image_name,
        "id": image_id,
        "exists": bool(image_id),
        "size_bytes": size_bytes,
        "size_human": _human_size(size_bytes),
        "active_container_ids": active_ids,
        "active_container_count": len(active_ids),
        "stopped_container_ids": stopped_ids,
        "stopped_container_count": len(stopped_ids),
    }


def _docker_container_size_bytes(container_id: str) -> int:
    proc = _run(["docker", "container", "inspect", "--size", container_id, "--format", "{{.SizeRootFs}}"])
    if proc.returncode != 0:
        return 0
    try:
        return int(proc.stdout.strip() or "0")
    except ValueError:
        return 0


def _docker_container_entries(container_ids: list[str], *, image_name: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for container_id in container_ids:
        size_bytes = _docker_container_size_bytes(container_id)
        entries.append(
            {
                "id": container_id,
                "image_name": image_name,
                "size_bytes": size_bytes,
                "size_human": _human_size(size_bytes),
            }
        )
    return entries


def _docker_volume_entries(volume_prefix: str) -> list[dict[str, Any]]:
    volumes: list[dict[str, Any]] = []
    for name in _docker_lines(["docker", "volume", "ls", "--format", "{{.Name}}"]):
        if not name.startswith(volume_prefix):
            continue
        mount_proc = _run(["docker", "volume", "inspect", name, "--format", "{{.Mountpoint}}"])
        mountpoint = mount_proc.stdout.strip() if mount_proc.returncode == 0 else ""
        mount_path = Path(mountpoint) if mountpoint else None
        size_bytes = _bytes_from_du(mount_path) if mount_path else 0
        volumes.append(
            {
                "name": name,
                "mountpoint": mountpoint,
                "size_bytes": size_bytes,
                "size_human": _human_size(size_bytes),
            }
        )
    return volumes


def _build_cache_entries(image_names: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for image_name in image_names:
        path = _docker_buildx_cache_dir(image_name)
        size_bytes = _bytes_from_du(path)
        entries.append(
            {
                "image_name": image_name,
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": size_bytes,
                "size_human": _human_size(size_bytes),
            }
        )
    return entries


def _docker_system_df_summary() -> dict[str, Any]:
    proc = _run(["docker", "system", "df"])
    return {
        "available": proc.returncode == 0,
        "raw": proc.stdout.strip() if proc.returncode == 0 else proc.stderr.strip(),
    }


def _remove_path(path: Path) -> bool:
    if not path.exists():
        return False
    shutil.rmtree(path)
    return True


def _write_report(payload: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_docker_runtime_report(
    *,
    mode: str,
    dry_run: bool,
    include_image: bool,
    include_volumes: bool,
    image_name: str,
    desktop_image_name: str,
    volume_prefix: str,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {
        "generated_at": generated_at,
        "mode": mode,
        "dry_run": dry_run,
        "docker_available": _docker_available(),
        "docker_daemon_available": False,
        "image_name": image_name,
        "desktop_image_name": desktop_image_name,
        "volume_prefix": volume_prefix,
    }
    if not report["docker_available"]:
        report["status"] = "docker_missing"
        return report
    if not _docker_daemon_available():
        report["status"] = "daemon_unavailable"
        return report

    report["docker_daemon_available"] = True
    report["status"] = "ok"

    image_infos = [_docker_image_info(image_name), _docker_image_info(desktop_image_name)]
    stopped_container_entries: list[dict[str, Any]] = []
    for item in image_infos:
        stopped_container_entries.extend(
            _docker_container_entries(item["stopped_container_ids"], image_name=item["name"])
        )
    volume_entries = _docker_volume_entries(volume_prefix)
    build_cache_entries = _build_cache_entries([image_name, desktop_image_name])

    unique_image_sizes: dict[str, int] = {
        item["id"]: int(item["size_bytes"])
        for item in image_infos
        if item.get("id")
    }
    managed_total_bytes = (
        sum(unique_image_sizes.values())
        + sum(int(item["size_bytes"]) for item in stopped_container_entries)
        + sum(int(item["size_bytes"]) for item in volume_entries)
        + sum(int(item["size_bytes"]) for item in build_cache_entries)
    )

    removable_containers = [item["id"] for item in stopped_container_entries]
    removable_build_caches = [item for item in build_cache_entries if item["exists"] and mode == "aggressive"]
    removable_images: list[dict[str, Any]] = []
    skipped_active: list[dict[str, Any]] = []
    if mode == "aggressive" and include_image:
        for item in image_infos:
            if not item["exists"]:
                continue
            if item["active_container_count"] > 0:
                skipped_active.append(
                    {
                        "kind": "image",
                        "name": item["name"],
                        "reason": "active_container",
                    }
                )
                continue
            removable_images.append(item)
    removable_volumes = volume_entries if mode == "aggressive" and include_volumes else []

    planned_reclaim_bytes = (
        sum(int(item["size_bytes"]) for item in stopped_container_entries)
        + sum(int(item["size_bytes"]) for item in removable_build_caches)
        + sum(int(item["size_bytes"]) for item in removable_images)
        + sum(int(item["size_bytes"]) for item in removable_volumes)
    )

    removed = {
        "containers": [],
        "build_caches": [],
        "images": [],
        "volumes": [],
    }
    reclaimed_bytes = 0

    if not dry_run:
        for item in stopped_container_entries:
            proc = _run(["docker", "rm", "-f", item["id"]])
            if proc.returncode == 0:
                removed["containers"].append(item["id"])
                reclaimed_bytes += int(item["size_bytes"])
        for item in removable_build_caches:
            path = Path(str(item["path"]))
            if _remove_path(path):
                removed["build_caches"].append(str(path))
                reclaimed_bytes += int(item["size_bytes"])
        for item in removable_images:
            proc = _run(["docker", "image", "rm", "-f", item["name"]])
            if proc.returncode == 0:
                removed["images"].append(item["name"])
                reclaimed_bytes += int(item["size_bytes"])
        for item in removable_volumes:
            proc = _run(["docker", "volume", "rm", "-f", item["name"]])
            if proc.returncode == 0:
                removed["volumes"].append(item["name"])
                reclaimed_bytes += int(item["size_bytes"])

    report["images"] = image_infos
    report["stopped_containers"] = stopped_container_entries
    report["volumes"] = volume_entries
    report["build_caches"] = build_cache_entries
    report["system_df"] = _docker_system_df_summary()
    report["plan"] = {
        "removable_container_ids": removable_containers,
        "removable_build_cache_paths": [str(item["path"]) for item in removable_build_caches],
        "removable_image_names": [item["name"] for item in removable_images],
        "removable_volume_names": [item["name"] for item in removable_volumes],
        "skipped_active": skipped_active,
        "planned_reclaim_bytes": planned_reclaim_bytes,
        "planned_reclaim_human": _human_size(planned_reclaim_bytes),
    }
    report["managed_totals"] = {
        "image_bytes": sum(unique_image_sizes.values()),
        "stopped_container_bytes": sum(int(item["size_bytes"]) for item in stopped_container_entries),
        "volume_bytes": sum(int(item["size_bytes"]) for item in volume_entries),
        "build_cache_bytes": sum(int(item["size_bytes"]) for item in build_cache_entries),
        "managed_total_bytes": managed_total_bytes,
        "managed_total_human": _human_size(managed_total_bytes),
    }
    report["result"] = {
        "removed": removed,
        "reclaimed_bytes": reclaimed_bytes,
        "reclaimed_human": _human_size(reclaimed_bytes),
        "remaining_bytes_estimate": max(managed_total_bytes - reclaimed_bytes, 0),
        "remaining_human_estimate": _human_size(max(managed_total_bytes - reclaimed_bytes, 0)),
        "skipped_active": skipped_active,
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit or prune repo-owned Docker runtime residue.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rebuildable", action="store_true")
    parser.add_argument("--aggressive", action="store_true")
    parser.add_argument("--include-image", action="store_true")
    parser.add_argument("--include-volumes", action="store_true")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--desktop-image", default=DEFAULT_DESKTOP_IMAGE)
    parser.add_argument("--volume-prefix", default=DEFAULT_VOLUME_PREFIX)
    return parser.parse_args()


def resolve_mode(args: argparse.Namespace) -> tuple[str, bool]:
    if args.rebuildable and args.aggressive:
        raise SystemExit("--rebuildable and --aggressive are mutually exclusive")
    if args.aggressive:
        return "aggressive", False
    if args.rebuildable:
        return "rebuildable", False
    return "dry-run", True


def main() -> int:
    args = parse_args()
    mode, implied_dry_run = resolve_mode(args)
    dry_run = bool(args.dry_run or implied_dry_run)
    report = build_docker_runtime_report(
        mode=mode,
        dry_run=dry_run,
        include_image=bool(args.include_image),
        include_volumes=bool(args.include_volumes),
        image_name=args.image,
        desktop_image_name=args.desktop_image,
        volume_prefix=args.volume_prefix,
    )
    report_path = Path(args.report).expanduser().resolve()
    _write_report(report, report_path)

    if report["status"] == "docker_missing":
        print("[docker-runtime] docker command not found")
        return 0
    if report["status"] == "daemon_unavailable":
        print("[docker-runtime] docker daemon unavailable")
        return 0

    print(
        "[docker-runtime] "
        f"mode={mode} dry_run={str(dry_run).lower()} "
        f"managed_total={report['managed_totals']['managed_total_human']} "
        f"planned_reclaim={report['plan']['planned_reclaim_human']} "
        f"reclaimed={report['result']['reclaimed_human']} "
        f"report={report_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
