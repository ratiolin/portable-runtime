import pytest

from portable_runtime.core.process import PortableSubprocessExecutor, ProcessSpec
from portable_runtime.triggers.alertmanager.trigger import AlertmanagerTrigger
from portable_runtime.triggers.base import TriggerEvent
from portable_runtime.triggers.webhook.trigger import WebhookTrigger


@pytest.mark.asyncio
async def test_webhook_trigger():
    trigger = WebhookTrigger()
    events = []
    async def emit(ev: TriggerEvent):
        events.append(ev)
    await trigger.start(emit)
    ev = await trigger.handle({"payload":{"title":"test"}})
    assert ev is not None
    await trigger.stop()

@pytest.mark.asyncio
async def test_alertmanager_trigger():
    trigger = AlertmanagerTrigger()
    events = []
    async def emit(ev: TriggerEvent):
        events.append(ev)
    await trigger.start(emit)
    payload = {"alerts":[{"labels":{"alertname":"TestAlert","fingerprint":"fp1"},"status":"firing","fingerprint":"fp1"}]}
    events_result = await trigger.handle_webhook(payload)
    ev = events_result[0] if events_result else None
    assert ev is not None
    await trigger.stop()

@pytest.mark.asyncio
async def test_process_truncate_and_exec():
    execu = PortableSubprocessExecutor()
    spec = ProcessSpec(argv=["python","-c","print('hello')"])
    res = await execu.run(spec)
    assert res.exit_code == 0
    assert "hello" in res.stdout
    spec2 = ProcessSpec(argv=["python","-c","import sys; print(sys.stdin.read())"], stdin_text="hi stdin")
    res2 = await execu.run(spec2)
    assert "hi stdin" in res2.stdout
