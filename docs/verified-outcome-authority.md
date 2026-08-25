# F1-B2 Verified Outcome Authority

Status: design and counterexample freeze only. Production authority is intentionally absent at this rollback point.

Baseline: `main @ d72dcc636fe2b685fe57a03ba80c9c5f81aaba0f` (F1-B1 complete).

## Scope

F1-B2 closes exactly one responsibility edge:

```text
persisted, bound verification fact
        ↓
verification authority
        ↓
authoritative Outcome
```

F1-B2 does not perform governance discharge, continued qualification, reopen, recovery reconciliation, or terminal completion.

The non-substitutability chain is frozen as:

```text
provider execution report
    != objective verification

persisted EvidenceArtifact
    != evidence for this Action

bound verification evidence
    != governance discharge

confirmed Outcome
    != terminal completion
```

## Canonical Outcome meaning

`OutcomeRecord` already supports the lifecycle states `recorded` and `confirmed`.

F1-B2 assigns them the following authority meaning:

```text
OutcomeRecord(lifecycle_status="recorded")
    = recorded / compatibility outcome fact
    != authoritative objective verification

OutcomeRecord(lifecycle_status="confirmed")
    = verification-authorized objective conclusion
```

`confirmed` means that the Outcome has valid verification provenance. It does not mean success.

The objective judgment is carried in metadata:

```text
metadata.objective_result = "pass" | "fail"
```

Therefore:

```text
Outcome absent
    = no authoritative objective conclusion

confirmed Outcome + objective_result="pass"
    = objective satisfied

confirmed Outcome + objective_result="fail"
    = objective not satisfied
```

Both explicit pass and explicit fail are authoritative conclusions when their evidence is validly bound.

The legacy/core `Outcome.status` vocabulary is not extended with `verified`, `unverified`, `reported`, or similar lifecycle values. The legacy adapter remains compatibility-only and maps legacy `Outcome` to canonical `OutcomeRecord(lifecycle_status="recorded")`.

## Authority object

The production authority is reserved as:

```text
VerifiedOutcomeAuthority
```

It is an authority boundary, not a generic projector.

Planned operation:

```text
VerifiedOutcomeAuthority(store).confirm(
    action_ref=...,
    evidence_refs=[...],
    expected_work_id=...,
    expected_run_id=...,
    expected_request_id=...,
    expected_attempt_ref=...,
    verification_scope=...,
    subject_version_refs=[...],
) -> OutcomeRecord
```

The operation must resolve durable execution state and durable typed evidence before materializing an Outcome.

## Durable Action read seam

F1-B1 persists the execution `Action` in the core action namespace. The current `StateStore` protocol exposes `save_action()` but not `get_action()`.

F1-B2 must not establish authority by scraping `export_state()` or private `_records` buckets. Production therefore needs a narrow durable Action read seam (`get_action(action_id)`) implemented consistently by Memory and SQLite stores.

This is a storage read capability only. It does not alter provider execution semantics.

`Action` does not carry `attempt_ref`. Exact attempt binding is therefore checked transitively:

```text
EvidenceArtifact.metadata.attempt_ref
        ↓
StepAttempt.id
        ↓
StepAttempt.request_ref
        ==
Action.request_ref
```

The referenced Step must belong to the same Run as the Action.

## Verification evidence contract

F1-B2 consumes only persisted canonical `EvidenceArtifact` records.

Accepted kinds are the existing typed verification kinds:

```text
closed-verification
verification-result
task-objective-proof
```

An attached `CapabilityResult.verification_result` is not an authority input. F1-B1 already freezes this distinction.

Each accepted proof must carry an explicit closed result:

```text
metadata.verification_result.result = "pass" | "fail"
```

Unknown, missing, non-dict, or other result values fail closed.

Each proof must bind at least:

```text
action_ref
request_id
attempt_ref
work_id
run_id
verification_scope
subject_version_refs
obligation_refs
verifier/provider provenance
```

F1-B2 does not require the verifier provider to differ from the executor provider. Responsibility independence is semantic: the verification role, method/provenance, and binding must be explicit and non-substitutable. Deployment topology is not frozen by provider-id inequality.

If multiple evidence refs form one verification closure, their explicit objective results must agree. Mixed pass/fail evidence does not authorize the runtime to synthesize a judgment; it fails closed unless a separate typed closure artifact explicitly resolves the conflict.

## Shared verification validator

