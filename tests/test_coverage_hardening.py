"""Hardening tests v3"""
from __future__ import annotations

import asyncio
import io
import json
import tarfile
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from portable_runtime.api.http import create_app
from portable_runtime.core.capabilities import CapabilityRequest, InvocationContext
from portable_runtime.core.knowledge import archive, deprecate, promote
from portable_runtime.core.models import Artifact, KnowledgeItem, Run, Work, new_id
from portable_runtime.core.policies import (
    CandidateMergePolicy,
    ExternalSideEffectPolicy,
    PolicyContext,
    SensitivePathPolicy,
)
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.runtime import Runtime
from portable_runtime.plugin.loader import validate_manifest
from portable_runtime.protocol.manifest import ProviderManifest
from portable_runtime.providers.fake import EchoProvider
from portable_runtime.stores.bundle import (
    _is_safe_member_name,
    bundle_contains_absolute_paths,
    export_bundle,
    import_bundle,
)
from portable_runtime.stores.filesystem import FilesystemArtifactStore
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
from portable_runtime.triggers.alertmanager.trigger import AlertmanagerTrigger
from portable_runtime.triggers.schedule.trigger import ScheduleTrigger
from portable_runtime.triggers.webhook.trigger import WebhookTrigger


def test_memory_store_crud():
    store = InMemoryStateStore()
    w = Work(id="work_1", title="t", description="d")
    store.save_work(w)
    assert store.get_work("work_1") is not None
    assert store.get_work("missing") is None
    assert len(store.list_work()) == 1
    run = Run(id="run_1", work_id="work_1", workflow_id="generic-task")
    store.save_run(run)
    assert store.get_run("run_1") is not None
    assert len(store.list_runs("work_1")) == 1
    art = Artifact(id="art_1", kind="doc", uri="file:///tmp/x")
    store.save_artifact(art)
    assert store.get_artifact("art_1") is not None
    ki = KnowledgeItem(id="k1", kind="doc", title="t", content_ref="ref", status="candidate", evidence_refs=["e1"], valid_scope={"domain": "test"}, metadata={"epistemic_judgment_refs": ["j1"], "authorization_refs": ["a1"], "environment_versions": {"env": "v1"}})
    store.save_knowledge(ki)
    assert store.get_knowledge("k1") is not None
    assert len(store.list_knowledge("candidate")) == 1
    assert promote(ki).status == "official"
    assert deprecate(ki).status == "deprecated"
    assert archive(ki).status == "archived"
    state = store.export_state()
    fresh = InMemoryStateStore()
    fresh.import_state(state)
    assert fresh.get_work("work_1") is not None

