# F1-B4 provider-visible request semantic partition audit

Baseline: `main@3d5e794640451be5ef8b08dd201ecb7627f39049`.

This audit is design/counterexample work only. It introduces no production invocation specification object, no retry materializer, no Runtime consumption, and no provider or reconciliation execution path.

Its purpose is to answer the blocker left by the durable invocation specification audit:

```text
CapabilityRequest / InvocationContext
        ↓
which values can a provider actually observe and use to change behavior?
        ↓
which of those values define reusable operation meaning?
```

## Executive conclusion

A single global field allowlist is not sufficient to define durable invocation semantics.

The current provider surface has two materially different forms:

1. in-process Python providers receive the full `CapabilityRequest` plus `InvocationContext`;
2. the stdio JSONL adapter projects a strict subset into `InvokeMessage`.

Built-in providers also consume different subsets. Therefore:

```text
provider-visible semantics
!= CapabilityRequest.model_dump()
!= one global core allowlist
!= metadata-is-nonsemantic
!= transport payload by itself
```

A future canonical invocation specification requires an explicit, versioned provider semantic contract that defines the semantic projection for both request and context inputs. Unknown provider-visible extensions must fail closed until classified.

This audit does **not** authorize such a production contract yet.

## Current materialization surfaces

### CapabilityProvider interface

The provider protocol is:

```text
invoke(request: CapabilityRequest, context: InvocationContext)
```

This is the widest provider surface. A Python provider can inspect every declared request field, every declared context field, and any extra request field admitted by Pydantic.

`CapabilityRequest` currently uses `extra="allow"`. Therefore an unrecognized caller-supplied extension can remain observable by an in-process provider even when core code does not know what it means.

This creates a hard rule for durable replay:

```text
core does not understand field
!= field is non-semantic
```

### stdio JSONL provider

The stdio adapter does not forward the full request. It constructs `InvokeMessage` with:

```text
id
capability
work_id
run_id
instruction
input_artifact_refs
parameters
```

It does not forward, among other fields:

```text
constraints
metadata
preferred_provider_ids
excluded_provider_ids
idempotency_key
step_key
actor_ref
resource_ref
subject_version_refs
effect_class
lease_generation
lease_owner
timeout_seconds
```

`timeout_seconds` is consumed locally by the adapter as execution control rather than sent to the child process.

Therefore the stdio transport is already a provider-specific projection boundary.

### Codex provider

The Codex provider observes at least:

```text
instruction
parameters.prompt
parameters.repo
parameters.model
capability
timeout_seconds
run_id
request.id
```

It also derives the process sandbox from `capability` and deployment configuration.

Several of these values have different responsibility classes:

```text
instruction / model / repo / capability
    can change the operation presented to Codex

timeout_seconds
    controls execution lifetime

run_id / request.id
    are used for transcript/provenance naming
```

This is exactly why a field-name-only canonicalizer is insufficient.

### Feishu providers

The current Feishu providers observe narrower projections:

```text
capability
instruction
request.id
```

Again, this differs from Codex and stdio.

## InvocationContext is also provider-visible

`InvocationContext` includes values such as:

```text
runtime_id
work_id
run_id
metadata
lease_generation
idempotency_key
```

The provider interface makes this context available directly to Python providers.

A future semantic partition therefore cannot classify only `CapabilityRequest`. It must explicitly state whether each provider-observable context value is:

```text
provider_semantic
orchestration_provenance
runtime_ephemeral
forbidden_unknown
```

If a provider uses `context.runtime_id` or `context.metadata` to change the external operation, that dependency must either become part of the declared semantic contract or make the provider ineligible for exact automatic retry.

## Required responsibility classes

The audit freezes the following vocabulary for future design work. These are semantic classes, not yet production schema fields.

### 1. `provider_semantic`

Values intentionally allowed to affect provider operation meaning and therefore candidates for canonical specification identity.

Examples may include:

```text
capability
instruction
input_artifact_refs
operation parameters
provider-declared semantic extensions
resource/version target when provider-visible operation meaning depends on them
```

A field belongs here because an explicit provider semantic contract says so, not because core guessed from the field name.

### 2. `orchestration_provenance`

Values that bind the invocation to historical workflow identity but do not by themselves authorize execution or define reusable provider operation meaning.

Examples:

```text
work_id
run_id
source request ref
source Attempt / Action / dispatch refs
```

Some transports may expose these values to providers for correlation. Exposure alone does not make them canonical operation semantics.

### 3. `qualification_transport`

Values used to resolve current qualification, policy, authorization, or governance state.

Examples include typed references transported through request metadata:

```text
authorization_refs
evidence_refs
verification_refs
checkpoint_refs
decision_refs
qualification_refs
```

These must never become reusable operation authority merely because the original provider-facing request object contained them.

### 4. `runtime_ephemeral`

Values that belong to one concrete execution attempt and must be freshly derived or minted.

Examples:

```text
request id as runtime request identity
lease owner / generation
selected provider authority
qualification digest
governance snapshot / requirement digest
InvocationPermit
Attempt identity
dispatch commitment
current effective effect/procedure state
execution timeout when treated as runtime control
```

A provider protocol may expose some of these for correlation. They remain non-reusable unless a separate stable provider semantic value is explicitly defined.

### 5. `forbidden_unknown`

Any provider-visible field or context extension that has no explicit classification.

For action-critical durable replay:

```text
unknown provider-visible value
→ STOP
```

The system must not silently omit it from canonical identity, because omission can produce a different provider operation under the same specification identity.

It also must not silently include the raw object, because doing so can persist qualification/admission/runtime authority.

## Why `metadata` cannot receive one global classification

`CapabilityRequest.metadata` is currently arbitrary. Core uses it for many control-plane concerns, while third-party Python providers are technically able to read it directly.