F1-B2 must not copy the existing `CompletionAuthority.validate_proof_invariant()` implementation.

Production should extract a lower-level validator with responsibility similar to:

```text
BoundVerificationEvidenceValidator
```

The common layer validates durable typed proof and binding, while callers retain their own authority-specific policy.

Common validation responsibilities:

```text
EvidenceArtifact type and accepted kind
explicit closed verification result
Work/Run binding
Action binding
request/attempt binding
scope binding
subject/version binding
verification provenance
```

Caller-specific responsibilities remain separate:

```text
VerifiedOutcomeAuthority
    accepts explicit pass or fail
    requires exact Action/request/attempt binding
    materializes confirmed Outcome

CompletionAuthority
    requires pass
    enforces acceptance/obligation coverage
    enforces terminal proof consumption semantics
    authorizes Work/Run terminal transition
```

The extraction must preserve CompletionAuthority behavior. If current terminal fixtures do not yet carry a provenance field required by F1-B2, the common validator must support an explicit caller policy during migration rather than silently broadening or tightening terminal authority in this phase.

## Outcome materialization

A confirmed canonical Outcome uses only declared `OutcomeRecord` top-level fields:

```text
action_ref
evidence_refs
artifact_refs
lifecycle_status="confirmed"
```

Authority provenance is carried in metadata because canonical writes reject undeclared top-level fields.

Required metadata:

```text
objective_result = "pass" | "fail"
work_id
run_id
request_id
attempt_ref
verification_scope
subject_version_refs
obligation_refs
verifier_provenance
```

`artifact_refs` may include artifacts referenced by the accepted verification closure. `evidence_refs` records the exact canonical EvidenceArtifact identities consumed by the authority.

## Idempotence and identity

Confirmed Outcome identity must be deterministic from the semantic closure, including at least:

```text
action_ref
verification evidence identity
verification_scope
subject_version_refs
```

The canonicalization must be order-stable for equivalent evidence sets.

Replay of the same verification closure returns the same semantic Outcome identity and must not append duplicate authority facts.

New verification evidence is a new fact and must not be treated as replay of the old closure. Supersession/reopen semantics are deliberately deferred to F1-B3.

## Atomic authority commit

Outcome authority is one transaction:

```text
validated bound evidence
    + confirmed OutcomeRecord
    + objective-verification authority events
```

If either canonical Outcome persistence or authority-event append fails, the transaction rolls back. No half-authoritative Outcome or orphaned authority event may remain.

## Events

F1-B2 reserves two authority events:

```text
ObjectiveVerificationAccepted
OutcomeConfirmed
```

Both carry:

```text
semantic_level = "objective-verification"
authoritative_outcome = true
objective_result = "pass" | "fail"
outcome_ref
action_ref
verification_refs
```

These events are emitted only by `VerifiedOutcomeAuthority` after binding validation succeeds.

F1-B2 must not restore provider-level `OutcomeRecorded`, and must not change the execution-level meaning of `CapabilitySucceeded` / `CapabilityCompleted` established by F1-B1.

## Required conformance

The production phase must turn the following frozen counterexamples green:

```text
FB2-001 bound persisted pass proof
        -> exactly one confirmed Outcome(objective_result=pass)

FB2-002 bound persisted fail proof
        -> exactly one confirmed Outcome(objective_result=fail)

FB2-003 provider-attached CapabilityResult.verification_result=pass
        -> no Outcome authority

FB2-004 wrong action/request/work/run binding
        -> fail closed

FB2-005 wrong scope/version anchor
        -> fail closed

FB2-006 missing/non-typed/unknown proof ref
        -> fail closed

FB2-007 same verification closure replay
        -> idempotent Outcome identity

FB2-008 proof from another Action/Run
        -> cannot be reused

FB2-009 Outcome + authority-event persistence failure
        -> atomic rollback

FB2-010 legacy/core Outcome or canonical OutcomeRecord(recorded)
        -> not confirmed authority

FB2-011 confirmed Outcome alone
        -> no governance discharge

FB2-012 confirmed Outcome alone
        -> no terminal completion; CompletionAuthority remains independent
```

## Explicit non-goals

F1-B2 does not implement:

```text
continued qualification
ReviewObligation opening or discharge
reopen/supersession
provider reconciliation
recovery closure
Work/Run terminal transition
principal identity redesign
provider protocol changes
transport fencing changes
```

The next phase after F1-B2 is intentionally a separate rollback point.