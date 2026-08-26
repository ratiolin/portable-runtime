# F1-B4 reconciliation-only RecoveryApplication consumption audit

Baseline: `main@133270642419dfe3ebebf9e3f4680ac6b9aaa613`.

This audit opens only the design question:

```text
RecoveryApplication(reconciliation-request)
→ one reconciliation responsibility
→ RealityBoundary.reconcile
→ durable RecoveryObservation
→ STOP
```

It does not authorize production reconciliation consumption, retry materialization, `InvocationDispatchCommitted.invocation_spec_ref`, provider transport closure, fresh request/permit/Attempt/dispatch creation, provider `invoke`, terminal authority, governance discharge, historical backfill, or P5 import authority.

## Current-state findings

The current runtime still exposes a legacy recovery utility path:

```text
Runtime.reconcile(step_id)
→ latest StepAttempt
→ dispatch_recovery_mode(step, attempt)
→ request_ref + provider_id
→ CapabilityService.reconcile
→ RealityBoundary.reconcile
→ registry.get(provider_id)
→ provider.reconcile(request_id)
```

That path does not consume an exact `RecoveryApplicationRecorded` fact.

Current `RecoveryApplication` is a durable non-executing intent with exact disposition/dispatch/Attempt/Step/Action/request provenance, but it persists only `source_provider_id`; it does not carry an authoritative configured-provider execution binding.

Current `RecoveryObservationCommitRequest` and `RecoveryObservation` bind an exact dispatch graph but do not contain a first-class `recovery_application_ref`.

Current provider protocol exposes only:

```text
reconcile(request_id) -> CapabilityResult | None
```

There is no repeat-safe / side-effect-free / idempotent reconciliation contract.

Current provider registry explicitly allows unregister/register replacement under the same provider id. Therefore:

```text
same provider_id
!= same configured provider execution identity
```

for reconciliation as well as retry.

## Required authority chain

A future reconciliation consumer must begin from one exact durable application identity:

```text
RecoveryApplicationRecorded
application_kind = reconciliation-request
        ↓
reconstruct exact RecoveryDisposition
        ↓
reconstruct exact source dispatch / Attempt / Step / Action
        ↓
prove reconciliation target identity
        ↓
prove reconciliation repeatability model
        ↓
one reconciliation responsibility
        ↓
RealityBoundary.reconcile
        ↓
store-owned RecoveryObservation(
    dispatch_ref,
    recovery_application_ref,
    reported_status,
    ...
)
        ↓
STOP
```

A Step, Attempt, RecoveryDisposition, request id, provider id, or caller-supplied provenance is not reconciliation consumption authority.

## Crash seam: two different questions

The crash window must not be collapsed into a generic `RecoveryApplicationConsumed` fact:

```text
provider.reconcile returned
→ process crashes
→ RecoveryObservation not durably committed
```

There are two valid models.

### Model A: repeat-safe reconciliation

If an explicit provider reconciliation contract proves repeated reconciliation is safe for the same external subject, then the same reconciliation responsibility may be re-entered after a crash until a bound durable observation exists.

```text
explicit repeat-safe contract
+ no bound observation
→ repeat provider.reconcile allowed
```

### Model B: repeat-safety unproven

If repeat safety is unproven, then a crash after the external call but before observation persistence creates ambiguity.

```text
external reconciliation call may have happened
+ no durable observation
+ repeat-safety unproven
→ automatic repeat forbidden
```

If Model B later requires a durable pre-call fact, its semantics should describe reality-boundary progress, for example `RecoveryReconciliationAttemptRecorded`; it must not imply completed application consumption.

This audit does not authorize such a record.

## Provider target blocker

Automated reconciliation production is blocked for legacy dispatches by provider identity provenance.

Current durable history proves only:

```text
InvocationDispatchCommitted.provider_id
RecoveryApplication.source_provider_id
```

It does not prove:

```text
historical dispatch
→ exact configured provider execution identity
→ current reconciliation target
```

The local `ProviderReplayBinding` introduced for `DurableInvocationSpecification` remains representation-only because its `provider_binding_id` is capture input and is not resolved from authoritative execution configuration. It cannot be promoted into reconciliation authority by citation.

Therefore:

```text
legacy dispatch lacking original configured-provider binding
+ current registry provider with same id
→ NOT sufficient for automatic reconciliation
```

Historical reconciliation binding backfill from current registry state is closed.

A valid audit outcome is:

```text
reconciliation-only architecture
= VALID

automated reconciliation production for legacy dispatches
= BLOCKED
```

## First-class application-to-observation binding

Opaque `provenance_refs` must not carry application-consumption authority.

Future reconciliation-produced observations require an exact first-class binding:

```text
RecoveryObservation.recovery_application_ref
```

For a reconciliation-produced observation:

```text
RecoveryApplication A
→ RecoveryObservation O(recovery_application_ref=A)
```

Then completion/replay semantics can be expressed without a generic consumed flag:

```text
same A + exact bound O exists
→ provider calls = 0
```

A further reconciliation requires a new responsibility cycle:

```text
O
→ new RecoveryDisposition
→ new RecoveryApplication A2
→ new reconciliation responsibility
```

Thus:

```text
same RecoveryApplication
!= unlimited implicit reconcile loop
```

## Counterexample freeze

The audit freezes the following obligations.

```text
RC-001  Step / Attempt alone != reconciliation consumption authority
RC-002  RecoveryDisposition alone != reconciliation consumption authority
RC-003  exact RecoveryApplication(kind=reconciliation-request) is required
RC-004  non-reconciliation application kinds cannot enter reconcile
RC-005  dispatch / Attempt / Action are reconstructed from durable authority, not caller fields
RC-006  provider_id equality != authoritative reconciliation target identity
RC-007  registry replacement under same provider_id cannot silently retarget reconciliation
RC-008  historical dispatch without original provider execution binding cannot be upgraded from current registry
RC-009  reconciliation repeatability must be explicit before automatic post-crash repeat
RC-010  post-call/pre-observation crash with unproven repeatability must become ambiguous / fail closed
RC-011  reconciliation RecoveryObservation requires first-class recovery_application_ref
RC-012  same application + bound observation => provider calls = 0
RC-013  a new observation does not automatically create a new disposition or application
RC-014  reconciliation result != Outcome and != RecoveryDisposition
RC-015  reconciliation consumption creates no fresh CapabilityRequest / InvocationPermit / Attempt / dispatch / provider.invoke
RC-016  legacy Runtime.reconcile(step_id) cannot remain an authority bypass
```

## Production gate

No reconciliation production is authorized by this audit.

A later production slice may be authorized only after independent closure of:

```text
1. exact RecoveryApplication consumption authority
2. first-class application -> RecoveryObservation binding
3. authoritative source-provider reconciliation target binding
4. explicit reconciliation repeatability contract or fail-closed ambiguous-call model
5. crash semantics for pre-call / post-call-pre-observation / post-observation states
```

The production slice, if authorized, must still stop after a durable bound RecoveryObservation and must not create any fresh invocation execution authority.

## Explicitly unchanged

```text
local DurableInvocationSpecification
= CLOSED / SUPPORTED

PVP-007 provider transport completeness
= UNPROVEN

DIS-015 dispatch -> exact invocation_spec_ref
= UNPROVEN

reconciliation consumption production
= NOT AUTHORIZED

retry execution chain
= CLOSED

P5 portability/import authority
= CLOSED / UNSUPPORTED
```
