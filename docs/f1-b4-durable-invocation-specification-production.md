# F1-B4 local DurableInvocationSpecification production capability

Baseline authorization: `main@1506b8738d4915ef04940b20e61b5bb7a17a7430`.

This production slice implements only local, non-executing invocation specification authority.

## Capability statement

```text
ProviderSemanticContract
= SUPPORTED locally

canonical semantic projection
= SUPPORTED locally

DurableInvocationSpecification
= SUPPORTED locally

Memory/SQLite opt-in durable authority
= SUPPORTED

semantic/provenance deterministic replay
= SUPPORTED

direct InvocationSpecificationRecorded event bypass
= CLOSED

P5 serialized authority import
= CLOSED / UNSUPPORTED

dispatch/spec binding
= UNPROVEN

provider transport completeness
= UNPROVEN

authoritative configured-provider binding at execution boundary
= UNPROVEN

RecoveryApplication consumption
= NOT SUPPORTED

retry materialization / permit / Attempt / dispatch / provider execution
= NOT SUPPORTED
```

## Provider replay binding authority

The local specification currently accepts an explicit `provider_binding_id` at capture time and combines it with the provider descriptor and exact semantic-contract digest into a deterministic `ProviderReplayBinding`.

This supports:

```text
stable provider replay-binding representation
same durable fact -> same declared binding
provider/contract/binding drift -> different or invalid durable fact
```

It does **not** yet prove:

```text
provider_binding_id
-> actual configured source-provider execution identity
```

The store does not resolve that identifier from an authoritative live registry/configuration boundary. Therefore this slice deliberately does not claim exact configured-provider execution authority.

That proof belongs to a later execution-boundary integration where the provider selected for the original dispatch can be bound against authoritative configuration. This slice does not introduce a registry resolver because doing so would expand the local specification responsibility into Runtime/dispatch authority.

## Internal integrity closure

A decoded `DurableInvocationSpecification` is accepted only if one closed chain holds:

```text
canonical_semantic_payload
-> ProviderSemanticProjection validation
-> semantic_identity

projection.contract_digest
== specification.semantic_contract_digest
== provider_binding.semantic_contract_digest

projection.payload.provider_id
== provider_binding.provider_id

provider binding fields
-> provider_binding.binding_digest

semantic/provenance identity payload
-> specification.id
```

The projection and provider-binding models own their own digest rules. `DurableInvocationSpecification` reuses those validators rather than duplicating their hash algorithms.

This prevents independently well-formed but mutually inconsistent hash islands from becoming a durable authority fact.

## Store ownership

Only the opt-in stores own this authority:

```text
InvocationSpecificationInMemoryStateStore
InvocationSpecificationSQLiteStateStore
```

The baseline stores used by Runtime are intentionally not expanded with `commit_invocation_specification`.

The opt-in stores enforce:

```text
commit_invocation_specification(...)
-> validate exact semantic/provenance graph
-> durable InvocationSpecificationRecorded fact

same exact input
-> idempotent replay

same authority identity + changed immutable meaning
-> fail closed

direct authority-event append
-> fail closed

serialized authority import
-> fail closed
```

SQLite authority survives close/reopen and reconstructs through the same specification validation boundary.

## Permanent negative guarantees

Historical specification auto-backfill is closed, not deferred:

```text
old request_ref / dispatch_ref / current provider state
-> infer missing historical authoritative specification
= REJECTED
```

A historical dispatch that did not originally bind an authoritative specification cannot be upgraded by reconstruction from current state.

## Deliberately unresolved integration obligations

Two strict obligations remain outside this production slice:

```text
PVP-007
provider transport must preserve every declared provider-semantic value

DIS-015
action-critical dispatch must bind the exact invocation_spec_ref
```

Neither obligation is evidence that the local durable specification authority is incomplete. They are execution-chain integration responsibilities and remain fail-closed/unimplemented until separately audited.