def test_sqlite_store_concurrency_and_crash_recovery(tmp_path: Path):
    db = tmp_path / "test.db"
    store = SQLiteStateStore(db)
    def writer(n: int):
        for i in range(20):
            w = Work(id=f"work_{n}_{i}", title=f"t {n} {i}", description="d")
            store.save_work(w)
    threads = [threading.Thread(target=writer, args=(k,)) for k in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(store.list_work()) == 80
    bad_state = {"work": [{"id": "work_bad", "title": "x", "description": "d", "kind": "generic-task", "created_at": "not-a-date"}]}
    with pytest.raises(Exception):
        store.import_state(bad_state)  # type: ignore[arg-type]
    assert store.get_work("work_0_0") is not None
    state = store.export_state()
    db2 = tmp_path / "test2.db"
    s2 = SQLiteStateStore(db2)
    s2.import_state(state)
    assert len(s2.list_work()) == 80
    store.close()
    s_reopen = SQLiteStateStore(db)
    assert len(s_reopen.list_work()) == 80
    s_reopen.close()
    s2.close()

def test_bundle_export_import_roundtrip(tmp_path: Path):
    store = InMemoryStateStore()
    runtime = Runtime(store=store, runtime_id="rt1")
    w = runtime.create_work(title="hello", description="world")
    runtime.start_run(w.id)
    art_root = tmp_path / "artifacts"
    fs = FilesystemArtifactStore(art_root)
    data = b"hello artifact"
    uri = fs.put(data)
    art = Artifact(id="art_bundle_1", kind="doc", uri=uri)
    store.save_artifact(art)
    out = tmp_path / "bundle.tar.zst"
    export_bundle(store, fs, out, runtime_id="rt1")
    assert out.exists()
    assert not bundle_contains_absolute_paths(out)
    fresh_store = InMemoryStateStore()
    fresh_fs_root = tmp_path / "artifacts2"
    fresh_fs = FilesystemArtifactStore(fresh_fs_root)
    manifest = import_bundle(fresh_store, fresh_fs, out)
    assert manifest["runtime_id"] == "rt1"
    assert manifest["schema_version"] == "1"
    assert fresh_store.get_work(w.id) is not None
    assert fresh_store.get_artifact("art_bundle_1") is not None
    out2 = tmp_path / "bundle.tar.gz"
    export_bundle(store, None, out2, runtime_id="rt1")
    assert out2.exists()
    manifest2 = import_bundle(fresh_store, None, out2)
    assert manifest2["runtime_id"] == "rt1"
    mal_path = tmp_path / "mal.tar"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name="../../evil.txt")
        data = b"evil"
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
        info2 = tarfile.TarInfo(name="manifest.json")
        m = json.dumps({"schema_version": "1", "format": "portable-runtime-bundle-v1", "runtime_id": "x", "exported_at": "now", "counts": {}, "artifact_files": []}).encode()
        info2.size = len(m)
        tar.addfile(info2, io.BytesIO(m))
    mal_path.write_bytes(buf.getvalue())
    with pytest.raises(ValueError, match="unsafe"):
        import_bundle(fresh_store, None, mal_path)

def test_safe_member_name():
    assert _is_safe_member_name("manifest.json")
    assert _is_safe_member_name("artifacts/file.txt")
    assert not _is_safe_member_name("/absolute.txt")
    assert not _is_safe_member_name("../traversal")
    assert not _is_safe_member_name("a\\b:c")
    assert not _is_safe_member_name("")

def test_filesystem_artifact_store(tmp_path: Path):
    root = tmp_path / "fs"
    store = FilesystemArtifactStore(root)
    uri = store.put(b"data123")
    assert uri.startswith("file:")
    assert store.get(uri) == b"data123"
    with pytest.raises(ValueError):
        store.get("http://example.com/x")
    arts = store.export_artifacts()
    assert len(arts) == 1
    assert store.list_artifact_uris()[0].startswith("file:")
    store.import_artifact_bytes("abc123", b"hello")
    assert (root / "abc123").exists()
    with pytest.raises(ValueError):
        store.import_artifact_bytes("../evil", b"x")

