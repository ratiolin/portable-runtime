# Cognitive closure — v1

Status: stable
Owner: `agent-kernel/contracts`
Contract: `cognitive-closure-v1`

This contract defines the minimum durable handoff required to pause open cognition and make a bounded direction eligible for Work proposal. It does not define a reasoning algorithm, prove that the selected direction is true, admit Work, authorize effects, verify outcomes or discharge responsibility.

## Boundary

```text
open cognition / candidates / issues / evidence
    -> CognitiveClosure
    -> WorkProposal handoff eligibility
```

Canonical separations:

```text
ReasonerOutput != CognitiveClosure
CognitiveClosure != ControllerClose
CognitiveClosure != WorkProposal
CognitiveClosure != WorkAdmission
CognitiveClosure != ActionAuthorization
CognitiveClosure != VerifiedOutcome
```

## Minimum closure content

A closure binds one exact controller state version and records at least:

- bounded controller/responsibility/subject identity;
- basis references;
- selected direction;
- selected/deferred/rejected candidate references when present;
- explicit disposition of every current open issue;
- acceptance criteria;
- verification plan;
- stop/escalation conditions;
- reopen conditions;
- requested capabilities and effect class;
- policy provenance;
- a responsibility-preserving cognitive handoff envelope.

Structural admissibility does not prove that any referenced evidence or model output is true.

## Current-state binding

A closure is valid only for the exact `ControllerState.version` it names. A stale closure cannot be silently promoted to current Work eligibility.

```text
HistoricalClosure -/-> CurrentWorkEligibility
```

A controller with an active closure may not continue ordinary exploration. It may only hand off the closure to `WorkProposal`, wait, or close the current cognitive episode. Further exploration requires an explicit reopen that clears the active closure.

## Open issues

Closure does not require pretending that all uncertainty disappeared. Every controller `open_issue_ref` must instead be explicitly represented as deferred before the closure is admitted.

```text
UnknownRecorded != UnknownResolved
DeferredUnknown != ForgottenUnknown
```

## Work handoff

`PROPOSE_WORK` must reference the active closure. The requested effect class must match the closure and requested capabilities must not exceed the closure's capability set.

The handoff still stops at canonical `WorkProposal`. Priority judgment, portfolio admission, resource reservation, commitment, Work materialization, authorization and execution remain downstream owners.

## Revalidation and reopen

A closure is temporary. Reality feedback, verification failure, scope/environment change or explicit revision may make it unsuitable for current use. Reopening cognition clears current closure eligibility without erasing closure history.

## Non-goals

This contract does not define candidate generation, search allocation, universal stopping rules, model routing, value arbitration or execution policy. Those remain replaceable policy/reasoning concerns unless a concrete runtime failure justifies a new product distinction.
