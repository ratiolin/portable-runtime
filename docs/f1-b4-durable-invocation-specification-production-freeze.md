# F1-B4 DurableInvocationSpecification production counterexample freeze

Baseline: `main@687f282e90bca484102b24692218a0bc9a138ae6`.

This document freezes the smallest production authority that may be implemented next. It is still an audit/design slice: no production source is introduced here.

The two prerequisite audits are now closed at design level:

```text
provider-visible semantic partition
→ explicit/versioned provider semantic contract required

first-version replay target
→ exact stable source-provider binding only
→ generic cross-provider idempotency-domain abstraction not required
```

The purpose of this freeze is to prevent the next implementation from expanding into retry orchestration.

## Exact production slice authorized after this audit

The next implementation may introduce only:

```text
ProviderSemanticContract
        ↓
canonical provider-semantic projection
        ↓
DurableInvocationSpecification
        ↓
store-owned durable commit/replay
        ↓
STOP
```

It may also introduce the minimum stable provider replay binding needed to make the specification's source-provider provenance non-ambiguous.

It must not introduce:

```text
Runtime consumption
RecoveryApplication consumption
retry request materialization
InvocationPermit issuance from a specification
automatic Attempt creation
dispatch/spec production integration
provider invocation
cross-provider retry
P5 import authority
```

## Responsibility split

### ProviderSemanticContract

This object declares what a particular provider integration treats as operation semantics.

Conceptually it must bind:

```text
contract identity/version
request semantic fields
context semantic fields
typed semantic extension rules
transport/materialization compatibility identity
```

It is classification authority only.

```text
ProviderSemanticContract exists
!= invocation specification exists
!= retry is permitted
!= provider is authorized
```

### Canonical semantic projection

Given one concrete request/context plus one exact semantic contract, projection produces a canonical payload containing only declared reusable operation meaning.

It must:

```text
include every declared semantic value
exclude qualification transport
exclude runtime-ephemeral authority
reject unknown provider-visible extensions
be deterministic under key ordering / representation noise
bind the semantic contract identity
```

### Provider replay binding

The specification must preserve which configured provider execution identity the original semantic projection was prepared for.

For this first production slice it is provenance/replay binding only. It does not itself prove external idempotency-domain equivalence and does not authorize retry.

At minimum, binding must be stronger than `provider_id` alone and must detect configured provider/semantic-contract drift.

The final field names are not important to this freeze. A candidate may contain:

```text
provider_id
provider version / descriptor binding digest
semantic contract digest
stable configured provider binding identity
```

The implementation must fail closed if it cannot construct a stable binding.

### DurableInvocationSpecification

A durable specification is a local, immutable, content-addressed authority over reusable operation meaning plus source provenance.

Conceptually:

```text
specification content identity
    = schema
    + canonical semantic projection
    + semantic contract digest
    + replay identity where operation replay requires it
```

Source provenance may additionally bind:

```text
source request id
work/run refs
provider replay binding
source idempotency identity
```

Whether provenance fields participate in content identity must be explicit. They may not be accidentally included just because they were available in the caller object.

## Source request capture versus historical reconstruction

The initial invocation is allowed to create a durable specification from the live request only through the store-owned specification commit authority.

This is not the rejected shortcut:

```text
old caller request still in memory
→ authorize retry
```

The distinction is:

```text
initial authoritative capture before/for dispatch
→ store validates contract/projection
→ durable specification fact
```

versus:

```text
historical request_ref / caller object / logs
→ guess missing old specification
```

The latter remains forbidden.

## Deterministic identity and rebound

The same exact canonical semantic payload under the same contract must produce the same specification identity.

If the same specification identity is presented with changed semantics, changed contract binding, changed replay identity, or changed provider binding where that binding is part of the immutable durable fact:

```text
semantic rebound
→ reject
```

Never overwrite.

## Store ownership

Like RecoveryDisposition and RecoveryApplication, specification authority must be store-owned.

Required local behavior:

```text
Memory commit/replay
SQLite writer-serialized commit/replay
SQLite close/reopen reconstruction
direct authority-event append rejection
same-id changed-semantics rebound rejection
```

A caller may request specification capture but may not append `InvocationSpecificationRecorded` directly.

## Import posture

P5 remains unproven.

Therefore:

```text
serialized InvocationSpecificationRecorded import
→ fail closed
```

until a later portability authority explicitly proves bundle compatibility and provenance.

## Source binding

The specification must bind its source request identity at initial capture.

A future dispatch binding must prove:

```text
request used for permit evaluation
→ exact specification ref
→ exact semantic materialization
```

but this production freeze does not authorize dispatch integration yet.

Historical dispatches that predate specification binding remain non-upgradable.

## Semantic contract drift

A provider semantic contract is part of the specification's interpretation.

Therefore:

```text
same semantic payload
+ different semantic contract identity/version
→ different specification identity or explicit incompatibility
```

An old specification must never be silently reinterpreted under a new contract.

## Runtime-ephemeral changes