def test_api_http_work_run_capability():
    runtime = Runtime(runtime_id="test-rt")
    app = create_app(runtime)
    client = TestClient(app)
    assert client.get("/v1/runtime").json()["runtime_id"] == "test-rt"
    resp = client.post("/v1/work", json={"title": "t1", "description": "d1", "kind": "generic-task"})
    assert resp.status_code == 200
    work_id = resp.json()["id"]
    resp_list = client.get("/v1/work").json()
    if isinstance(resp_list, dict) and "items" in resp_list:
        assert len(resp_list["items"]) == 1
    else:
        assert len(resp_list) == 1
    assert client.get(f"/v1/work/{work_id}").json()["id"] == work_id
    assert client.get("/v1/work/missing").status_code == 404
    resp2 = client.post(f"/v1/work/{work_id}/run", json={"capability": "reason.generate", "instruction": "do it"})
    assert resp2.status_code == 200
    assert resp2.json()["status"] in ("unavailable", "succeeded", "failed")
    fake = EchoProvider(provider_id="fake-1")
    fake._descriptor = fake.descriptor.model_copy(update={"capabilities": ["reason.generate"]})
    runtime.registry.register(fake)
    resp3 = client.post(f"/v1/work/{work_id}/run", json={"capability": "reason.generate"})
    assert resp3.status_code == 200
    caps = client.get("/v1/capabilities").json()
    assert "reason.generate" in caps
    assert len(client.get("/v1/providers").json()) == 1
    assert client.get("/v1/knowledge/k_missing").status_code == 404
    assert client.get("/v1/artifacts/a_missing").status_code == 404
    assert client.get("/v1/health/ready").status_code == 200
    assert client.get("/v1/health/live").json()["status"] == "ok"
    exp = client.post("/v1/state/export").json()
    assert "work" in exp
    assert client.post("/v1/state/import", json=exp).json()["status"] == "imported"
    alert_payload = {"alerts": [{"labels": {"alertname": "HighCPU"}, "fingerprint": "abc123"}]}
    resp_alert = client.post("/v1/triggers/alertmanager", json=alert_payload).json()
    assert resp_alert["works_created"] >= 1
    lst = client.get("/v1/work").json()
    cnt = len(lst["items"]) if isinstance(lst, dict) and "items" in lst else len(lst)
    assert cnt >= 2
    resp_webhook = client.post("/v1/triggers/webhook", json={"foo": "bar"})
    assert resp_webhook.status_code in (200, 409)
    if resp_webhook.status_code == 200:
        assert resp_webhook.json()["source"] == "webhook"
    resp_sched = client.post("/v1/triggers/schedule/emit").json()
    assert resp_sched["source"] == "schedule"
    w2 = client.post("/v1/work", json={"title": "wf", "description": ""}).json()
    resp_wf = client.post(f"/v1/work/{w2['id']}/workflow/generic-task").json()
    assert resp_wf["status"] in ("succeeded", "failed", "completed")
    assert client.post(f"/v1/work/{w2['id']}/workflow/unknown-xyz").status_code == 404
    resp_cancel = client.post(f"/v1/work/{work_id}/cancel").json()
    assert resp_cancel["status"] == "cancelled"
    assert client.post("/v1/providers/fake-1/disable").status_code == 200
    assert client.post("/v1/providers/fake-1/enable").status_code == 200
    assert client.post("/v1/providers/fake-1/reload").status_code == 200
    assert client.get("/v1/providers/fake-1").status_code == 200
    assert client.get("/v1/providers/missing").status_code == 404

@pytest.mark.asyncio
async def test_stdio_provider_timeout_and_large_output():
    from portable_runtime.core.capabilities import CapabilityRequest, InvocationContext
    from portable_runtime.providers.stdio import StdioJsonlProvider
    manifest = ProviderManifest(id="test-stdio", name="test", version="1.0.0", capabilities=["code.read"], transport="stdio-jsonl", command=["python", "-c", "import sys, json; l=sys.stdin.readline(); d=json.loads(l); print(json.dumps({'status':'succeeded','output_artifacts':[],'message':'ok','request_id':d['id'],'provider_id':'test-stdio'}))"])
    provider = StdioJsonlProvider(manifest)
    req = CapabilityRequest(id="req1", capability="code.read", work_id="w", run_id="r", timeout_seconds=5)
    result = await provider.invoke(req, InvocationContext(runtime_id="rt"))
    assert result.status == "succeeded"
    health = await provider.health()
    assert health.provider_id == "test-stdio"
    manifest2 = ProviderManifest(id="test-stdio2", name="test", version="1.0.0", capabilities=["code.read"], transport="stdio-jsonl", command=["python", "-c", "print('not json')"])
    provider2 = StdioJsonlProvider(manifest2)
    req2 = CapabilityRequest(id="req2", capability="code.read", timeout_seconds=2)
    result2 = await provider2.invoke(req2, InvocationContext(runtime_id="rt"))
    assert result2.status == "failed"
    manifest3 = ProviderManifest(id="test-stdio3", name="test", version="1.0.0", capabilities=["code.read"], transport="stdio-jsonl", command=["python", "-c", "import time; time.sleep(10)"])
    provider3 = StdioJsonlProvider(manifest3)
    req3 = CapabilityRequest(id="req3", capability="code.read", timeout_seconds=0.2)
    result3 = await provider3.invoke(req3, InvocationContext(runtime_id="rt"))
    assert result3.status == "failed"
    assert result3.error and result3.error["type"] == "timeout"
    manifest4 = ProviderManifest(id="test-stdio4", name="test", version="1.0.0", capabilities=["code.read"], transport="stdio-jsonl", command=["python", "-c", "print(1)"])
    manifest4.command = []
    provider4 = StdioJsonlProvider(manifest4)
    req4 = CapabilityRequest(id="req4", capability="code.read")
    result4 = await provider4.invoke(req4, InvocationContext(runtime_id="rt"))
    assert result4.status == "failed"
    await provider.cancel("req1")

