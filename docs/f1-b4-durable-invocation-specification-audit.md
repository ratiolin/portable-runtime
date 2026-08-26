# F1-B4 durable invocation specification substrate audit

Baseline: `bce08d95434eb0ea9b0c1c80923829d02bb1e0f9` (`main` after B4-P4a merge).

This audit is not P4b implementation. It introduces no production authority, no retry materializer, no Runtime consumption, and no provider/reconciliation call. Its purpose is to answer one substrate question exposed by P4:

```text
RecoveryApplication(retry-request)
        ↓
what exact durable fact says what the original provider operation was?
```

## Existing authority chain

The runtime now supports, locally:

```text
InvocationDispatchCommitted
        ↓
RecoveryObservation
        ↓
optional objective verification / confirmed Outcome
        ↓
RecoveryDispositionRecorded
        ↓
RecoveryApplicationRecorded
        ↓
STOP
```

P4a deliberately stops before fresh orchestration. A `retry-request` application retains source dispatch/attempt/action/request/provider/work/run provenance and the source idempotency key, but it does not contain a provider request body and does not authorize execution.

## Confirmed substrate gap

The current durable execution graph can prove:

```text
which dispatch
which Attempt
which Action
which provider
which request identity
which idempotency identity
which Work / Run
which governance / qualification digests were used
```

It cannot reconstruct the complete provider-facing invocation body.

`InvocationPermit` does hold an immutable `request_snapshot`, but it is an in-process execution permit object. `InvocationDispatchCommitted` persists only the permit digest plus selected authority digests and execution identities; it does not persist that snapshot.

Therefore none of these is a valid replacement for durable invocation specification authority:

```text
request_ref alone
Action + StepAttempt
InvocationPermit digest
caller-owned CapabilityRequest still in memory
logs / tracing output
guessed parameters from Work description
```

## Do not persist the entire CapabilityRequest as one authority object

`CapabilityRequest` currently mixes multiple responsibility classes:

```text
operation semantics
+ orchestration scope
+ routing preferences
+ qualification-reference transport
+ authorization inputs
+ current lease/fencing state
+ derived effect/procedure state
+ arbitrary metadata / extra fields
```

A durable retry specification must not make old execution/admission state reusable merely because it was serialized.

The audit therefore requires a semantic partition rather than a raw request snapshot dump.

## Candidate responsibility object

Working name:

```text
DurableInvocationSpecification
```

Alternative external name:

```text
InvocationRequestSnapshot
```

The first name is preferred because the object is a specification/provenance fact, not an execution request and not an authorization token.

Its invariant is:

```text
durable specification exists
!= request currently authorized
!= current qualification exists
!= InvocationPermit exists
!= retry is permitted
!= provider may be invoked
```

## Candidate semantic partition

The audit distinguishes four classes of request state.

### A. Exact operation semantics

These define what operation was requested and must not be guessed during retry:

```text
capability
instruction
input_artifact_refs
parameters
constraints
resource_ref
subject_version_refs
requested effect floor
provider-visible semantic metadata, once explicitly typed/partitioned
```

For an exact retry, changing any of these means a new operation/specification, not reuse of the old specification.

`resource_ref` and `subject_version_refs` are included even though they are also authorization inputs. Persisting them preserves the target proposition; current authorization must still be evaluated again. If the target version is no longer admissible, retry must fail or require a new specification rather than silently retargeting.

### B. Replay identity / logical execution identity

These are not authorization but may be required to preserve the same external effect identity:

```text
idempotency_key
step_key / equivalent logical operation key
```

For `retry-idempotent`, the source idempotency identity must be preserved. It is provenance/replay identity only.

### C. Orchestration provenance/binding

These bind the historical specification to the source runtime graph but need not belong to content identity:

```text
source request_ref
work_ref
run_ref
source dispatch_ref
source attempt_ref
source action_ref
```

P4a already retains most of these. The future dispatch graph must bind the exact durable specification identity to the exact historical request/dispatch.

### D. Fresh execution/admission authority

These must never be revived from the durable specification:

```text
request id
selected provider authority
lease_owner
lease_generation
qualification digest / qualification satisfaction
AuthorizationGrant authority
policy decision state
governance requirement/snapshot digest
InvocationPermit
fresh Attempt identity
fresh dispatch identity
terminal completion authority
```

A retry may reconstruct operation intent from the durable specification, but all state in this class must be created or re-evaluated under current runtime conditions.

## Effect and procedure fields require re-derivation

Current request construction/boundary logic carries both caller-requested and derived execution state.

The specification should preserve the caller's requested floor/intent, for example:

```text
requested_effect_class
explicit requested procedure profile / constraints
```

It must not freeze a historically derived effective result as permanent authority:

```text
old effective_impact
old effect_semantics derived from then-current contract
old effective procedure profile
old reliability allowance
```

On retry, current capability/effect contracts must be able to raise requirements. A historical specification cannot downgrade a stricter current contract.

## Qualification-reference transport is not operation authority

`AssessmentContext` treats request metadata as an untrusted reference transport and resolves typed facts from the authoritative store. Current qualification refs include authorization, evidence, verification, relation, checkpoint, decision, obligation, and procedure-proof refs.

Those refs must not be converted into permanent satisfaction merely because a request specification is durable.

Open design choice for implementation:

```text
1. exclude qualification-reference transport from the canonical operation specification
   and let orchestration build a fresh qualification reference set;

or

2. retain source qualification refs as provenance only,
   while requiring full current re-resolution/revalidation before a permit.
```

