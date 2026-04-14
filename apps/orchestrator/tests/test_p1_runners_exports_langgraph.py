from __future__ import annotations

import pkgutil
import pytest

import openvibecoding_orch.runners as runners


def test_runners_exports_match_discoverable_submodules() -> None:
    expected_exports = {
        module_info.name
        for module_info in pkgutil.iter_modules(runners.__path__)
        if not module_info.name.startswith("_")
    }
    assert set(runners.__all__) == expected_exports
    assert "agents_contract_flow" in expected_exports
    assert "agents_stream_flow" in expected_exports


def test_runners_lazy_export_resolves_flow_modules() -> None:
    contract_flow = runners.agents_contract_flow
    stream_flow = runners.agents_stream_flow

    assert contract_flow.__name__ == "openvibecoding_orch.runners.agents_contract_flow"
    assert stream_flow.__name__ == "openvibecoding_orch.runners.agents_stream_flow"


def test_runners_dir_lists_discovered_modules_and_invalid_attr_errors() -> None:
    exported = dir(runners)
    assert "agents_binding" in exported
    with pytest.raises(AttributeError):
        getattr(runners, "missing_runner_module")