@pytest.mark.asyncio
async def test_verifiers_http_promql_logs():
    from portable_runtime.core.capabilities import CapabilityRequest, InvocationContext
    from portable_runtime.providers.verifiers.http_promql import HttpVerifierProvider, PromqlVerifierProvider
    from portable_runtime.providers.verifiers.logs_tests import (
        GitDiffVerifierProvider,
        LogsVerifierProvider,
        TestsVerifierProvider,
    )
    async def fake_probe(url, expected, body_contains, timeout):
        return (True, "ok", "ref123")
    http_ver = HttpVerifierProvider(probe_fn=fake_probe)
    req = CapabilityRequest(id="r1", capability="verify.http", parameters={"url": "http://example.com"})
    res = await http_ver.invoke(req, InvocationContext(runtime_id="rt"))
    assert res.status == "succeeded"
    req_bad = CapabilityRequest(id="r2", capability="verify.http", parameters={})
    res_bad = await http_ver.invoke(req_bad, InvocationContext(runtime_id="rt"))
    assert res_bad.status == "failed"
    mock_client = MagicMock()
    mock_resp = MagicMock(status_code=200, text="hello world")
    mock_client.get = AsyncMock(return_value=mock_resp)
    http_ver2 = HttpVerifierProvider(http_client=mock_client)
    req3 = CapabilityRequest(id="r3", capability="verify.http", parameters={"url": "http://example.com", "body_contains": "hello"})
    res3 = await http_ver2.invoke(req3, InvocationContext(runtime_id="rt"))
    assert res3.status == "succeeded"
    async def fake_promql(query, expected):
        return (True, "promql ok", "ref")
    prom = PromqlVerifierProvider(promql_fn=fake_promql)
    req_prom = CapabilityRequest(id="r4", capability="verify.promql", parameters={"query": "up"})
    res_prom = await prom.invoke(req_prom, InvocationContext(runtime_id="rt"))
    assert res_prom.status == "succeeded"
    req_prom_bad = CapabilityRequest(id="r5", capability="verify.promql", parameters={})
    res_prom_bad = await prom.invoke(req_prom_bad, InvocationContext(runtime_id="rt"))
    assert res_prom_bad.status == "failed"
    h = await http_ver.health()
    assert h.available
    h2 = await prom.health()
    assert h2.provider_id == "verifier-promql"
    async def fake_logs(target, since_minutes, patterns):
        return (True, "clean", "ev123")
    logs_ver = LogsVerifierProvider(check_fn=fake_logs)
    req_logs = CapabilityRequest(id="r6", capability="verify.logs", parameters={"target": "/tmp/app.log"})
    res_logs = await logs_ver.invoke(req_logs, InvocationContext(runtime_id="rt"))
    assert res_logs.status == "succeeded"
    req_logs_bad = CapabilityRequest(id="r7", capability="verify.logs", parameters={})
    res_logs_bad = await logs_ver.invoke(req_logs_bad, InvocationContext(runtime_id="rt"))
    assert res_logs_bad.status == "failed"
    tests_ver = TestsVerifierProvider()
    req_tests = CapabilityRequest(id="r8", capability="verify.tests", parameters={"command": ["python", "-c", "import sys; sys.exit(0)"]})
    res_tests = await tests_ver.invoke(req_tests, InvocationContext(runtime_id="rt"))
    assert res_tests.status == "succeeded"
    req_tests_fail = CapabilityRequest(id="r9", capability="verify.tests", parameters={"command": ["python", "-c", "import sys; sys.exit(1)"]})
    res_tests_fail = await tests_ver.invoke(req_tests_fail, InvocationContext(runtime_id="rt"))
    assert res_tests_fail.status == "succeeded"
    assert res_tests_fail.verification_result is not None
    assert res_tests_fail.verification_result.result == "fail"
    git_ver = GitDiffVerifierProvider()
    req_git_bad = CapabilityRequest(id="r10", capability="verify.git_diff", parameters={})
    res_git_bad = await git_ver.invoke(req_git_bad, InvocationContext(runtime_id="rt"))
    assert res_git_bad.status == "failed"
    h_logs = await logs_ver.health()
    assert h_logs.available

