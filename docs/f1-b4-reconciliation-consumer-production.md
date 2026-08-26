# F1-B4 reconciliation consumer production closure

Baseline: `main@02aa704069a4645878c99431be7ba5fc16426201`.

This production slice implements the reconciliation consumer architecture frozen by PR #43 and no more.  On merge, the B4 recovery/reconciliation authority line is **CLOSED FOR V1** unless a concrete counterexample requires reopening it.

## Supported authority chain

```text
exact RecoveryApplication ref
→ reconstruct exact durable application/source graph
→ require application_kind = reconciliation-request
→ A-first completion check
   A exists → replay / provider calls = 0 / STOP
→ decode historical ProviderExecutionBinding (B)
→ resolve exact current configured execution identity
→ decode historical ReconciliationRepeatabilityAuthority (C)
→ verify exact request-id subject and current B/protocol/contract equivalence
→ exact-target reconciliation reality exit
→ store-owned application-bound RecoveryObservation commit (A)
→ STOP
```

The production caller surface is deliberately one opaque field:

```text
RecoveryReconciliationRequest(
    recovery_application_ref
)
```

Caller-supplied dispatch, request, provider, B, C, observation, or reported-status identity is not accepted.

## Production service

`portable_runtime.workflows.reconciliation_consumer` defines:

- `RecoveryReconciliationConsumer`
- `RecoveryReconciliationRequest`
- `RecoveryReconciliationResult`

The result is orchestration state, not durable authority. Its statuses are `replayed`, `completed`, `unavailable`, `unknown`, and `conflicted`.

Only `completed` or `replayed` together with an exact application-bound RecoveryObservation reference represents durable completion of that reconciliation responsibility.

A provider `CapabilityResult` by itself is never completion authority.

## A-first ordering

A is checked after exact durable application graph validation and before any current provider-registry/B/C dependency.

```text
A exists
→ no B resolution
→ no C evaluation
→ no provider call
→ replay existing completion
→ STOP
```

Current provider removal, B drift, C drift, or protocol/configuration drift cannot reopen an already durably completed historical responsibility.

A store support is capability-based. The consumer requires the exact opt-in surfaces:

```text
get_recovery_application_observation(...)
commit_recovery_application_observation(...)
```

If those surfaces are unavailable, the consumer is unavailable and crosses no provider boundary. There is no fallback to generic `commit_recovery_observation()`.

## Exact-target reality exit

`portable_runtime.core.reconciliation_boundary.RecoveryReconciliationRealityBoundary` owns one narrow operation:

```text
reconcile_exact_target(
    exact resolved provider object,
    exact historical request id,
)
```

It has no registry lookup and no recovery-policy interpretation. The consumer owns A/B/C eligibility; the exact-target boundary owns only one `provider.reconcile` reality exit.

The authoritative call graph never uses the legacy `RealityBoundary.reconcile(request_id, provider_id)` path, because that legacy method re-resolves the current provider by bare provider id.

## Crash and concurrency closure

For repeat-safe-only V1:

```text
provider call may have started or returned
+ A absent
+ exact C still eligible
→ exact reconciliation query may repeat
```

This includes the case where an earlier identical reconciliation query may still be externally in flight.

A's store transaction is the responsibility linearization point:

```text
first durable A semantics linearizes
same application + same later semantics → replay
same application + incompatible later semantics → rebound / fail closed
```

The consumer has no extra lock, no `RecoveryReconciliationAttemptRecorded`, and no `RecoveryApplicationConsumed` fact.

If the provider returned but A commit fails:

```text
provider call happened
A absent
→ orchestration result = unknown
→ no durable completion claim
```

A later invocation may repeat only through the same B/C eligibility chain.

## Legacy bypass closure

`Runtime.reconcile(step_id)` remains a compatibility-only fail-closed utility. Step/latest-Attempt identity cannot select one unique reconciliation responsibility.

It performs **zero provider reconciliation calls**, creates no RecoveryObservation, and cannot enter the authoritative consumer. It may conservatively project the local Step to `unknown` after a durably committed ambiguous dispatch; that projection is not reconciliation authority.

The legacy `RealityBoundary.reconcile(request_id, provider_id)` remains compatibility/non-authoritative. The production consumer never calls it.

## Explicit non-authorities

The consumer creates none of the following:

```text
CapabilityRequest
InvocationPermit
StepAttempt
InvocationDispatchCommitted
provider.invoke
Outcome
RecoveryDisposition
RecoveryApplication
RecoveryReconciliationAttemptRecorded
RecoveryApplicationConsumed
```

It does not open retry authority, P5/import authority, DurableInvocationSpecification retry execution, or Experience Governance production.

## Counterexample graduation

RCX-001 through RCX-025 are production PASS tests. The suite additionally proves:

- existing A short-circuits all current registry/B/C access;
- missing/wrong/rebound application authority produces zero provider calls;
- B mismatch/unavailability produces zero provider calls;
- C absence/subject mismatch/protocol-or-contract drift/current-only configuration produces zero provider calls;
- exact A+B+C crosses exactly reconciliation reality, never `provider.invoke`;
- provider return plus failed A commit is not durable completion;
- all same-application calls after A are zero-call replays;
- two overlapping repeat-safe reconciliations may both return externally, but only one incompatible A semantics can durably linearize;
- no fresh invocation or recovery-decision chain is created;
- P5 cannot manufacture application-bound completion authority.

## V1 closure verdict

After this production slice merges:

```text
B4 RecoveryDisposition authority              = SUPPORTED
B4 RecoveryApplication local authority        = SUPPORTED
A application-bound RecoveryObservation       = SUPPORTED
B configured-provider execution binding       = SUPPORTED
C reconciliation repeatability authority      = SUPPORTED
reconciliation consumer                       = SUPPORTED
legacy automated Runtime bypass               = CLOSED
legacy provider-id boundary path               = NON-AUTHORITATIVE
new durable reconciliation-attempt fact       = NOT REQUIRED FOR V1
RecoveryApplicationConsumed                   = NOT REQUIRED
historical authority backfill                 = CLOSED
retry                                          = CLOSED
P5 authority import                           = CLOSED / UNSUPPORTED

B4 recovery/reconciliation authority line      = CLOSED FOR V1
```

The next architectural stage, when separately authorized, is Experience Use Authority audit. This production slice does not begin that stage.
