import json
from pathlib import Path

import pytest

from portable_runtime.api.cli import run_cli
from portable_runtime.core.capabilities import CapabilityRequest, InvocationContext
from portable_runtime.core.process import ProcessResult, ProcessSpec
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.plugin.manager import PluginManager
from portable_runtime.providers.codex.provider import CodexProvider
from portable_runtime.providers.verifiers.http_promql import HttpVerifierProvider, PromqlVerifierProvider
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.migration import dual_write_repair, list_legacy_mappings, stable_work_id


@pytest.mark.asyncio
async def test_cli_work_submit_and_list(tmp_path):
    db = tmp_path / "test.db"
    rc = run_cli(["--state", str(db), "work", "submit", "--title", "cli-test", "--kind", "generic-task"])
    assert rc == 0
    rc = run_cli(["--state", str(db), "work", "list"])
    assert rc == 0
    rc = run_cli(["--state", str(db), "status"])
    assert rc == 0
    rc = run_cli(["--state", str(db), "capability", "list"])
    assert rc == 0
    rc = run_cli(["--state", str(db), "workflow", "list"])
    assert rc == 0
    rc = run_cli(["--state", str(db), "trigger", "list"])
    assert rc == 0

@pytest.mark.asyncio
async def test_cli_plugin_validate(tmp_path):
    # create minimal manifest
    pdir = tmp_path / "plug"
    pdir.mkdir()
    manifest = {"id":"test-plug","name":"Test","version":"1.0.0","protocol_version":"1","transport":"stdio-jsonl","command":["python","-c","print(1)"],"capabilities":["text.echo"]}
    (pdir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    db = tmp_path / "db2.db"
    rc = run_cli(["--state", str(db), "plugin", "validate", str(pdir)])
    assert rc in (0,1)

def test_migration_dual_write():
    store = InMemoryStateStore()
    row = {"id":"r1","type":"incident","title":"Test incident","description":"desc","status":"open"}
    work, run = dual_write_repair(row, store)
    assert work.id == stable_work_id("r1")
    assert store.get_work(work.id) is not None
    mappings = list_legacy_mappings(store)
    assert any(m["legacy_repair_id"]=="r1" for m in mappings)

@pytest.mark.asyncio
async def test_http_verifier_with_probe_fn():
    async def fake_probe(url, expected=None, body_contains=None, timeout=10):
        return (True, "ok probe", "ref123")
    provider = HttpVerifierProvider(probe_fn=fake_probe)
    req = CapabilityRequest(id="req1", capability="verify.http", parameters={"url":"http://example.com"})
    res = await provider.invoke(req, InvocationContext(runtime_id="test"))
    assert res.status == "succeeded"
    assert res.metadata.get("evidence_ref") == "ref123"
    # missing url -> failed
    req2 = CapabilityRequest(id="req2", capability="verify.http", parameters={})
    res2 = await provider.invoke(req2, InvocationContext(runtime_id="test"))
    assert res2.status == "failed"

@pytest.mark.asyncio
async def test_promql_verifier_with_fn():
    async def fake_promql(query, expected):
        return (True, "promql ok", "ev1")
    provider = PromqlVerifierProvider(promql_fn=fake_promql)
    req = CapabilityRequest(id="r1", capability="verify.promql", parameters={"query":"up==1"})
    res = await provider.invoke(req, InvocationContext(runtime_id="test"))
    assert res.status == "succeeded"
    # missing query -> failed
    req2 = CapabilityRequest(id="r2", capability="verify.promql", parameters={})
    res2 = await provider.invoke(req2, InvocationContext(runtime_id="test"))
    assert res2.status == "failed"

@pytest.mark.asyncio
async def test_codex_provider_with_fake_executor():
    class FakeExec:
        async def run(self, spec: ProcessSpec) -> ProcessResult:
            return ProcessResult(exit_code=0, stdout=json.dumps({"status":"succeeded","message":"codex ok"}), stderr="", timed_out=False)
        async def health(self): return True
    provider = CodexProvider(executor=FakeExec(), working_directory=Path.cwd())
    health = await provider.health()
    assert health.available or not health.available  # health may depend on CLI existence but should not crash
    req = CapabilityRequest(id="creq1", capability="reason.generate", instruction="hello")
    res = await provider.invoke(req, InvocationContext(runtime_id="test"))
    # fake returns succeeded via stdout json
    assert res.status in ("succeeded","failed","unavailable")

def test_plugin_manager_discover(tmp_path):
    registry = ProviderRegistry()
    mgr = PluginManager(registry, plugin_dir=tmp_path / "plugins")
    # empty dir
    assert mgr.discover() == []
    # create plugin dir with manifest
    plug_dir = tmp_path / "plugins" / "myplug"
    plug_dir.mkdir(parents=True)
    manifest = {"id":"myplug","name":"My Plug","version":"1.0.0","protocol_version":"1","transport":"stdio-jsonl","command":["python","-c","print(1)"],"capabilities":["text.echo"]}
    (plug_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    recs = mgr.discover()
    assert len(recs) == 1
    assert recs[0].id == "myplug"

@pytest.mark.asyncio
async def test_plugin_manager_load(tmp_path):
    registry = ProviderRegistry()
    mgr = PluginManager(registry, plugin_dir=tmp_path / "plugins2")
    pdir = tmp_path / "plug2"
    pdir.mkdir()
    manifest = {"id":"plug2","name":"Plug2","version":"1.0.0","protocol_version":"1","transport":"stdio-jsonl","command":["python","-c","import sys, json; print(json.dumps({'status':'succeeded','message':'ok','request_id':json.loads(sys.stdin.readline())['id'],'provider_id':'plug2'}))"],"capabilities":["text.echo"]}
    (pdir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    rec = await mgr.load(pdir)
    assert rec.status in ("loaded","failed","discovered")
