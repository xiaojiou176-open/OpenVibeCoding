import hashlib
import json
from pathlib import Path


def _output_schema_artifacts(role: str = "worker") -> list[dict]:
    schema_root = Path(__file__).resolve().parents[4] / "schemas"
    schema_name = "agent_task_result.v1.json"
    if role.lower() in {"reviewer"}:
        schema_name = "review_report.v1.json"
    if role.lower() in {"test", "test_runner"}:
        schema_name = "test_report.v1.json"
    schema_path = schema_root / schema_name
    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    return [
        {
            "name": f"output_schema.{role.lower()}",
            "uri": f"schemas/{schema_name}",
            "sha256": sha,
        }
    ]


def _write_manifest(run_dir: Path, payload: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_contract(run_dir: Path, payload: dict) -> None:
    (run_dir / "contract.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_events(run_dir: Path, lines: list[str]) -> None:
    (run_dir / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_lock(lock_dir: Path, lock_id: str, run_id: str, path: str, ts: str) -> None:
    lock_dir.mkdir(parents=True, exist_ok=True)
    content = "\n".join([f"run_id={run_id}", f"path={path}", f"ts={ts}"])
    (lock_dir / f"{lock_id}.lock").write_text(content, encoding="utf-8")


def _write_report(run_dir: Path, name: str, payload: object) -> None:
    reports_dir = run_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        (reports_dir / name).write_text(payload, encoding="utf-8")
    else:
        (reports_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def _write_artifact(run_dir: Path, name: str, payload: object) -> None:
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        (artifacts_dir / name).write_text(payload, encoding="utf-8")
    else:
        (artifacts_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def _write_intake_bundle(
    runtime_root: Path,
    intake_id: str,
    intake_payload: dict,
    response_payload: dict,
    intake_events: list[dict],
) -> None:
    intake_dir = runtime_root / "intakes" / intake_id
    intake_dir.mkdir(parents=True, exist_ok=True)
    (intake_dir / "intake.json").write_text(json.dumps(intake_payload), encoding="utf-8")
    (intake_dir / "response.json").write_text(json.dumps(response_payload), encoding="utf-8")
    (intake_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(item) for item in intake_events) + "\n",
        encoding="utf-8",
    )
