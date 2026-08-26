# F1-B4 P4 RecoveryApplication design / counterexample audit

Baseline: `a94fb67f99318a83ff696a78bbda7ec40919b57b` (P3 merge into the intended B4 lineage).

This audit does not authorize RecoveryApplication production or Runtime consumption. It defines the next responsibility boundary and records one blocking substrate gap discovered after P3 became durable.

## Established input authority

P3 now establishes this local durable chain:

```text
InvocationDispatchCommitted
        ↓
exact durable Attempt / Step / Action / Run / Work graph
        ↓
RecoveryObservation set
+ optional confirmed Outcome set
        ↓
store-derived recovery/effect classification
        ↓
policy identity + policy responsibility
        ↓
RecoveryDispositionRecorded
```

`RecoveryDispositionRecorded` is a decision fact. It is not execution authority and does not create a retry, reconciliation call, fresh Attempt, InvocationPermit, dispatch commitment, terminal completion, or governance discharge.

## P4 responsibility split

P4 must not collapse application intent and execution consumption into one module.

```text
P4a RecoveryApplication authority
RecoveryDispositionRecorded
        ↓
store-owned exact reconstruction
        ↓
one durable RecoveryApplication intent
        ↓
STOP

P4b orchestration consumption
RecoveryApplication intent
        ↓
materialize an eligible fresh orchestration request/responsibility
        ↓
existing qualification / governance / authorization boundary
        ↓
fresh InvocationPermit where execution is required
        ↓
fresh StepAttempt
        ↓
fresh InvocationDispatchCommitted
        ↓
RealityBoundary provider exit
```

P4a is therefore non-executing. P4b, if later authorized, must consume P4a rather than reading a `RecoveryDispositionRecorded` directly.

## P4a candidate authority contract

The caller-side commit request should carry only an exact durable disposition identity:

```text
RecoveryApplicationCommitRequest
    disposition_ref
```

The caller must not declare application semantics, source dispatch, source Attempt, provider, request id, idempotency identity, or any new execution authority. Those facts are reconstructed or derived inside the store-owned authority boundary.

Candidate application identity:

```text
RecoveryApplicationKey =
H(
    schema,
    disposition_ref
)
```

Application output semantics are deliberately excluded from identity. This preserves the same deterministic-authority rule used by P3:

```text
same exact disposition identity
+ changed derived application semantics
→ semantic rebound / nondeterminism
→ fail closed
```

One durable disposition therefore produces at most one implicit application intent. Repeated recovery work must first produce new authoritative facts and a new disposition. If a future design requires explicit re-application of the same disposition, that requires a new explicit generation/authority contract; silent repeated consumption is not allowed.

### Derived application vocabulary

The first audit freezes only the responsibility meaning of the existing P3 action vocabulary:

```text
hold-unresolved
    → hold

reconcile-again
    → reconciliation-request

retry-idempotent
    → retry-request

require-manual-resolution
    → manual-resolution-handoff

accept-objective-resolution
    → objective-resolution-acceptance
```

These are orchestration responsibility semantics, not provider commands.

For provenance, P4a may reconstruct and retain the exact source `dispatch`, `Attempt`, `Step`, and `Action` identities. For `retry-idempotent`, it must also retain the source idempotency identity. Those are source/provenance facts only; none is a new execution identity.

A P4a application must not contain or mint:

```text
fresh Attempt identity
InvocationPermit
new dispatch commitment
provider selection
provider invocation
provider reconciliation call
terminal completion
governance discharge
```

## Existing execution boundary already provides the required fresh-attempt ordering

The current `RealityBoundary.execute()` path has the useful ordering P4b must reuse rather than bypass:

```text
qualification
→ governance-use
→ policy
→ authorization
→ procedure
→ reliability
→ routing
→ InvocationPermit
→ durable precommit
→ fresh StepAttempt
→ GovernanceDispatchCommitter
→ provider invocation
```

The precommit stage creates a fresh `StepAttempt` identity and increments `attempt_no`; it does not issue permits, commit governance dispatch, or invoke providers. This means P4 does not need its own Attempt allocator or execution boundary.