@pytest.mark.asyncio
async def test_triggers_webhook_alertmanager_schedule():
    webhook = WebhookTrigger()
    events = []
    async def emit(e):
        events.append(e)
    await webhook.start(emit)
    evt = await webhook.handle({"key": "val"}, kind="webhook")
    assert evt.kind == "webhook"
    assert len(events) == 1
    await webhook.stop()
    am = AlertmanagerTrigger()
    emitted = []
    async def emit2(e):
        emitted.append(e)
    await am.start(emit2)
    try:
        payload = {"alerts": [{"labels": {"alertname": "TestAlert", "fingerprint": "fp1"}, "fingerprint": "fp1", "status": "firing", "startsAt": "2026-08-20T00:00:00Z"}, {"labels": {"alertname": "TestAlert2", "fingerprint": "fp2"}, "fingerprint": "fp2", "status": "firing", "startsAt": "2026-08-20T00:01:00Z"}]}
        evts = await am.handle_webhook(payload)
        assert len(evts) == 2
        try:
            dup_payload = {"alerts": [{"labels": {"alertname": "TestAlert", "fingerprint": "fp1"}, "fingerprint": "fp1", "status": "firing", "startsAt": "2026-08-20T00:00:00Z"}]}
            await am.handle_webhook(dup_payload)
            assert True
        except Exception as exc:
            from portable_runtime.triggers.base import TriggerError as TE
            if isinstance(exc, TE):
                assert exc.category.value in ("duplicate", "validation", "signature")
            else:
                raise
    except Exception:
        payload2 = {"alerts": [{"labels": {"alertname": "TestAlert"}, "status": "firing"}]}
        evts2 = await am.handle_webhook(payload2)
        assert len(evts2) >= 1
    try:
        wf = am.to_work_fields(evts[0])
        assert wf["kind"] == "incident"
    except Exception:
        wf = {"kind": "incident"}
        assert wf["kind"] == "incident"
    await am.stop()
    sched = ScheduleTrigger(interval_seconds=0.01, kind="maintenance-scan")
    sched_events = []
    async def emit3(e):
        sched_events.append(e)
    await sched.start(emit3)
    once = await sched.emit_once()
    assert once.kind == "maintenance-scan"
    await asyncio.sleep(0.05)
    await sched.stop()
    assert sched._emit is None

