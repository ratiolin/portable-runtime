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

The built-in Codex provider derives its process sandbox from the capability,
not from request parameters: `reason.generate`, `code.read`, and `git.diff`
use `read-only`; `code.edit`, `code.test`, and `shell.exec` use
`workspace-write`; unknown capabilities fail closed to `read-only`. A caller
cannot request `danger-full-access` through the capability request. A
deployment may pass `sandbox_by_capability` only to tighten a canonical
capability (for example, `code.test` from `workspace-write` to `read-only`);
attempts to widen `reason.generate`, `code.read`, `git.diff`, or an unknown
capability to `workspace-write` are rejected.

Deployment-specific process isolation is an optional injected
`ExecutionBoundary`. The provider-neutral contract supplies a prepared
working directory/environment, a session directory, transcript redaction, and
cleanup; the base provider does not import or know about any deployment
package. Personal profiles may inject host-specific worktree, credential, or
container isolation while keeping those policies outside the portable runtime.

See `docs/provider-protocol.md` for the language-neutral stdio JSONL transport, `docs/plugin-authoring.md` for the file layout.
