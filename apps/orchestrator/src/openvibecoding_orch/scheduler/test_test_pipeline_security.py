from __future__ import annotations

from pathlib import Path

from openvibecoding_orch.scheduler.test_pipeline import cleanup_test_artifacts, read_artifact_text


def test_read_artifact_text_blocks_path_traversal(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    content = read_artifact_text(worktree, {"path": "../outside.txt"})

    assert content == ""


def test_read_artifact_text_rejects_symlink_target(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    symlink = worktree / "link.txt"
    symlink.symlink_to(outside)

    content = read_artifact_text(worktree, {"path": "link.txt"})

    assert content == ""


def test_cleanup_test_artifacts_does_not_delete_outside_file(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    outside = tmp_path / "outside.log"
    outside.write_text("keep", encoding="utf-8")

    report = {
        "commands": [
            {
                "stdout": {"path": "../outside.log"},
                "stderr": {"path": "../outside.log"},
            }
        ]
    }

    cleanup_test_artifacts(report, worktree)

    assert outside.exists()
    assert outside.read_text(encoding="utf-8") == "keep"
