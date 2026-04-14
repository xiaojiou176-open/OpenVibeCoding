from openvibecoding_orch.gates.network_gate import validate_network_policy, requires_network_items


def test_validate_network_policy_invalid() -> None:
    result = validate_network_policy("weird", requires_network=True)
    assert result["ok"] is False
    assert result["reason"] == "invalid network policy"


def test_validate_network_policy_on_request_approved(monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_NETWORK_APPROVED", "true")
    result = validate_network_policy("on-request", requires_network=True)
    assert result["ok"] is True


def test_validate_network_policy_on_request_denied(monkeypatch) -> None:
    monkeypatch.delenv("OPENVIBECODING_NETWORK_APPROVED", raising=False)
    result = validate_network_policy("on-request", requires_network=True)
    assert result["ok"] is False
    assert result["reason"] == "network access requires approval"


def test_validate_network_policy_override() -> None:
    result = validate_network_policy("on-request", requires_network=True, approved_override=True)
    assert result["ok"] is True


def test_requires_network_items() -> None:
    assert requires_network_items([None, "", [], 0]) is False
    assert requires_network_items([None, [], "x"]) is True
