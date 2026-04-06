import json
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = (
    "task_id",
    "status",
    "summary",
)


def _examples_root() -> Path:
    return Path(__file__).resolve().parents[3] / "contracts" / "examples"


def _failure_example_paths() -> list[Path]:
    return sorted(path for path in _examples_root().glob("*failure*.json") if path.is_file())


def _load_failure_examples() -> list[tuple[Path, dict[str, Any]]]:
    files = _failure_example_paths()
    assert files, "Expected failure contract samples under contracts/examples/*failure*.json"

    payloads: list[tuple[Path, dict[str, Any]]] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{path} is not valid JSON: {exc}") from exc

        assert isinstance(payload, dict), f"{path} must be a JSON object"
        payloads.append((path, payload))

    return payloads


def _normalized_name(path: Path) -> str:
    return path.stem.lower().replace("-", "_").replace(".", "_")


def _find_non_empty_string_by_key(node: Any, key: str) -> str | None:
    if isinstance(node, dict):
        for current_key, value in node.items():
            if current_key == key and isinstance(value, str) and value.strip():
                return value.strip()
            nested = _find_non_empty_string_by_key(value, key)
            if nested:
                return nested
        return None

    if isinstance(node, list):
        for item in node:
            nested = _find_non_empty_string_by_key(item, key)
            if nested:
                return nested

    return None


def _has_semantic_text(payload: dict[str, Any], keyword_groups: tuple[tuple[str, ...], ...]) -> bool:
    candidates: list[str] = []
    for key in ("summary", "failure_reason"):
        value = payload.get(key)
        if isinstance(value, str):
            candidates.append(value.lower())

    if not candidates:
        candidates.append(json.dumps(payload, ensure_ascii=False).lower())

    text = " ".join(candidates)
    return any(all(keyword in text for keyword in group) for group in keyword_groups)


def test_failure_contract_examples_exist_and_are_valid_json() -> None:
    examples_root = _examples_root()
    assert examples_root.is_dir(), f"Missing examples directory: {examples_root}"
    _load_failure_examples()


def test_failure_contract_examples_have_required_fields_and_failed_status() -> None:
    for path, payload in _load_failure_examples():
        missing_fields = [field for field in REQUIRED_FIELDS if field not in payload]
        assert not missing_fields, f"{path} missing required fields: {missing_fields}"
        assert payload["status"] == "FAILED", f"{path} status must be FAILED, got: {payload['status']}"

        failure_reason = payload.get("failure_reason")
        failure = payload.get("failure")
        failure_message = failure.get("message") if isinstance(failure, dict) else None
        assert isinstance(failure_reason, str) or isinstance(failure_message, str), (
            f"{path} must provide failure_reason or failure.message"
        )

        evidence_refs = payload.get("evidence_refs")
        artifacts = payload.get("artifacts")
        assert isinstance(evidence_refs, dict) or isinstance(artifacts, list), (
            f"{path} must provide evidence_refs or artifacts"
        )


def test_failure_contract_examples_include_denied_sampling_gate_timeout_semantics() -> None:
    payloads = _load_failure_examples()

    denied_samples = [(path, payload) for path, payload in payloads if "denied" in _normalized_name(path)]
    sampling_gate_samples = [
        (path, payload)
        for path, payload in payloads
        if "sampling" in _normalized_name(path) and "gate" in _normalized_name(path)
    ]
    timeout_samples = [(path, payload) for path, payload in payloads if "timeout" in _normalized_name(path)]

    assert denied_samples, "Expected at least one denied failure sample (filename contains 'denied')"
    assert sampling_gate_samples, "Expected at least one sampling_gate failure sample"
    assert timeout_samples, "Expected at least one timeout failure sample"

    for path, payload in denied_samples:
        denied_reason = _find_non_empty_string_by_key(payload, "denied_reason")
        has_denied_semantic = bool(denied_reason) or _has_semantic_text(payload, (("denied",), ("deny",)))
        assert has_denied_semantic, f"{path} must include denied_reason field or denied semantic text"

    for path, payload in sampling_gate_samples:
        assert _has_semantic_text(payload, (("sampling", "gate"), ("sample", "gate"))), (
            f"{path} must include sampling gate failure semantic text in summary/failure_reason"
        )

    for path, payload in timeout_samples:
        assert _has_semantic_text(payload, (("timeout",), ("timed", "out"))), (
            f"{path} must include timeout failure semantic text in summary/failure_reason"
        )
