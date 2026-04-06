from __future__ import annotations

from cortexpilot_orch.scheduler import task_execution_runtime_helpers as runtime_helpers


def test_coerce_optional_bool_parses_string_false_without_reversal() -> None:
    assert runtime_helpers._coerce_optional_bool("false") is False
    assert runtime_helpers._coerce_optional_bool("0") is False
    assert runtime_helpers._coerce_optional_bool("no") is False


def test_coerce_optional_bool_parses_truthy_and_unknown_values() -> None:
    assert runtime_helpers._coerce_optional_bool("true") is True
    assert runtime_helpers._coerce_optional_bool("1") is True
    assert runtime_helpers._coerce_optional_bool(True) is True
    assert runtime_helpers._coerce_optional_bool(False) is False
    assert runtime_helpers._coerce_optional_bool("unknown") is None


def test_coerce_optional_bool_handles_numeric_and_non_scalar_values() -> None:
    assert runtime_helpers._coerce_optional_bool(1) is True
    assert runtime_helpers._coerce_optional_bool(0) is False
    assert runtime_helpers._coerce_optional_bool(0.0) is False
    assert runtime_helpers._coerce_optional_bool(object()) is None
