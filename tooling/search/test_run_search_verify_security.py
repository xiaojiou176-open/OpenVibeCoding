from __future__ import annotations

import pytest

from tooling.search.run_search_verify import _require_safe_run_id


@pytest.mark.parametrize("bad_run_id", ["", "../bad", "run/../bad", "/tmp/run", "..", "run..id"])
def test_require_safe_run_id_rejects_unsafe_values(bad_run_id: str) -> None:
    with pytest.raises(SystemExit):
        _require_safe_run_id(bad_run_id)


def test_require_safe_run_id_accepts_expected_value() -> None:
    assert _require_safe_run_id("run_20260225_abcdef") == "run_20260225_abcdef"