Therefore neither of these rules is valid:

```text
metadata is always semantic
```

or:

```text
metadata is always non-semantic
```

A future provider semantic contract needs a typed extension mechanism, for example conceptually:

```text
ProviderInvocationSemanticContract
    request_semantic_fields
    context_semantic_fields
    semantic_extension_schema
    contract_version / digest
```

The exact API is intentionally not frozen here.

## Provider contract, not provider implementation introspection

The runtime must not define durable semantics by source-code inspection such as “which attributes this provider currently reads.”

Source inspection is useful for this audit only.

Production semantics must be explicit and stable because:

```text
provider implementation changes
without contract change
```

must not silently change canonical operation meaning.

A future provider semantic contract therefore needs stable identity/versioning and compatibility rules.

## Transport consistency requirement

A provider semantic contract is not enough unless the actual materialization path preserves it.

For every provider execution, the following must eventually be provable:

```text
canonical semantic projection
        =
semantic values materialized into provider-visible request/context
        =
semantic values covered by durable specification identity
```

If a transport drops a field declared semantic, execution must fail closed.

Example:

```text
provider declares semantic extension X
stdio InvokeMessage cannot carry X
→ provider/transport pair is not retry-safe
```

The runtime must not “best effort” such a mismatch.

## Fresh request identity versus provider-visible identity

The current design requires retry to mint a fresh `CapabilityRequest.id`.

But some providers/transports can observe request id. Therefore a provider that treats request id as operation semantics creates a conflict:

```text
fresh request identity required
+
provider treats request id as stable operation meaning
```

Such a provider cannot support exact automatic retry unless the provider contract exposes a separate stable replay/operation identity (for example the idempotency identity) and treats request id as correlation only.

This audit therefore freezes:

```text
request.id provider-visible
!= request.id reusable operation identity
```

unless a future explicit contract proves otherwise.

## Timeout and other execution controls

`timeout_seconds` demonstrates another ambiguity. Codex and stdio consume it as local execution control. It can affect whether the local caller waits, but it is not necessarily part of the remote operation meaning.

The durable specification design must therefore distinguish:

```text
operation semantics
from
execution envelope
```

A changed execution timeout should not automatically create a new operation identity unless the provider semantic contract declares that timeout changes provider-visible operation behavior.

## Routing fields

`preferred_provider_ids`, `excluded_provider_ids`, constraints used solely for routing, and selected-provider state are not automatically provider operation semantics.

However, this audit does not globally remove `constraints` from future durable specification identity. A constraint can represent either:

```text
routing/admission constraint
or
operation semantic constraint
```

The future contract must classify it explicitly.

## Frozen counterexamples

The audit freezes the following production obligations.

### PVP-001 — unknown extra request field

An action-critical request carrying an undeclared provider-visible extra field must not receive a reusable canonical specification identity.

### PVP-002 — arbitrary metadata

Unpartitioned metadata must not silently enter or silently disappear from reusable semantics.

### PVP-003 — typed semantic extension

A provider must be able to declare an explicit typed semantic extension; changing its value must change canonical semantic identity.

### PVP-004 — qualification transport exclusion

Qualification/policy/authorization references must be excluded from reusable provider operation authority and re-resolved fresh.

### PVP-005 — runtime ephemeral exclusion

Lease, permit, Attempt, dispatch and current admission state must not enter reusable semantic identity.

### PVP-006 — provider semantic contract identity

Canonical projection must be bound to a stable provider semantic contract version/digest so contract drift cannot silently reinterpret an old specification.

### PVP-007 — transport completeness

A transport that cannot materialize every declared provider-semantic value must fail closed.

### PVP-008 — request/context consistency

Provider-semantic dependencies in `InvocationContext` require the same explicit treatment as request fields.

### PVP-009 — fresh request id

Fresh retry request identity must not accidentally change operation meaning. Providers that treat request id as semantic without a separate stable operation identity are not exact-retry eligible.

### PVP-010 — implementation drift

Provider implementation may not add a new semantic dependency without corresponding semantic-contract change/revalidation.

### PVP-011 — no core source introspection authority

Production canonicalization may not infer semantics by inspecting Python source or attribute access.

### PVP-012 — no production authorization

The existence of a semantic partition contract must not itself create DurableInvocationSpecification, retry permission, InvocationPermit, Attempt, dispatch or provider execution authority.

## Audit decision

The blocker from the prior invocation-spec audit is refined as follows:

```text
provider-visible semantic partition
= REQUIRED

single global CapabilityRequest allowlist
= REJECTED

raw metadata persistence
= REJECTED

unknown provider-visible extension defaulting to non-semantic
= REJECTED

provider semantic contract / typed extension mechanism
= REQUIRED BY DESIGN

production API/schema
= NOT YET AUTHORIZED
```

## What remains before DurableInvocationSpecification production

After this audit, two substrate questions remain logically separate:

```text
1. provider semantic projection contract
2. replay/idempotency-domain validity
```

The next audit should answer the narrower retry question first:

```text
Can the first automated retry version require
retry target provider == exact source provider?
```

If yes, a cross-provider idempotency-domain abstraction is not required for the first safe retry implementation.

Only after both audits close should production work define:

```text
canonical semantic projection
→ deterministic invocation specification identity
→ store-owned durable specification
→ exact dispatch/spec binding
```

Historical dispatches without an original authoritative specification binding remain non-upgradable and fail closed.

## Non-scope

This audit does not authorize:

```text
DurableInvocationSpecification production schema
provider semantic contract production API
semantic extension registry
retry materialization
cross-provider idempotency domain
Runtime recovery consumption
reconciliation consumption
InvocationPermit reuse
Attempt reuse
dispatch reuse
provider execution
P5 import / portability authority
```
