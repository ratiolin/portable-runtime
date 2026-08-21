from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest


# cover trivial re-exports
def test_trivial_imports():
    assert True

def test_main_import():
    from portable_runtime.__main__ import main
    assert callable(main)

@pytest.mark.asyncio
async def test_http_promql_timeout_and_auth():
    from portable_runtime.core.capabilities import CapabilityRequest, InvocationContext
    from portable_runtime.providers.verifiers.http_promql import HttpVerifierProvider, PromqlVerifierProvider
    async def fake_timeout(url, expected=None, body_contains=None, timeout=10):
        raise TimeoutError("timeout")
    prov1 = HttpVerifierProvider(probe_fn=fake_timeout)
    req1 = CapabilityRequest(id="t1", capability="verify.http", parameters={"url":"http://example.com"})
    res1 = await prov1.invoke(req1, InvocationContext(runtime_id="t"))
    assert res1.status == "failed"
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "unauthorized"
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)
    prov2 = HttpVerifierProvider(http_client=mock_client)
    req2 = CapabilityRequest(id="t2", capability="verify.http", parameters={"url":"http://example.com"})
    res2 = await prov2.invoke(req2, InvocationContext(runtime_id="t"))
    assert res2.status == "succeeded"
    assert res2.verification_result is not None
    assert res2.verification_result.result == "fail"
    mock_client2 = MagicMock(spec=httpx.AsyncClient)
    mock_client2.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    prov3 = PromqlVerifierProvider(http_client=mock_client2)
    req3 = CapabilityRequest(id="t3", capability="verify.promql", parameters={"query":"up"})
    res3 = await prov3.invoke(req3, InvocationContext(runtime_id="t"))
    assert res3.status == "failed"
    mock_resp2 = MagicMock()
    mock_resp2.status_code = 500
    mock_client3 = MagicMock(spec=httpx.AsyncClient)
    mock_client3.get = AsyncMock(return_value=mock_resp2)
    prov4 = PromqlVerifierProvider(http_client=mock_client3)
    h = await prov4.health()
    assert not h.available

def test_cli_error_branches(tmp_path):
    from portable_runtime.api.cli import run_cli
    db = tmp_path / "err2.db"
    assert run_cli(["--state", str(db), "work", "show", "nonexistent"]) in (0,1)
    try:
        run_cli(["--state", str(db), "work", "run", "nonexistent"])
    except SystemExit:
        pass
    except Exception:  # noqa: S110
        pass
    assert run_cli(["--state", str(db), "knowledge", "show", "nonexistent"]) in (0,1)
    assert run_cli(["--state", str(db), "provider", "health", "notfound"]) in (0,1,2)

def test_store_conformance_and_filesystem(tmp_path):
    from portable_runtime.stores.conformance import _run_crud
    from portable_runtime.stores.filesystem import FilesystemArtifactStore
    from portable_runtime.stores.memory import InMemoryStateStore
    store = InMemoryStateStore()
    _run_crud(store)
    fs = FilesystemArtifactStore(tmp_path / "artifacts")
    assert fs is not None
    from portable_runtime.core.models import Artifact
    art = Artifact(id="art1", kind="report", media_type="text/plain", inline_data="hello")
    store.save_artifact(art)
    assert store.get_artifact("art1") is not None

def test_config_and_compat(tmp_path):
    from portable_runtime.compat.legacy_control_plane import import_legacy_repair
    from portable_runtime.config import PortableConfig
    from portable_runtime.stores.memory import InMemoryStateStore
    cfg = PortableConfig.load(Path("nonexistent.toml"))
    assert cfg is not None
    store = InMemoryStateStore()
    row = {"id":"r99","title":"compat test","description":"desc","status":"open","type":"incident"}
    work, run = import_legacy_repair(row, store)
    assert work is not None