The audit does not authorize either production choice. It only freezes the invariant that source refs do not equal current qualification.

## Arbitrary metadata is a blocker to a sound canonical specification

`CapabilityRequest` currently permits arbitrary `metadata` and extra fields. Providers receive the materialized request and may therefore observe values outside a small known field set.

This creates a completeness problem:

```text
allowlist too little metadata
→ retry may execute a semantically different provider request

persist all metadata blindly
→ old authorization / qualification / lease / derived state may be revived
```

Before production `DurableInvocationSpecification` can be considered complete, provider-visible metadata needs an explicit partition such as:

```text
semantic_metadata
vs
admission / qualification / runtime metadata
```

or an equivalent typed contract that makes unknown provider-visible fields fail closed.

A raw `dict[str, Any]` snapshot is not yet a proven canonical specification format.

## Content identity and request/spec binding

Candidate content identity:

```text
InvocationSpecificationKey =
H(
    schema,
    canonical exact operation semantics,
    replay identity fields required by retry
)
```

The content identity should not include fresh request identity, lease generation, selected provider, qualification/governance digests, or InvocationPermit.

A source request/dispatch must separately bind to the exact specification identity:

```text
source request_ref
    ↓
exact invocation_spec_ref
    ↓
InvocationDispatchCommitted(invocation_spec_ref)
```

This lets a future fresh request materialize from the same operation specification without reviving the old request identity.

A dispatch that predates this binding cannot be retroactively made retry-safe by looking up a request id or digest. Historical dispatches without an authoritative specification binding remain fail closed for automated retry.

## Persistence timing

For recovery to rely on the specification, the specification and its source request binding must be durable before the reality exit can become externally visible.

The audit permits implementation to choose the exact transaction seam later, but requires this ordering:

```text
canonical specification established
        ↓
durable specification + exact request/spec binding
        ↓
current qualification / governance / authorization
        ↓
InvocationPermit
        ↓
precommit / Attempt
        ↓
InvocationDispatchCommitted binds exact spec
        ↓
provider reality exit
```

If implementation instead commits specification during precommit, it must still prove that the same exact specification was used by the permit/provider request and that dispatch cannot commit without the binding. This is a production-proof question, not resolved by this audit.

## Retry materialization contract

A future retry may only proceed from:

```text
RecoveryApplication(retry-request)
+ exact source invocation_spec_ref
+ current admissible source graph
+ valid idempotency-domain binding
```

The future fresh request must satisfy:

```text
fresh request id
same exact operation specification
same required replay/idempotency identity
current Work/Run fencing state
current qualification resolution
current policy / governance / authorization
current effect/procedure/reliability requirements
fresh InvocationPermit
fresh StepAttempt
fresh dispatch commitment
```

Old request id, old Attempt, old permit, old lease generation and old dispatch are provenance only.

## Second blocker: idempotency-domain binding

The current runtime stores a source provider and idempotency key, and classifies some effects as idempotent/deduplicatable. It does not currently expose an explicit durable `idempotency_domain` / `deduplication_domain` contract.

Therefore this is not proven:

```text
same idempotency key
+ different selected provider
→ same external effect identity
```

Before automated retry can be authorized, one of the following (or an equivalent proof) is required:

```text
retry pinned to exact source provider

or

source and fresh provider prove the same durable idempotency/dedup domain
```

Fresh routing cannot silently transfer an idempotency key across an unproven provider boundary.

This blocker is independent from durable invocation specification persistence.

## Counterexamples frozen by this audit

```text
IS-001 request_ref alone cannot reconstruct provider operation semantics

IS-002 InvocationPermit/dispatch digest is not reconstructable specification authority

IS-003 caller memory is not durable invocation authority

IS-004 same specification identity + changed canonical operation semantics
       → rebound / invalid

IS-005 durable specification cannot restore old permit, lease, qualification,
       governance or selected-provider authority

IS-006 retry materialization must use a fresh request id while preserving the
       exact specification and required idempotency identity

IS-007 action-critical dispatch must bind an exact durable specification identity
       before automated retry can rely on it

IS-008 specification existence alone cannot authorize provider execution

IS-009 arbitrary/unpartitioned metadata cannot silently become canonical retry semantics

IS-010 fresh routing cannot move an idempotency key to another provider without
       an exact idempotency-domain proof

IS-011 historical dispatch without invocation_spec_ref cannot be auto-backfilled
       from request_ref / permit digest

IS-012 serialized/imported invocation specification authority remains P5/unproven
```

## Audit conclusion

The P4b retry blocker is real and cannot be solved safely by persisting `InvocationPermit.request_snapshot` verbatim.

A dedicated durable specification/provenance boundary is **REQUIRED**, but its production schema is **NOT YET AUTHORIZED** because two substrate details must be closed first:

```text
1. explicit provider-visible semantic metadata / request-field partition
2. explicit idempotency-domain binding for retry
```

The current execution boundary ordering remains appropriate and should be reused rather than replaced.

## Capability statement after this audit

```text
P4a local durable RecoveryApplication authority
= SUPPORTED

P4b retry consumption
= NOT SUPPORTED

Durable invocation specification object
= REQUIRED BY AUDIT / NOT IMPLEMENTED

Canonical provider-visible request field partition
= UNPROVEN

Idempotency-domain binding across retry
= UNPROVEN

Historical dispatch auto-backfill
= CLOSED

Serialized invocation-spec authority
= UNPROVEN / P5
```

The next production authorization, if any, should target the smallest substrate object after metadata/idempotency-domain counterexamples are resolved. It should not yet target P4b retry execution.
