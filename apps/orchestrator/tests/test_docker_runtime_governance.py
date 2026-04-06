from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "cortexpilot_docker_runtime_governance",
        REPO_ROOT / "scripts" / "docker_runtime_governance.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_docker_runtime_report_tracks_build_cache_and_skipped_active(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "_docker_available", lambda: True)
    monkeypatch.setattr(module, "_docker_daemon_available", lambda: True)
    monkeypatch.setattr(
        module,
        "_docker_image_info",
        lambda name: {
            "name": name,
            "id": f"id-{name}",
            "exists": True,
            "size_bytes": 100 if "core" in name else 200,
            "size_human": "n/a",
            "active_container_ids": ["ctr-active"] if "core" in name else [],
            "active_container_count": 1 if "core" in name else 0,
            "stopped_container_ids": ["ctr-stop"] if "core" in name else [],
            "stopped_container_count": 1 if "core" in name else 0,
        },
    )
    monkeypatch.setattr(
        module,
        "_docker_container_entries",
        lambda container_ids, image_name: [
            {"id": item, "image_name": image_name, "size_bytes": 50, "size_human": "50 B"}
            for item in container_ids
        ],
    )
    monkeypatch.setattr(
        module,
        "_docker_volume_entries",
        lambda prefix: [{"name": f"{prefix}-vol", "mountpoint": "/tmp/x", "size_bytes": 30, "size_human": "30 B"}],
    )
    monkeypatch.setattr(
        module,
        "_build_cache_entries",
        lambda image_names: [
            {"image_name": image_names[0], "path": "/tmp/core-cache", "exists": True, "size_bytes": 70, "size_human": "70 B"},
            {
                "image_name": image_names[1],
                "path": "/tmp/desktop-cache",
                "exists": True,
                "size_bytes": 90,
                "size_human": "90 B",
            },
        ],
    )
    monkeypatch.setattr(module, "_docker_system_df_summary", lambda: {"available": True, "raw": "summary"})

    report = module.build_docker_runtime_report(
        mode="aggressive",
        dry_run=True,
        include_image=True,
        include_volumes=True,
        image_name="cortexpilot-ci-core:local",
        desktop_image_name="cortexpilot-ci-desktop-native:local",
        volume_prefix="cortexpilot",
    )

    assert report["status"] == "ok"
    assert report["plan"]["removable_build_cache_paths"] == ["/tmp/core-cache", "/tmp/desktop-cache"]
    assert report["plan"]["removable_image_names"] == ["cortexpilot-ci-desktop-native:local"]
    assert report["plan"]["skipped_active"] == [
        {"kind": "image", "name": "cortexpilot-ci-core:local", "reason": "active_container"}
    ]
    assert report["managed_totals"]["build_cache_bytes"] == 160
    assert report["plan"]["planned_reclaim_bytes"] == 440


def test_build_docker_runtime_report_apply_records_removed_build_cache(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "_docker_available", lambda: True)
    monkeypatch.setattr(module, "_docker_daemon_available", lambda: True)
    monkeypatch.setattr(
        module,
        "_docker_image_info",
        lambda name: {
            "name": name,
            "id": "",
            "exists": False,
            "size_bytes": 0,
            "size_human": "0 B",
            "active_container_ids": [],
            "active_container_count": 0,
            "stopped_container_ids": [],
            "stopped_container_count": 0,
        },
    )
    monkeypatch.setattr(module, "_docker_container_entries", lambda container_ids, image_name: [])
    monkeypatch.setattr(module, "_docker_volume_entries", lambda prefix: [])
    cache_dir = tmp_path / "docker-buildx-cache" / "cortexpilot-ci-core-local"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "marker.txt").write_text("cache", encoding="utf-8")
    monkeypatch.setattr(
        module,
        "_build_cache_entries",
        lambda image_names: [
            {
                "image_name": image_names[0],
                "path": str(cache_dir),
                "exists": True,
                "size_bytes": 5,
                "size_human": "5 B",
            },
            {"image_name": image_names[1], "path": str(tmp_path / "missing"), "exists": False, "size_bytes": 0, "size_human": "0 B"},
        ],
    )
    monkeypatch.setattr(module, "_docker_system_df_summary", lambda: {"available": True, "raw": "summary"})

    report = module.build_docker_runtime_report(
        mode="aggressive",
        dry_run=False,
        include_image=False,
        include_volumes=False,
        image_name="cortexpilot-ci-core:local",
        desktop_image_name="cortexpilot-ci-desktop-native:local",
        volume_prefix="cortexpilot",
    )

    assert report["result"]["removed"]["build_caches"] == [str(cache_dir)]
    assert report["result"]["reclaimed_bytes"] == 5
    assert cache_dir.exists() is False


def test_docker_runtime_governance_cli_writes_report_when_docker_is_missing(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "_docker_available", lambda: False)
    report_path = tmp_path / "docker_runtime.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docker_runtime_governance.py",
            "--dry-run",
            "--report",
            str(report_path),
        ],
    )

    assert module.main() == 0
    stored = json.loads(report_path.read_text(encoding="utf-8"))
    assert stored["status"] == "docker_missing"
