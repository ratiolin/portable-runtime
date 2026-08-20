# Provider API

Implement the `CapabilityProvider` contract:

```python
from portable_runtime.core.capabilities import (
    CapabilityRequest, CapabilityResult, InvocationContext,
    ProviderDescriptor, ProviderHealth,
)

class UppercaseProvider:
    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            id="uppercase",
            name="Uppercase Provider",
            version="1.0.0",
            capabilities=["text.uppercase"],
            tags={"side-effect-free"},
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id="uppercase", available=True)

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        text = request.instruction or ""
        return CapabilityResult(
            request_id=request.id,
            provider_id="uppercase",
            status="succeeded",
            message=text.upper(),
        )

    async def cancel(self, request_id: str) -> None:
        return None
```

Register at runtime:

```python
from portable_runtime.core.runtime import Runtime
from portable_runtime.providers.fake import EchoProvider

runtime = Runtime()
runtime.registry.register(UppercaseProvider())
runtime.registry.disable("uppercase")
runtime.registry.enable("uppercase")
result = await runtime.run_capability(work.id, "text.uppercase", instruction="hello")
```

For a tiny provider, use the decorator:

```python
from portable_runtime.plugin import provider
from portable_runtime.core.capabilities import CapabilityRequest, CapabilityResult

@provider(id="echo", version="1.0.0", capabilities=["text.echo"])
async def invoke(request: CapabilityRequest) -> CapabilityResult:
    return CapabilityResult(
        request_id=request.id,
        provider_id="echo",
        status="succeeded",
        message=request.instruction,
    )
```

Providers return structured `status` (`succeeded/failed/unavailable/needs-input/cancelled`) and `output_artifact_refs/evidence_refs`. They must not write Runtime state directly; Runtime records `Action/Outcome` around invocation.

Capabilities are open strings, e.g. `reason.generate, code.edit, verify.http, human.approve, notify.send`. Core never hardcodes the set.

See `docs/provider-protocol.md` for the language-neutral stdio JSONL transport, `docs/plugin-authoring.md` for the file layout.
