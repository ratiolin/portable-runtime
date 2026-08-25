# F1-B1 — Execution Report / Outcome Separation

Status: F1-B1 only. F1-B2, F1-B3, and F1-B4 are explicitly out of scope.

Baseline: F0 is complete at `83c358bef505a4ba29b156734222c3c90f98eb29`. Phase E dispatch semantics remain frozen at `2f47395a41e4e508eca5ad5af167f10bf5442fd3`.

## Responsibility boundary

F1-B1 removes one semantic shortcut:

```text
provider report
    !=
authoritative objective Outcome
```

The frozen rule is:

```text
CapabilityResult.status == "succeeded"
    => provider/execution report succeeded

CapabilityResult.status == "succeeded"
    !=> objective effect verified
    !=> authoritative successful Outcome
    !=> governance responsibility discharged
    !=> Work/Run terminal completion authorized
```

This distinction applies equally to governed and non-governed execution.

## Existing responsibility objects

F1-B1 does not introduce a new execution receipt model.

```text
Step / StepAttempt / Action
    = durable execution facts

EvidenceArtifact / ClosedVerificationResult
    = verification facts

Outcome
    = authoritative effect/outcome fact
```

`CapabilityResult.verification_result` remains a distinct provider result field. Its presence does not make `commit_execution_projection()` a verification authority. Even `verification_result.result == "pass"` does not cause F1-B1 to materialize an `Outcome`; binding and authoritative verification closure belong to F1-B2.

## Production projection rule

`commit_execution_projection()` is execution projection only. It may durably update:

- `Step`;
- `StepAttempt`;
- `Action`.

It MUST NOT create an `Outcome` from `CapabilityResult.status`, regardless of whether the reported status is `succeeded`, `failed`, `cancelled`, or `unknown`, and regardless of whether a `ClosedVerificationResult` is attached.

The execution projection transaction remains atomic. If durable projection fails after provider execution, the existing fail-closed recovery path remains authoritative: the boundary may return `unknown` / `ResultCommitFailed`, and a partially projected execution prefix must not remain committed.

## Event semantics

The strict RealityBoundary emits execution-level facts after durable execution projection:

```text
InvocationCompleted
ExecutionSucceeded | ExecutionCompleted
```

These events describe provider/runtime execution only.

`CapabilitySucceeded` and `CapabilityCompleted` are retained as compatibility events. Their payload is explicitly marked:

```text
semantic_level = "execution"
authoritative_outcome = false
compatibility_event = true
```

Therefore `CapabilitySucceeded` MUST NOT be interpreted as:

- `OutcomeVerified`;
- `ObjectiveSatisfied`;
- governance review discharge;
- terminal completion authority.

`OutcomeRecorded` is not emitted by the F1-B1 execution projection because `projection.outcome_id` is `None`. A later verification authority may materialize an Outcome, but that responsibility belongs to F1-B2 and must not be folded back into provider execution projection.

## CompletionAuthority

F1-B1 does not modify `CompletionAuthority`.

Terminal completion remains fail-closed and requires its existing bound typed verification evidence. Provider status, provider metadata, execution-level events, and an attached unbound `ClosedVerificationResult` do not constitute completion proof.

This invariant is a non-regression anchor:

```text
provider success alone
    !=> CompletionAuthority authorization
```

## No governance shortcut

F1-B1 does not discharge, close, reopen, or create governance responsibility.

In particular:

```text
verification_result == pass
    !=> automatic ReviewObligation discharge
```

Objective verification and governance review-discharge remain independent responsibilities.

## F1-B1 conformance

The required conformance set is:

```text
FB1-001 provider succeeded + no verification
        -> execution may succeed; no authoritative Outcome

FB1-002 provider succeeded + verification fail
        -> execution succeeded; no successful objective Outcome

FB1-003 provider succeeded + verification pass
        -> execution projection still does not become Outcome authority

FB1-004 provider failed
        -> no successful objective Outcome

FB1-005 provider unknown
        -> no successful objective Outcome

FB1-006 execution projection persistence failure
        -> atomic rollback / existing unknown-recovery semantics preserved

FB1-007 non-governed execution
        -> same execution/verification separation

FB1-008 CompletionAuthority
        -> provider success alone remains insufficient
```

The pre-fix counterexample was demonstrated on both Memory and SQLite: full pytest produced 11 failures in the new F1-B1 suite because execution projection immediately created `Outcome` records from provider status.

## Exit and next phase

F1-B1 is complete when:

1. provider execution projection creates no authoritative `Outcome`;
2. execution facts remain durable and atomic;
3. execution-level event semantics are explicit;
4. `CapabilitySucceeded` is compatibility-only at execution level;
5. FB1-001 through FB1-008 are required strict conformance;
6. existing `CompletionAuthority` fail-closed semantics remain unchanged;
7. full test suite and strict conformance are green.

Only after this boundary is merged should F1-B2 define:

```text
objective verification
    -> bound authoritative judgment
    -> authoritative Outcome
```

F1-B1 does not define continued qualification, reopen, recovery closure, transport fencing, or terminal integration.