Changing any of the following must not, by itself, change reusable operation identity unless explicitly declared provider-semantic by the exact contract:

```text
request.id
lease owner / generation
qualification refs
authorization refs
governance digests
selected-provider authorization
InvocationPermit
Attempt / dispatch ids
current procedure/effect assessment
```

Fresh execution will recreate these later.

## Semantic changes

Changing a declared provider-semantic value must change canonical semantic identity.

Examples:

```text
instruction
operation parameter
input artifact
provider-declared semantic extension
semantic target/version if declared operation-semantic
```

No changed semantic value may replay under the old specification identity.

## Replay identity

For retry-eligible side effects, the source idempotency identity must be retained separately and exactly.

This is deliberately not treated as authorization.

The implementation may bind it into the durable specification fact, but must preserve the distinction:

```text
same operation semantics
!= same external replay identity
```

Both are required later for retry.

## Dispatch integration remains a blocker

The next minimal production implementation stops before dispatch integration.

After it exists, a separate slice must prove:

```text
InvocationPermit evaluated exact semantic specification
InvocationDispatchCommitted binds exact invocation_spec_ref
provider-facing request/context materializes the same semantics
```

A database `invocation_spec_ref` field alone will not be sufficient.

## Frozen counterexamples

### DIS-001 — explicit contract required

Action-critical specification capture without an explicit provider semantic contract must fail closed.

### DIS-002 — unknown provider-visible extension

An unclassified request/context extension must prevent canonical specification capture.

### DIS-003 — runtime authority excluded

Changing request id, lease/fencing state, qualification transport, or other runtime-ephemeral state must not silently become reusable operation identity.

### DIS-004 — semantic change changes identity

Changing a declared provider-semantic value must change canonical specification identity.

### DIS-005 — contract drift changes interpretation

Changing semantic-contract identity/version must not reuse the same specification identity.

### DIS-006 — provider id alone insufficient

Specification capture must fail if provider replay binding cannot be made stronger than provider-id string equality.

### DIS-007 — exact idempotency identity retained

Retry-eligible side-effect specifications must retain the exact source idempotency identity; missing identity fails closed.

### DIS-008 — deterministic same-input replay

Same request semantics + same contract + same immutable provenance must replay the same durable specification.

### DIS-009 — specification rebound

Same specification/event identity with changed immutable semantics/provenance must be rejected.

### DIS-010 — Memory store ownership

Memory authority creation must occur through `commit_invocation_specification`, not direct event append.

### DIS-011 — SQLite durability

SQLite specification authority must survive close/reopen and replay deterministically.

### DIS-012 — P5 import fail closed

Serialized invocation-specification authority remains non-importable.

### DIS-013 — source request binding

A durable specification must bind the exact source request identity at initial capture; request-ref-only historical reconstruction remains forbidden.

### DIS-014 — non-executing authority

Specification capture must create no qualification, authorization, permit, Attempt, dispatch, provider call, or RecoveryApplication consumption.

### DIS-015 — dispatch binding remains required

Action-critical dispatch without exact `invocation_spec_ref` binding remains not retry-safe and must not be treated as such.

### DIS-016 — historical backfill forbidden

Old dispatch/request history without original specification binding cannot be retroactively upgraded from current mutable state.

### DIS-017 — provider binding drift

Same provider id with changed stable provider replay binding/semantic contract must not replay the old specification as if nothing changed.

### DIS-018 — retry materialization absent

The minimal production slice must still expose no API that converts a specification directly into an authorized retry execution.

## Graduation plan

The next **minimal production** slice should graduate only:

```text
DIS-001 through DIS-014
DIS-017
DIS-018 (as a negative invariant)
```

while keeping these as later integration blockers:

```text
DIS-015 dispatch/spec exact binding
DIS-016 historical backfill remains forbidden permanently
```

`DIS-016` can become a passing fail-closed test without enabling backfill. `DIS-015` should remain blocked until dispatch integration is explicitly authorized.

## Audit decision

```text
ProviderSemanticContract production
= AUTHORIZED ONLY AS NON-EXECUTING CLASSIFICATION SUBSTRATE

canonical semantic projection
= AUTHORIZED

stable local provider replay binding
= AUTHORIZED AS PROVENANCE/BINDING ONLY

DurableInvocationSpecification local production
= AUTHORIZED AFTER COUNTEREXAMPLES FREEZE

Memory / SQLite store-owned commit/replay
= AUTHORIZED

Runtime consumption
= NOT AUTHORIZED

dispatch/spec integration
= NOT AUTHORIZED

retry materialization
= NOT AUTHORIZED

cross-provider retry
= NOT AUTHORIZED

P5 import authority
= NOT AUTHORIZED
```

## Non-scope

This freeze does not authorize:

```text
RecoveryApplication consumption
fresh CapabilityRequest materialization from spec
Runtime retry API
InvocationPermit issuance from spec
Attempt or dispatch creation from spec
provider invocation
reconciliation consumption
cross-provider idempotency domain
historical spec backfill
P5 serialization/import authority
```