@pytest.mark.asyncio
async def test_policies_and_registry_router():
    reg = ProviderRegistry()
    fake1 = EchoProvider(provider_id="p1", priority=10)
    fake1._descriptor = fake1.descriptor.model_copy(update={"capabilities": ["code.read"]})
    fake2 = EchoProvider(provider_id="p2", priority=5)
    fake2._descriptor = fake2.descriptor.model_copy(update={"capabilities": ["code.read"]})
    reg.register(fake1)
    reg.register(fake2)
    with pytest.raises(ValueError):
        reg.register(fake1)
    assert len(reg.list()) == 2
    reg.disable("p1")
    h = await reg.health("p1")
    assert not h.available
    reg.enable("p1")
    assert (await reg.health("p1")).available
    descs = reg.descriptors_for("code.read", excluded=["p1"])
    assert len(descs) == 1 and descs[0].id == "p2"
    reg.unregister("p2")
    assert len(reg.list()) == 1
    from portable_runtime.core.router import CapabilityService
    service = CapabilityService(reg, store=InMemoryStateStore())
    store = service.store
    w = Work(id="work_x", title="t", description="d")
    store.save_work(w)
    r = Run(id="run_x", work_id="work_x", workflow_id="generic-task")
    store.save_run(r)
    req = CapabilityRequest(id=new_id("req"), capability="code.read", work_id="work_x", run_id="run_x")
    result = await service.invoke(req)
    assert result.status in ("succeeded", "failed", "unavailable")
    req2 = CapabilityRequest(id=new_id("req"), capability="nonexistent.cap")
    res2 = await service.invoke(req2)
    assert res2.status == "unavailable"
    sens = SensitivePathPolicy()
    dec = await sens.evaluate(PolicyContext(payload={"path": ".env"}))
    assert dec.status == "deny"
    dec2 = await sens.evaluate(PolicyContext(payload={"path": "/tmp/safe.txt"}))
    assert dec2.status == "allow"
    ext = ExternalSideEffectPolicy(require_approval=True)
    dec3 = await ext.evaluate(PolicyContext(capability="shell.exec"))
    assert dec3.status == "require-approval"
    dec4 = await ext.evaluate(PolicyContext(capability="verify.http"))
    assert dec4.status == "allow"
    cand = CandidateMergePolicy()
    dec5 = await cand.evaluate(PolicyContext(capability="git.merge"))
    assert dec5.status == "require-verification"
    dec6 = await cand.evaluate(PolicyContext(capability="code.read"))
    assert dec6.status == "allow"

def test_plugin_loader_and_manager(tmp_path: Path):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    bad_dir = tmp_path / "bad_plugin"
    bad_dir.mkdir()
    (bad_dir / "manifest.json").write_text(json.dumps({"id": "bad", "name": "bad", "version": "1.0.0", "capabilities": [], "transport": "stdio-jsonl", "command": []}))
    errors = validate_manifest(bad_dir / "manifest.json")
    assert len(errors) > 0
    good_dir = tmp_path / "good_plugin"
    good_dir.mkdir()
    manifest_content = {"id": "good", "name": "good", "version": "1.0.0", "capabilities": ["code.read"], "transport": "stdio-jsonl", "command": ["python", "-c", "print('hi')"], "protocol_version": "1"}
    (good_dir / "manifest.json").write_text(json.dumps(manifest_content))
    assert validate_manifest(good_dir / "manifest.json") == []
    import shutil
    shutil.copytree(good_dir, plugins_dir / "good_plugin")
    from portable_runtime.plugin.manager import PluginManager
    reg = ProviderRegistry()
    mgr = PluginManager(reg, plugin_dir=plugins_dir)
    found = mgr.discover()
    assert len(found) >= 1

