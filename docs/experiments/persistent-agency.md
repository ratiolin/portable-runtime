# Persistent responsibility experiment

Status: **experimental / non-canonical / non-authority-bearing**.

This experiment asks what must exist *above* durable Work/Run orchestration when a system is expected to remain responsible for a condition over time. It intentionally does not add new public contracts to `src/portable_runtime` or the canonical contract catalog.

## Hypothesis

Stage-4 persistent agency requires a durable responsibility owner that outlives any single Work. The candidate flow is:

```text
StandingResponsibility
  -> Observation / ExpectedSignal
  -> SituationAssessment
  -> WorkProposal
  -> PriorityJudgment
  -> Commitment + ResourceEnvelope
  -> Work / Run / Effect / Verification
  -> Responsibility reassessment
  -> wait / reopen / propose again
```

A Trigger may wake the system, but a trigger does not itself justify Work. A model may propose Work, but proposal does not itself commit resources or mint authority. A completed Work does not discharge a standing responsibility.

## Candidate non-equivalences

These are deliberately **not** canonical. They should be promoted only if independent domains produce counterexamples that require them.

- `Observation != SituationAssessment`
- `SituationAssessment != WorkProposal`
- `WorkProposal != Commitment`
- `Commitment != ExecutionAuthorization`
- `PriorityJudgment != ValueTruth`
- `ResourceAllocation != ExternalEffectAuthority`
- `TaskCompleted != StandingResponsibilityDischarged`
- `StandingResponsibility != PermanentAuthority`
- `RoleDelegation != SubdelegationRight`
- `NoObservedFailure != ConditionVerifiedHealthy`

## Why Commitment exists

A proposal can be sensible while still not deserving resources *now*. Commitment is the explicit boundary where a system accepts a bounded resource allocation, stop conditions, and escalation conditions. It remains non-authority-bearing: external effect authority must still come from the existing authorization path.

## Why priority is multidimensional

The experiment stores urgency, impact, risk, reversibility, confidence, resource cost, and human-attention cost as separate dimensions. It intentionally avoids a universal scalar `priority_score` that would pretend a policy judgment is objective value truth.

## Missing events

Persistent responsibility cannot depend only on positive events. `ExpectedSignal` allows elapsed time plus missing evidence to produce a `SituationAssessment`. Absence becomes actionable only relative to an explicit expectation; `no error observed` is not equivalent to verified health.

## Escalation

The experiment treats autonomy and authority as independent. Read-only, reversible diagnosis may remain autonomous. Financial or irreversible external effects can route to human review without reducing the system's ability to notice, diagnose, propose, or prepare work.

## Promotion rule

Do not move these types into the canonical runtime merely because the experiment is convenient. Promotion requires repeated domain evidence that collapsing the candidate responsibility position causes a real shortcut, ambiguity, or unsafe state.

The first reference-domain falsification target is `commerce-orchestrator`'s Listing Integrity Steward: a standing responsibility remains active after each listing-diagnosis Work completes, while external publication changes continue to use Commerce-owned Decision -> ExecutionAuthorization -> Effect -> Reality -> ConfirmedOutcome semantics.
