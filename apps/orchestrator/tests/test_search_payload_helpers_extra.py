import json
from pathlib import Path

from cortexpilot_orch.api import search_payload_helpers


def test_extract_search_queries_skips_invalid_entries_then_reads_list(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps(["alpha", " ", 2]), encoding="utf-8")

    contract = {
        "inputs": {
            "artifacts": [
                "bad-entry",
                {"name": "other.json", "uri": str(valid)},
                {"name": "search_requests.json", "uri": " "},
                {"name": "search_requests.json", "uri": str(tmp_path / "missing.json")},
                {"name": "search_requests.json", "uri": str(broken)},
                {"name": "search_requests.json", "uri": str(valid)},
            ]
        }
    }

    assert search_payload_helpers.extract_search_queries(contract) == ["alpha", "2"]


def test_extract_search_queries_handles_dict_query_forms_and_non_list_raw(tmp_path: Path) -> None:
    raw_dict = tmp_path / "raw_dict.json"
    raw_dict.write_text(json.dumps({"query": {"bad": True}}), encoding="utf-8")
    assert (
        search_payload_helpers.extract_search_queries(
            {"inputs": {"artifacts": [{"name": "search_queries.json", "uri": str(raw_dict)}]}}
        )
        == []
    )

    one_query = tmp_path / "one_query.json"
    one_query.write_text(json.dumps({"query": "single"}), encoding="utf-8")
    assert (
        search_payload_helpers.extract_search_queries(
            {"inputs": {"artifacts": [{"name": "search_queries.json", "uri": str(one_query)}]}}
        )
        == ["single"]
    )

    many_queries = tmp_path / "many_queries.json"
    many_queries.write_text(json.dumps({"queries": ["a", "", "b"]}), encoding="utf-8")
    assert (
        search_payload_helpers.extract_search_queries(
            {"inputs": {"artifacts": [{"name": "search_queries.json", "uri": str(many_queries)}]}}
        )
        == ["a", "b"]
    )

    assert search_payload_helpers.extract_search_queries({"inputs": {"artifacts": "bad"}}) == []
    assert search_payload_helpers.extract_search_queries("bad-contract") == []


def test_build_search_payload_reads_expected_artifacts_and_reports() -> None:
    calls: list[tuple[str, str]] = []

    def _read_artifact(run_id: str, name: str) -> object:
        calls.append(("artifact", name))
        return f"{run_id}:{name}"

    def _read_report(run_id: str, name: str) -> object:
        calls.append(("report", name))
        return {"id": run_id, "name": name}

    payload = search_payload_helpers.build_search_payload(
        "run-x",
        read_artifact_fn=_read_artifact,
        read_report_fn=_read_report,
    )

    assert payload["run_id"] == "run-x"
    assert payload["raw"] == "run-x:search_results.json"
    assert payload["verification_ai"] == "run-x:verification_ai.json"
    assert payload["evidence_bundle"] == {"id": "run-x", "name": "evidence_bundle.json"}
    assert ("artifact", "search_results.jsonl") in calls
    assert ("report", "evidence_bundle.json") in calls
