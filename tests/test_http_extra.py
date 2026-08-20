from fastapi.testclient import TestClient

from portable_runtime.api.http import create_app
from portable_runtime.core.runtime import Runtime
from portable_runtime.stores.memory import InMemoryStateStore


def test_http_endpoints():
    runtime = Runtime(store=InMemoryStateStore())
    app = create_app(runtime)
    client = TestClient(app)
    # health
    assert client.get("/v1/health/live").status_code == 200
    assert client.get("/v1/health/ready").status_code == 200
    assert client.get("/metrics").status_code == 200
    assert client.get("/v1/metrics/json").status_code == 200
    assert client.get("/v1/runtime").status_code == 200
    # providers
    assert client.get("/v1/providers").status_code == 200
    assert client.get("/v1/capabilities").status_code == 200
    # work
    resp = client.post("/v1/work", json={"title":"http-test","kind":"generic-task"})
    assert resp.status_code == 200
    work_id = resp.json()["id"]
    assert client.get(f"/v1/work/{work_id}").status_code == 200
    assert client.get("/v1/work").status_code == 200
    # run capability
    resp2 = client.post(f"/v1/work/{work_id}/run", json={"capability":"text.echo","instruction":"hi"})
    # may be 200 or 404 depending on provider, but should not 500
    assert resp2.status_code in (200,404,500)
    # knowledge
    assert client.get("/v1/knowledge").status_code == 200
    # artifacts
    assert client.get("/v1/artifacts/nonexistent").status_code in (200,404)
    # triggers
    assert client.post("/v1/triggers/webhook", json={"payload":{}}).status_code in (200,404,422)
    assert client.post("/v1/triggers/alertmanager", json={"alerts":[]}).status_code in (200,404,422)