For an idempotent retry, the future request must preserve the source idempotency identity while still obtaining a fresh request identity, fresh Attempt identity, current qualification/admission, and a fresh dispatch commitment. The old dispatch commitment is provenance and evidence that an effect may already have occurred. It can never be revived as authority for another reality exit.

## Blocking audit finding: the original invocation specification is not durably reconstructable

P3 persists enough execution identity to classify and decide recovery, but not enough information to safely reconstruct a retry request body.

The durable `Action` and `StepAttempt` retain identities such as capability, provider, request ref, step relation and idempotency key. They do not retain the complete invocation specification required to build an equivalent fresh request, including fields such as:

```text
instruction
parameters
constraints
actor/resource binding
subject version refs
qualification/procedure refs
other request metadata required by current admission
```

`InvocationPermit` does contain an immutable `request_snapshot`, but the permit is transient. The durable `InvocationDispatchCommitted` event stores only its digest and governance/qualification digests, not that request snapshot.

Therefore this implication is currently invalid:

```text
RecoveryDisposition(retry-idempotent)
→ reconstruct exact retry request
```

No P4 implementation may fill this gap by copying a caller-owned request object, reading process memory, guessing parameters, or treating `request_ref` as if it were a durable request body.

Until an authoritative invocation-specification/replay source exists, P4b retry materialization must fail closed.

This gap does not prevent P4a from defining a durable `retry-request` application intent. It prevents that intent from becoming an executable retry.

## Reconciliation boundary

`reconcile-again` has a different meaning from retry. Reconciliation queries the external provider about the already committed dispatch; it does not create a second execution dispatch. The application fact may therefore identify the source dispatch/request/provider as the subject to reconcile, but P4a still must not call `provider.reconcile` or `RealityBoundary.reconcile` itself.

A future consumer must use the existing reality boundary for the external reconciliation call and must durably record the resulting `RecoveryObservation` before any new recovery judgment. The source dispatch remains the subject being reconciled, not renewed provider authority.

## Non-execution dispositions

The following application semantics cannot create provider work:

```text
hold
manual-resolution-handoff
objective-resolution-acceptance
```

In particular, `objective-resolution-acceptance` is not terminal completion authority. Any terminal closure still belongs to the existing terminal/verification authority chain.

## Direct-event and portability boundaries

If P4a production is later authorized, `RecoveryApplicationRecorded` must be store-owned exactly as P1/P3 authority events are store-owned. Ordinary `append_event(RecoveryApplicationRecorded)` must fail closed.

This local direct-event rule must not be interpreted as portability closure:

```text
local Memory/SQLite RecoveryApplication creation/replay
    != serialized import authority
    != bundle portability authority
```

P5 remains independent and unproven.

## Frozen P4 counterexamples

The audit suite freezes these future conditions:

```text
P4C-001  caller request carries only exact disposition_ref
P4C-002  exact disposition replays one deterministic application intent
P4C-003  same application identity cannot hide changed application semantics
P4C-004  retry intent preserves source idempotency but mints no execution authority
P4C-005  RecoveryApplication module has no reality exit or terminal authority
P4C-006  application kind is derived from durable disposition semantics
P4C-007  direct RecoveryApplicationRecorded append is denied
P4C-008  retry materialization fails closed without authoritative invocation specification
```

The audit also keeps substrate assertions that:

```text
Runtime does not consume RecoveryDisposition directly
fresh execution re-enters qualification/admission before precommit
precommit allocates a fresh Attempt
permit / dispatch / provider ownership stay separate
serialized application authority remains out of scope
```

## Decision gate after this audit

The intended audit conclusion is deliberately narrower than P4 production authorization:

```text
P3 durable RecoveryDisposition authority
= CLOSED / MERGED INTO B4 LINEAGE

P4a RecoveryApplication design
= AUDITED / COUNTEREXAMPLES FROZEN

P4a production
= NOT AUTHORIZED

P4b retry/reconciliation consumption
= NOT AUTHORIZED

P4b retry materialization substrate
= BLOCKED: authoritative invocation specification missing

P5 serialized import/bundle authority
= UNPROVEN
```

Before any P4 production slice, the review must decide whether to authorize only P4a durable intent first, and independently how the missing durable invocation specification will be established for retry consumption.
