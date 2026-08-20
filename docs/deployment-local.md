# Deployment: portable-local

Runs anywhere without Codex/Feishu/Docker/Prometheus.

```powershell
uv sync
.venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db status
.venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db work submit --title "Echo test" --description "hello" --kind generic-task
.venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db work list
.venv\Scripts\python.exe -m portable_runtime plugin validate examples/echo-provider
.venv\Scripts\python.exe -m portable_runtime plugin test examples/echo-provider
```

Runtime factory:

```python
from pathlib import Path
from portable_runtime.deployment.local import create_local_runtime

runtime = create_local_runtime(Path("data/portable-runtime.db"), Path("data/artifacts"))
```

Docker (Core not dependent on Docker):

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install fastapi uvicorn pydantic httpx prometheus-client
COPY src ./src
CMD ["python", "-m", "portable_runtime", "--state", "/data/portable-runtime.db", "status"]
```
