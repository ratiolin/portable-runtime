# Plugin authoring

You can add a provider without reading the whole runtime. Only this document +
the runnable `examples/echo-provider/` example is required.

## 1. Copy the example

```powershell
Copy-Item -Recurse examples/echo-provider my-provider
```

`examples/echo-provider/` contains:

```
manifest.json
provider.py   # <50 lines example
```

## 2. Edit manifest

```json
{
  "id": "uppercase",
  "name": "Uppercase Provider",
  "version": "1.0.0",
  "protocol_version": "1",
  "transport": "stdio-jsonl",
  "command": ["python", "provider.py"],
  "capabilities": ["text.uppercase"]
}
```

`id` must be stable, `capabilities` are open strings (e.g. `text.uppercase`). Do not use a closed enum.

## 3. Implement the provider

For an external stdio plugin, edit the copied `provider.py`.  It reads one
JSON request per stdin line and writes one result per stdout line.  The
language-neutral wire contract is described in
`docs/provider-protocol.md`.

For an in-process Python provider (registered directly with
`ProviderRegistry`, not loaded by `PluginManager`), the decorator form is the
smallest implementation:

```python
from portable_runtime.plugin import provider
from portable_runtime.core.capabilities import CapabilityRequest, CapabilityResult

@provider(id="uppercase", version="1.0.0", capabilities=["text.uppercase"])
async def invoke(request: CapabilityRequest) -> CapabilityResult:
    return CapabilityResult(
        request_id=request.id,
        provider_id="uppercase",
        status="succeeded",
        message=(request.instruction or "").upper(),
    )
```

## 4. Validate

```powershell
.venv\Scripts\python.exe -m portable_runtime plugin validate ./my-provider
.venv\Scripts\python.exe -m portable_runtime plugin test ./my-provider
```

`validate` checks `manifest.json` and capabilities. `test` runs the conformance suite:

```
manifest valid
health works
capabilities declared
invoke accepted
result schema valid
timeout handled
cancel handled or explicit unsupported
reconcile handled or explicit unsupported; unresolved effects remain unknown
invalid input returns structured error
provider exit does not kill Runtime
```

## 5. Register / reload

```python
from portable_runtime.plugin import PluginManager
from portable_runtime.core.registry import ProviderRegistry

manager = PluginManager(ProviderRegistry())
record = await manager.load(Path("./my-provider"))
manager.enable("uppercase")   # next request routes immediately
manager.disable("uppercase")  # next request stops routing
manager.reload("uppercase")   # for stdio: respawn without restarting Runtime
manager.remove("uppercase")
```

CLI:

```powershell
runtime plugin validate ./my-provider
runtime plugin test ./my-provider
runtime provider list
runtime provider enable uppercase
runtime provider disable uppercase
```

Rules:

- Providers must not write `Work/Run/Artifact/Evidence` directly.
- Providers must not import `core` business logic.
- Add a provider without modifying `core/`, `router`, `store` or `workflow engine`.

If you need a new capability name, just declare it; no Core change required.
