# portable-runtime

[![CI](https://github.com/ratiolin/portable-runtime/actions/workflows/ci.yml/badge.svg)](https://github.com/ratiolin/portable-runtime/actions/workflows/ci.yml) [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=portable-runtime&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=portable-runtime) [![Coverage](https://sonarcloud.io/api/project_badges/measure?project=portable-runtime&metric=coverage)](https://sonarcloud.io/summary/new_code?id=portable-runtime) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](pyproject.toml)
- [Code of conduct](CODE_OF_CONDUCT.md) - [Contributing](CONTRIBUTING.md) - [MIT license](LICENSE) - [Security](SECURITY.md)

Portable runtime for durable **Work / Run** orchestration with pluggable
**Provider / Trigger / Store / Workflow**. Core never depends on a model,
harness, OS, message platform, monitoring system or external tool.

## Quick start

```powershell
uv sync
uv run runtime init
uv run runtime start
```

In another terminal:

```powershell
uv run runtime provider list
uv run runtime plugin install examples/echo-provider
uv run runtime work submit --kind generic-task --title "Echo test" --capability text.echo --description "hello"
uv run runtime work list
# module entry:
# .venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db status
# .venv\Scripts\python.exe -m portable_runtime plugin validate examples/echo-provider
# .venv\Scripts\python.exe -m portable_runtime work submit --title "Echo test" --description "hello" --kind generic-task --capability text.echo
```

Export / import state without any model or network:

```powershell
.venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db state export runtime-state.json
.venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db state import runtime-state.json
```

## Architecture

```
Work / Run / Artifact / Evidence / Knowledge
                    |
              Runtime + Store
                    |
          CapabilityService + Router
                    |
             ProviderRegistry
                    |
      in-process or stdio-jsonl providers
```

- **Provider** – implements `CapabilityProvider`; open capability strings (`text.echo`, `verify.http`, ...).
- **Trigger** – creates Work (`webhook`, `schedule`, `alertmanager`-compatible).
- **Store** – `StateStore / ArtifactStore / EventStore` on `src/portable_runtime/interfaces`; `SQLite` and `InMemory` / `Filesystem` included.
- **Workflow** – orchestrates `context.invoke(capability, ...)`; built-ins: `generic_task`, `incident_repair`, `daily_scan`, `knowledge_consolidation`.

See [docs/architecture.md](docs/architecture.md),
[docs/provider-api.md](docs/provider-api.md),
[docs/provider-protocol.md](docs/provider-protocol.md),
[docs/plugin-authoring.md](docs/plugin-authoring.md),
[docs/workflow-authoring.md](docs/workflow-authoring.md),
[docs/store-api.md](docs/store-api.md),
[docs/state-migration.md](docs/state-migration.md) and
[docs/deployment-local.md](docs/deployment-local.md).

## Plugin authoring

Copy a template and declare capabilities – no Core change required:

```powershell
Copy-Item -Recurse templates/provider-python my-provider  # optional local template
# or start from examples/echo-provider
```

`examples/echo-provider/manifest.json`:

```json
{
  "id": "echo",
  "name": "Example Echo Provider",
  "version": "1.0.0",
  "protocol_version": "1",
  "transport": "stdio-jsonl",
  "command": ["python", "provider.py"],
  "capabilities": ["text.echo"]
}
```

Validate and test:

```powershell
uv run runtime plugin validate examples/echo-provider
# or
.venv\Scripts\python.exe -m portable_runtime plugin test examples/echo-provider
```

## Deployment

Local (no Docker required):

```python
from pathlib import Path
from portable_runtime.deployment.local import create_local_runtime

runtime = create_local_runtime(Path("data/portable-runtime.db"), Path("data/artifacts"))
```

Reference profile: `examples/personal-platform-profile` is a minimal trigger/provider mapping example (Schedule/Alertmanager + verifiers) you can adapt to your own deployment.

## Development

```powershell
uv sync --extra dev
uv run ruff check .
uv run mypy src
uv run pytest
```

---

Standalone portable runtime for durable execution.