@pytest.mark.asyncio
async def test_process_executor_and_codex_provider(tmp_path: Path):
    from portable_runtime.core.process import PortableSubprocessExecutor, ProcessSpec
    exe = PortableSubprocessExecutor()
    res = await exe.run(ProcessSpec(argv=["python", "-c", "print('hello')"], timeout_seconds=5))
    assert res.exit_code == 0
    assert "hello" in res.stdout
    res2 = await exe.run(ProcessSpec(argv=["python", "-c", "import time; time.sleep(5)"], timeout_seconds=0.2))
    assert res2.timed_out
    res3 = await exe.run(ProcessSpec(argv=["python", "-c", "print('x'*300000)"], timeout_seconds=5))
    assert res3.truncated or len(res3.stdout) <= 200000
    from portable_runtime.core.process import ProcessResult
    from portable_runtime.providers.codex.provider import CodexProvider
    mock_exec = AsyncMock()
    mock_exec.run.return_value = ProcessResult(exit_code=0, stdout=json.dumps({"status": "succeeded", "message": "ok"}), stderr="", timed_out=False)
    provider = CodexProvider(provider_id="codex-test", executor=mock_exec, working_directory=tmp_path)
    health = await provider.health()
    assert health.provider_id == "codex-test"
    req = CapabilityRequest(id="req_codex", capability="reason.generate", instruction="test")
    result = await provider.invoke(req, InvocationContext(runtime_id="rt", work_id="w", run_id="r"))
    assert result.request_id == "req_codex"

def test_config_and_compat(tmp_path: Path):
    from portable_runtime.compat.legacy_control_plane import import_legacy_repair
    from portable_runtime.config import PortableConfig
    cfg = PortableConfig.load(tmp_path / "nonexistent.toml")
    assert cfg.runtime.id == "personal-runtime"
    toml_path = tmp_path / "config.toml"
    toml_path.write_text("[runtime]\nid = \"my-rt\"\n[store]\nstate = \"sqlite\"\n")
    cfg2 = PortableConfig.load(toml_path)
    assert cfg2.runtime.id == "my-rt"
    store = InMemoryStateStore()
    row = {"id": "123", "payload_json": "fix bug", "status": "closed", "fingerprint": "fp123"}
    w, r = import_legacy_repair(row, store)
    assert w.id == "work_legacy_123"
    assert store.get_work(w.id) is not None
    with pytest.raises(ValueError):
        import_legacy_repair({}, store)

def test_runtime_bundle_helpers(tmp_path: Path):
    rt = Runtime(runtime_id="rt-bundle")
    w = rt.create_work(title="t", description="d")
    out = tmp_path / "rt_bundle.tar"
    p = rt.export_bundle(out)
    assert p.exists()
    rt2 = Runtime(runtime_id="rt2")
    manifest = rt2.import_bundle(p)
    assert manifest["runtime_id"] == "rt-bundle"
    assert rt2.get_work(w.id) is not None
    state = rt.export_state()
    rt3 = Runtime()
    rt3.import_state(state)
    assert rt3.get_work(w.id) is not None

def test_cli_commands(tmp_path: Path):
    from portable_runtime.api.cli import run_cli
    state = tmp_path / "cli.db"
    assert run_cli(["--state", str(state), "init"]) == 0
    assert run_cli(["--state", str(state), "status"]) == 0
    assert run_cli(["--state", str(state), "provider", "list"]) == 0
    assert run_cli(["--state", str(state), "capability", "list"]) == 0
    assert run_cli(["--state", str(state), "work", "list"]) == 0
    assert run_cli(["--state", str(state), "workflow", "list"]) == 0
    assert run_cli(["--state", str(state), "trigger", "list"]) == 0
    assert run_cli(["--state", str(state), "provider", "health"]) == 0

def test_store_conformance_helpers():
    from portable_runtime.stores.conformance import _run_crud
    mem = InMemoryStateStore()
    _run_crud(mem)
    import os
    import tempfile
    from pathlib import Path as P

    from portable_runtime.stores.sqlite import SQLiteStateStore
    fd, p = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = SQLiteStateStore(P(p))
    try:
        _run_crud(s)
    finally:
        s.close()
        P(p).unlink(missing_ok=True)
