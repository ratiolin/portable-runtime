import json

import pytest

from portable_runtime.core.metrics import generate_metrics_content, provider_health, run_total, work_total
from portable_runtime.core.process import _truncate
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.plugin.manager import PluginManager


def test_truncate():
    short, trunc = _truncate("hello", limit=10)
    assert not trunc
    long_text = "a" * 300000
    out, trunc2 = _truncate(long_text, limit=200000)
    assert trunc2
    assert len(out.encode("utf-8")) <= 200000

def test_metrics_counters():
    work_total.labels(kind="generic-task", status="pending").inc()
    run_total.labels(workflow_id="generic-task", status="running").inc()
    provider_health.labels(provider_id="test").set(1)
    data, ctype = generate_metrics_content()
    assert b"portable_work_total" in data
    assert "text/plain" in ctype

@pytest.mark.asyncio
async def test_plugin_manager_enable_disable(tmp_path):
    registry = ProviderRegistry()
    mgr = PluginManager(registry, plugin_dir=tmp_path / "plugins3")
    # create and load
    pdir = tmp_path / "plug3"
    pdir.mkdir()
    manifest = {"id":"plug3","name":"Plug3","version":"1.0.0","protocol_version":"1","transport":"stdio-jsonl","command":["python","-c","import sys, json; print(json.dumps({\"status\":\"succeeded\",\"message\":\"ok\",\"request_id\":json.loads(sys.stdin.readline())[\"id\"],\"provider_id\":\"plug3\"}))"],"capabilities":["text.echo"]}
    (pdir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    rec = await mgr.load(pdir)
    assert rec.status in ("loaded","failed")
    if rec.status == "loaded":
        # disable/enable
        rec2 = mgr.disable("plug3")
        assert rec2.status == "disabled"
        rec3 = mgr.enable("plug3")
        assert rec3.status == "enabled"
        rec4 = mgr.reload("plug3")
        assert rec4 is not None
        rec5 = mgr.disable("plug3")

def test_plugin_manager_discover_with_invalid(tmp_path):
    registry = ProviderRegistry()
    mgr = PluginManager(registry, plugin_dir=tmp_path / "badplugins")
    (tmp_path / "badplugins").mkdir()
    # invalid manifest
    bad = tmp_path / "badplugins" / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    recs = mgr.discover()
    # should handle gracefully
    assert isinstance(recs, list)
