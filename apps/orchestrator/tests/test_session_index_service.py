from pathlib import Path

from cortexpilot_orch.services.session_index_service import SessionIndexService


def test_session_index_list_and_read_files(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    service = SessionIndexService(runtime_root)

    assert service.list_session_ids() == []
    assert service.read_session_files("missing") == ({}, {}, [])

    intakes_root = runtime_root / "intakes"
    (intakes_root / "b-session").mkdir(parents=True, exist_ok=True)
    (intakes_root / "a-session").mkdir(parents=True, exist_ok=True)
    (intakes_root / "README.txt").write_text("ignore", encoding="utf-8")
    assert service.list_session_ids() == ["a-session", "b-session"]

    target = intakes_root / "a-session"
    (target / "intake.json").write_text('["not-a-dict"]', encoding="utf-8")
    (target / "response.json").write_text("{bad-json", encoding="utf-8")
    (target / "events.jsonl").write_text(
        "\n".join(
            [
                "",
                '{"event":"INTAKE_RUN","run_id":"r-1"}',
                "42",
                "{broken-json",
            ]
        ),
        encoding="utf-8",
    )

    intake, response, events = service.read_session_files("a-session")
    assert intake == {}
    assert response == {}
    assert events == [
        {"event": "INTAKE_RUN", "run_id": "r-1"},
        {"raw": "{broken-json"},
    ]


def test_session_index_derive_source_and_bindings(tmp_path: Path) -> None:
    service = SessionIndexService(tmp_path)

    assert (
        service.derive_session_source(
            {"session_source": "  API  "},
            {"source": "response"},
        )
        == "api"
    )
    assert (
        service.derive_session_source(
            {"session_source": "  "},
            {"origin": "  Dashboard "},
        )
        == "dashboard"
    )
    assert service.derive_session_source({}, {}) == "intake"

    bindings = service.derive_bindings(
        pm_session_id="pm-1",
        response={
            "chain_run_id": " primary-run ",
            "chain_run_ids": ["child-1", " child-1 ", None, "", "child-2"],
            "updated_at": " 2026-02-10T10:00:00Z ",
        },
        intake_events=[
            {"event": "INTAKE_RUN", "run_id": " child-1 ", "ts": " 2026-02-10T09:00:00Z "},
            {"event": "INTAKE_CHAIN_RUN", "run_id": "primary-run", "ts": "2026-02-10T08:00:00Z"},
            {"event": "INTAKE_RUN", "run_id": 123, "ts": "ignored"},
            {"event": "UNKNOWN", "run_id": "ignored"},
            "not-a-dict",  # type: ignore[list-item]
        ],
    )

    assert [(item.run_id, item.binding_type, item.bound_at) for item in bindings] == [
        ("child-1", "child", "2026-02-10T09:00:00Z"),
        ("primary-run", "primary", "2026-02-10T08:00:00Z"),
        ("child-2", "child", "2026-02-10T10:00:00Z"),
    ]


def test_session_index_read_jsonl_missing_file() -> None:
    assert SessionIndexService._read_jsonl(Path("/tmp/non-existent-session-events.jsonl")) == []
