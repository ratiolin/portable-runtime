from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from portable_runtime.api.cli import run_cli
from portable_runtime.core.capabilities import CapabilityRequest, InvocationContext
from portable_runtime.core.process import PortableSubprocessExecutor, ProcessSpec
from portable_runtime.plugin.sdk import FunctionProvider, provider
from portable_runtime.providers.verifiers.http_promql import (
    ContainerVerifierProvider,
    HttpVerifierProvider,
    PromqlVerifierProvider,
)
from portable_runtime.providers.verifiers.logs_tests import LogsVerifierProvider, TestsVerifierProvider


@pytest.mark.asyncio
async def test_http_verifier_http_client_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "hello world"
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)
    prov = HttpVerifierProvider(http_client=mock_client)
    req = CapabilityRequest(id="h1", capability="verify.http", parameters={"url":"http://example.com","expected_status":[200]})
    res = await prov.invoke(req, InvocationContext(runtime_id="t"))
    assert res.status == "succeeded"
    mock_client.get.assert_awaited()

@pytest.mark.asyncio
async def test_http_verifier_body_contains_fail():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "hello"
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)
    prov = HttpVerifierProvider(http_client=mock_client)
    req = CapabilityRequest(id="h2", capability="verify.http", parameters={"url":"http://example.com","expected_status":[200],"body_contains":"missing"})
    res = await prov.invoke(req, InvocationContext(runtime_id="t"))
    assert res.status == "succeeded"
    assert res.verification_result is not None
    assert res.verification_result.result == "fail"

@pytest.mark.asyncio
async def test_http_verifier_status_mismatch():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "not found"
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)
    prov = HttpVerifierProvider(http_client=mock_client)
    req = CapabilityRequest(id="h3", capability="verify.http", parameters={"url":"http://example.com","expected_status":[200]})
    res = await prov.invoke(req, InvocationContext(runtime_id="t"))
    assert res.status == "succeeded"
    assert res.verification_result is not None
    assert res.verification_result.result == "fail"

@pytest.mark.asyncio
async def test_promql_verifier_http_client_success():
    mock_resp = MagicMock()
    mock_resp.headers = {"content-type":"application/json"}
    mock_resp.json.return_value = {"data":{"result":[{"value":[123, "1"]}]}}
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)
    prov = PromqlVerifierProvider(http_client=mock_client, prometheus_url="http://prom.test")
    req = CapabilityRequest(id="p1", capability="verify.promql", parameters={"query":"up==1","expected":1})
    res = await prov.invoke(req, InvocationContext(runtime_id="t"))
    assert res.status == "succeeded"

@pytest.mark.asyncio
async def test_promql_verifier_no_result():
    mock_resp = MagicMock()
    mock_resp.headers = {"content-type":"application/json"}
    mock_resp.json.return_value = {"data":{"result":[]}}
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)
    prov = PromqlVerifierProvider(http_client=mock_client)
    req = CapabilityRequest(id="p2", capability="verify.promql", parameters={"query":"up==1"})
    res = await prov.invoke(req, InvocationContext(runtime_id="t"))
    assert res.status == "succeeded"
    assert res.verification_result is not None
    assert res.verification_result.result == "fail"

@pytest.mark.asyncio
async def test_promql_verifier_expected_mismatch():
    mock_resp = MagicMock()
    mock_resp.headers = {"content-type":"application/json"}
    mock_resp.json.return_value = {"data":{"result":[{"value":[123, "2"]}]}}
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)
    prov = PromqlVerifierProvider(http_client=mock_client)
    req = CapabilityRequest(id="p3", capability="verify.promql", parameters={"query":"up","expected":1})
    res = await prov.invoke(req, InvocationContext(runtime_id="t"))
    assert res.status == "succeeded"
    assert res.verification_result is not None
    assert res.verification_result.result == "fail"

@pytest.mark.asyncio
async def test_container_verifier_with_check_fn():
    async def fake_check(*args, **kwargs):
        return (True, "containers ok", "ev1")
    prov = ContainerVerifierProvider(check_fn=fake_check)
    req = CapabilityRequest(id="c1", capability="verify.container", parameters={"targets":["mycontainer"]})
    res = await prov.invoke(req, InvocationContext(runtime_id="t"))
    assert res.status == "succeeded"
    h = await prov.health()
    assert h.available

@pytest.mark.asyncio
async def test_logs_verifier_with_check_fn(tmp_path):
    async def fake_logs(target, since_minutes=30, patterns=None):
        return (True, "clean", "ev123")
    prov = LogsVerifierProvider(check_fn=fake_logs)
    req = CapabilityRequest(id="l1", capability="verify.logs", parameters={"target": str(tmp_path / "app.log")})
    res = await prov.invoke(req, InvocationContext(runtime_id="t"))
    assert res.status == "succeeded"
    # missing target
    req2 = CapabilityRequest(id="l2", capability="verify.logs", parameters={})
    res2 = await prov.invoke(req2, InvocationContext(runtime_id="t"))
    assert res2.status == "failed"

@pytest.mark.asyncio
async def test_tests_verifier():
    prov = TestsVerifierProvider()
    h = await prov.health()
    assert h.available in (True, False)
    req = CapabilityRequest(id="t1", capability="verify.tests", parameters={"command":["python","-c","print(1)"]})
    res = await prov.invoke(req, InvocationContext(runtime_id="t"))
    assert res.status in ("succeeded","failed")

@pytest.mark.asyncio
async def test_function_provider_sdk():
    async def my_handler(req, ctx):
        from portable_runtime.core.capabilities import CapabilityResult
        return CapabilityResult(request_id=req.id, provider_id="sdk-test", status="succeeded", message="sdk ok")
    prov = FunctionProvider(my_handler, provider_id="sdk-test", version="1.0.0", capabilities=["sdk.test"])
    h = await prov.health()
    assert h.available
    req = CapabilityRequest(id="s1", capability="sdk.test")
    res = await prov.invoke(req, InvocationContext(runtime_id="t"))
    assert res.status == "succeeded"
    # decorator
    @provider(id="dec-test", version="1.0.0", capabilities=["dec.test"])
    async def dec_handler(req):
        from portable_runtime.core.capabilities import CapabilityResult
        return CapabilityResult(request_id=req.id, provider_id="dec-test", status="succeeded")
    assert dec_handler.descriptor.id == "dec-test"

@pytest.mark.asyncio
async def test_process_executor_timeout(tmp_path):
    execu = PortableSubprocessExecutor()
    spec = ProcessSpec(argv=["python","-c","import time; time.sleep(2)"], timeout_seconds=0.2)
    res = await execu.run(spec)
    assert res.timed_out

def test_cli_state_export_import(tmp_path):
    db = tmp_path / "cli.db"
    # submit work
    rc = run_cli(["--state", str(db), "work", "submit", "--title","export-test"])
    assert rc == 0
    export_path = tmp_path / "state.json"
    rc = run_cli(["--state", str(db), "state", "export", str(export_path)])
    assert rc == 0
    assert export_path.exists()
    # import into new db
    db2 = tmp_path / "cli2.db"
    rc = run_cli(["--state", str(db2), "state", "import", str(export_path)])
    assert rc == 0
    rc = run_cli(["--state", str(db2), "work", "list"])
    assert rc == 0
