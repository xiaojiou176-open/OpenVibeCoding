from openvibecoding_orch.observability.codex_event_parser import parse_codex_event_line


def test_parse_codex_event_json():
    line = '{"type":"item","threadId":"thread-1","sessionId":"sess-1","id":"item-1"}'
    result = parse_codex_event_line(line, codex_version="1.2.3")
    assert result.is_json is True
    assert result.event_type == "item"
    assert result.thread_id == "thread-1"
    assert result.session_id == "sess-1"
    assert result.item_id == "item-1"
    assert result.codex_version == "1.2.3"
    context = result.to_event_context()
    assert context["payload"]["threadId"] == "thread-1"


def test_parse_codex_event_non_json():
    line = "not-json"
    result = parse_codex_event_line(line)
    assert result.is_json is False
    assert "non_json" in result.errors
    assert result.to_codex_jsonl().startswith("{")


def test_parse_codex_event_non_object_payload():
    line = '["a", "b"]'
    result = parse_codex_event_line(line)
    assert result.is_json is True
    assert "payload_not_object" in result.warnings
    assert result.payload["value"] == ["a", "b"]


def test_parse_codex_event_empty_and_nested():
    empty = parse_codex_event_line("")
    assert empty.is_json is False
    assert "empty_line" in empty.errors
    context = empty.to_event_context()
    assert context["raw"] == ""

    nested = parse_codex_event_line('{"payload": {"event": "item", "threadId": "t1", "sessionId": "s1", "id": "i1"}}')
    assert nested.event_type == "item"
    assert nested.thread_id == "t1"
    assert nested.session_id == "s1"
    assert nested.item_id == "i1"
