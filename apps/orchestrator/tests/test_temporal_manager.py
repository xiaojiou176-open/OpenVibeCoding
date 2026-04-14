from openvibecoding_orch.temporal.manager import notify_run_started, notify_run_completed


def test_temporal_notify_skipped(monkeypatch) -> None:
    monkeypatch.delenv("OPENVIBECODING_TEMPORAL_ENABLED", raising=False)
    result = notify_run_started("run-1", {})
    assert result["ok"] is True
    assert result.get("skipped") is True


def test_temporal_notify_missing_lib(monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_ENABLED", "1")
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_ADDRESS", "127.0.0.1:1")
    result = notify_run_completed("run-2", {})
    assert result["ok"] is False
    assert any(
        token in result["error"]
        for token in ["temporalio not installed", "Connection refused", "Server connection error"]
    )


def test_temporal_manager_helpers(monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_ACTIVITY", "1")
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_ENABLED", "1")
    assert notify_run_started("run-x", {}).get("skipped") is True

    monkeypatch.delenv("OPENVIBECODING_TEMPORAL_ACTIVITY", raising=False)
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_ENABLED", "1")
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_ADDRESS", "127.0.0.1:7233")
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_NAMESPACE", "openvibecoding")

    import sys
    import types

    temporal_pkg = types.ModuleType("temporalio")
    temporal_client_mod = types.ModuleType("temporalio.client")

    class _FakeClient:
        @staticmethod
        async def connect(address: str, namespace: str):
            return {"address": address, "namespace": namespace}

    temporal_client_mod.Client = _FakeClient
    monkeypatch.setitem(sys.modules, "temporalio", temporal_pkg)
    monkeypatch.setitem(sys.modules, "temporalio.client", temporal_client_mod)

    started = notify_run_started("run-y", {})
    assert started["ok"] is True
    assert started["address"] == "127.0.0.1:7233"
    assert started["namespace"] == "openvibecoding"

    completed = notify_run_completed("run-z", {})
    assert completed["ok"] is True
    assert completed["run_id"] == "run-z"


def test_temporal_manager_import_and_connect_error_paths(monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_ENABLED", "1")
    monkeypatch.delenv("OPENVIBECODING_TEMPORAL_ACTIVITY", raising=False)
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_ADDRESS", "127.0.0.1:1")

    import sys

    sys.modules.pop("temporalio.client", None)
    missing_started = notify_run_started("run-missing", {})
    assert missing_started["ok"] is False
    assert any(
        token in missing_started["error"]
        for token in ["temporalio not installed", "Connection refused", "Server connection error"]
    )

    missing_completed = notify_run_completed("run-missing2", {})
    assert missing_completed["ok"] is False
    assert any(
        token in missing_completed["error"]
        for token in ["temporalio not installed", "Connection refused", "Server connection error"]
    )

    import types

    temporal_pkg = types.ModuleType("temporalio")
    temporal_client_mod = types.ModuleType("temporalio.client")

    class _BrokenClient:
        @staticmethod
        async def connect(address: str, namespace: str):
            raise RuntimeError("connect boom")

    temporal_client_mod.Client = _BrokenClient
    monkeypatch.setitem(sys.modules, "temporalio", temporal_pkg)
    monkeypatch.setitem(sys.modules, "temporalio.client", temporal_client_mod)

    started = notify_run_started("run-connect", {})
    assert started["ok"] is False
    assert "connect boom" in started["error"]


def test_temporal_manager_forced_import_error(monkeypatch) -> None:
    import builtins

    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_ENABLED", "1")
    monkeypatch.delenv("OPENVIBECODING_TEMPORAL_ACTIVITY", raising=False)

    real_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name == "temporalio.client":
            raise ImportError("forced missing temporal client")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    started = notify_run_started("run-import-err", {})
    completed = notify_run_completed("run-import-err", {})

    assert started["ok"] is False
    assert completed["ok"] is False
    assert "temporalio not installed" in started["error"]
    assert "temporalio not installed" in completed["error"]
