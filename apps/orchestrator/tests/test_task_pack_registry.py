from __future__ import annotations

from cortexpilot_orch.planning import intake as intake_mod


def test_task_pack_registry_includes_public_templates() -> None:
    registry = intake_mod._task_pack_registry()
    assert {"news_digest", "topic_brief", "page_brief"}.issubset(set(registry.keys()))
    assert registry["news_digest"]["evidence_contract"]["primary_report"] == "news_digest_result.json"


def test_supported_task_templates_reads_registry() -> None:
    supported = intake_mod._supported_task_templates()
    assert "news_digest" in supported
    assert "topic_brief" in supported
    assert "page_brief" in supported
