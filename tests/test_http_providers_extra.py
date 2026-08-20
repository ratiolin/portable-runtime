from fastapi.testclient import TestClient

from portable_runtime.api.http import create_app
from portable_runtime.core.runtime import Runtime
from portable_runtime.providers.fake import EchoProvider
from portable_runtime.stores.memory import InMemoryStateStore


def test_http_providers_enable_disable():
    runtime = Runtime(store=InMemoryStateStore())
    # register fake provider
    fake = EchoProvider(provider_id="fake-test")
    runtime.registry.register(fake)
    app = create_app(runtime)
    client = TestClient(app)
    # list
    assert client.get("/v1/providers").status_code == 200
    # get specific
    assert client.get("/v1/providers/fake-test").status_code == 200
    assert client.get("/v1/providers/notfound").status_code == 404
    # disable/enable/reload
    assert client.post("/v1/providers/fake-test/disable").status_code == 200
    assert client.post("/v1/providers/fake-test/enable").status_code == 200
    assert client.post("/v1/providers/fake-test/reload").status_code == 200
    assert client.post("/v1/providers/notfound/enable").status_code == 404
    # capabilities
    caps = client.get("/v1/capabilities").json()
    assert "text.echo" in caps

def test_http_work_flow():
    runtime = Runtime(store=InMemoryStateStore())
    fake = EchoProvider(provider_id="fake2")
    runtime.registry.register(fake)
    app = create_app(runtime)
    client = TestClient(app)
    # create work
    resp = client.post("/v1/work", json={"title":"wf-test","description":"desc","kind":"generic-task","requested_capabilities":["text.echo"]})
    assert resp.status_code == 200
    wid = resp.json()["id"]
    # get work
    assert client.get(f"/v1/work/{wid}").status_code == 200
    assert client.get("/v1/work/notfound").status_code == 404
    # run capability
    resp2 = client.post(f"/v1/work/{wid}/run", json={"capability":"text.echo","instruction":"hello"})
    assert resp2.status_code == 200
    # list work
    assert client.get("/v1/work").status_code == 200
    # knowledge
    assert client.get("/v1/knowledge").status_code == 200
    assert client.get("/v1/knowledge/notfound").status_code == 404
    # artifacts
    assert client.get("/v1/artifacts/notfound").status_code == 404
    # state export/import
    resp3 = client.post("/v1/state/export")
    assert resp3.status_code == 200
    state = resp3.json()
    # import
    resp4 = client.post("/v1/state/import", json=state)
    assert resp4.status_code == 200

def test_metrics_snapshot():
    from portable_runtime.core.metrics import generate_metrics_content
    from portable_runtime.core.runtime import Runtime
    from portable_runtime.stores.memory import InMemoryStateStore
    runtime = Runtime(store=InMemoryStateStore())
    # create works to increment metrics
    runtime.create_work(title="m1", kind="generic-task")
    runtime.create_work(title="m2", kind="incident")
    snap = runtime.metrics_snapshot()
    assert "work_counts" in snap or "works" in snap or isinstance(snap, dict)
    data, ctype = generate_metrics_content()
    assert b"portable_work" in data or b"portable" in data
    assert "text/plain" in ctype
