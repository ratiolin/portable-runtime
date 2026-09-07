from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
)
from portable_runtime.interactions.feishu import provider as feishu_provider


class _FakeProcess:
    def __init__(self, returncode: int | None) -> None:
        self.returncode = returncode
        self.kill_called = False
        self.wait_calls = 0

    async def wait(self) -> int | None:
        self.wait_calls += 1
        return self.returncode

    def kill(self) -> None:
        self.kill_called = True


def _request(*, timeout_seconds: float | None = None) -> CapabilityRequest:
    return CapabilityRequest(
        id="request-feishu-test",
        capability="notify.send",
        instruction="test notification",
        timeout_seconds=timeout_seconds,
    )


def _context() -> InvocationContext:
    return InvocationContext(runtime_id="runtime-feishu-test")


def _script_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    create: bool = True,
) -> Path:
    monkeypatch.setattr(
        feishu_provider.Path,
        "home",
        classmethod(lambda _cls: tmp_path),
    )
    script = tmp_path / ".local" / "bin" / "feishu-notify.ps1"
    script.parent.mkdir(parents=True)
    if create:
        script.write_text("# test fixture", encoding="utf-8")
    return script


@pytest.mark.asyncio
async def test_feishu_missing_script_is_unavailable_and_not_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _script_path(monkeypatch, tmp_path, create=False)
    launch = AsyncMock()
    monkeypatch.setattr(feishu_provider.asyncio, "create_subprocess_exec", launch)

    result = await feishu_provider.FeishuNotificationProvider().invoke(
        _request(), _context()
    )

    assert isinstance(result, CapabilityResult)
    assert result.status == "unavailable"
    assert result.error == {
        "code": "feishu_script_missing",
        "type": "script_missing",
        "message": f"notification script not found: {tmp_path / '.local' / 'bin' / 'feishu-notify.ps1'}",
    }
    assert result.metadata["provider_accepted"] is False
    assert result.metadata["delivery_confirmed"] is False
    launch.assert_not_awaited()


@pytest.mark.asyncio
async def test_feishu_script_start_failure_is_failed_and_identifiable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _script_path(monkeypatch, tmp_path)
    launch = AsyncMock(side_effect=OSError("powershell unavailable"))
    monkeypatch.setattr(feishu_provider.asyncio, "create_subprocess_exec", launch)

    result = await feishu_provider.FeishuNotificationProvider().invoke(
        _request(), _context()
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error["code"] == "feishu_script_start_failed"
    assert result.error["type"] == "script_start_failed"
    assert "powershell unavailable" in result.error["message"]
    assert result.metadata["provider_accepted"] is False
    assert result.metadata["delivery_confirmed"] is False
    assert launch.await_args.args[:4] == (
        "powershell.exe",
        "-File",
        str(script),
        "test notification",
    )


@pytest.mark.asyncio
async def test_feishu_script_timeout_is_unknown_and_kills_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _script_path(monkeypatch, tmp_path)
    process = _FakeProcess(returncode=None)
    launch = AsyncMock(return_value=process)
    monkeypatch.setattr(feishu_provider.asyncio, "create_subprocess_exec", launch)

    async def timeout_wait(awaitable: object, timeout: float) -> object:
        del timeout
        close = getattr(awaitable, "close", None)
        if close is not None:
            close()
        raise TimeoutError("timed out")

    monkeypatch.setattr(feishu_provider.asyncio, "wait_for", timeout_wait)

    result = await feishu_provider.FeishuNotificationProvider().invoke(
        _request(timeout_seconds=0.25), _context()
    )

    assert result.status == "unknown"
    assert result.error is not None
    assert result.error["code"] == "feishu_script_timeout"
    assert result.error["type"] == "timeout"
    assert result.metadata["provider_accepted"] is None
    assert result.metadata["delivery_confirmed"] is False
    assert process.kill_called is True
    assert process.wait_calls == 1


@pytest.mark.asyncio
async def test_feishu_nonzero_exit_is_failed_and_not_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _script_path(monkeypatch, tmp_path)
    process = _FakeProcess(returncode=23)
    launch = AsyncMock(return_value=process)
    monkeypatch.setattr(feishu_provider.asyncio, "create_subprocess_exec", launch)

    result = await feishu_provider.FeishuNotificationProvider().invoke(
        _request(), _context()
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error["code"] == "feishu_script_exit_nonzero"
    assert result.error["type"] == "script_exit"
    assert result.error["exit_code"] == 23
    assert result.metadata["provider_accepted"] is False
    assert result.metadata["delivery_confirmed"] is False


@pytest.mark.asyncio
async def test_feishu_zero_exit_only_reports_provider_acceptance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _script_path(monkeypatch, tmp_path)
    process = _FakeProcess(returncode=0)
    launch = AsyncMock(return_value=process)
    monkeypatch.setattr(feishu_provider.asyncio, "create_subprocess_exec", launch)

    result = await feishu_provider.FeishuNotificationProvider().invoke(
        _request(), _context()
    )

    assert result.status == "succeeded"
    assert result.message == (
        "Feishu notification provider accepted the request; delivery is not confirmed"
    )
    assert result.metadata["provider_accepted"] is True
    assert result.metadata["delivery_confirmed"] is False
    assert result.metadata["delivery_confirmation"] == "not_available"
    assert "message_id" not in result.metadata
    assert result.external_operation_ref is None
    assert launch.await_args.args[:4] == (
        "powershell.exe",
        "-File",
        str(script),
        "test notification",
    )
