# Persistent responsibility experiment — historical precursor

Status: **historical precursor / non-authority-bearing experiment**.

This document originally captured the falsifiable Stage-4 candidate that preceded `persistent-responsibility-v1`.

The promotion decision has now happened: the responsibility positions that survived independent-domain falsification are owned canonically by:

```text
contracts/semantics/core/persistent-responsibility-v1.md
contracts/schemas/responsibility/persistent-responsibility-v1.schema.json
src/portable_runtime/responsibility/
```

Therefore this experiment is **not** the current product-status or semantic authority for promoted concepts such as `StandingResponsibility`, `ResponsibilityAssessment`, `WorkProposal`, resource reservation/commitment separation, process/provider/model/session continuity, or the negative invariants cataloged by `persistent-responsibility-v1`.

The promoted contract includes, among others:

```text
HistoricalAssessment -/-> CurrentWorkAdmission
Commitment -/-> ExecutionAuthorization
ProviderChange -/-> ResponsibilityIdentityChange
ContextReset -/-> ResponsibilityLoss
ResponsibilityHandoff -/-> AuthorityTransfer
NoObservedFailure -/-> ConditionVerifiedHealthy
TaskCompleted -/-> ResponsibilityDischarged
StandingResponsibility -/-> PermanentAuthority
```

## What remains useful here

The old experiment remains useful as lineage for how the promoted contract was discovered and as a place to explore concepts that are **not** part of v1, for example broader supervisor/autonomy/arbitration policies.

Those experiment-only ideas must not be inferred into the stable contract. Any future promotion requires a new explicit versioned contract change driven by real failure/user need and independent-domain evidence.

## Historical hypothesis

The original hypothesis was that durable Work/Run orchestration is insufficient when a system must remain responsible for a condition over time. The candidate flow was:

```text
StandingResponsibility
  -> Observation / ExpectedSignal
  -> SituationAssessment
  -> WorkProposal
  -> PriorityJudgment
  -> Commitment + ResourceEnvelope
  -> Work / Run / Effect / Verification
  -> Responsibility reassessment
```

That hypothesis was later refined and promoted into the canonical v1 vocabulary. In the canonical contract, `SituationAssessment` became `ResponsibilityAssessment`, portfolio/resource admission became explicit typed positions, and continuity across provider/model/session/process changes became explicit durable state.

## Promotion evidence now available

Two independent downstream domains now exercise the promoted semantics:

- Commerce listing integrity: durable SQLite responsibility restart while PostgreSQL/DBOS remain the business/effect truth owners; responsibility continuity does not mint `AuthorizationGrant`.
- Control-plane deployment health: SQLite restart plus provider/model/session replacement, followed by fresh Prometheus current-truth re-evaluation that supersedes a still-fresh historical diagnostic proposal without deleting history or creating Work/authority.

These downstream results are evidence for the stable contract. They do not make this historical experiment a normative dependency.

## Authority ceiling remains unchanged

Promotion of persistent responsibility did **not** promote permanent authority or unrestricted autonomy:

```text
StandingResponsibility != PermanentAuthority
WorkProposal != Commitment
Commitment != ExecutionAuthorization
ResponsibilityHandoff != AuthorityTransfer
```

External effects still require the existing current Decision/Authorization/RealityBoundary path and fresh verification afterwards.

## Still non-goals for v1

```text
continual model/policy learning
universal value/priority function
automatic permanent mission creation
self-expanding permissions
self-authorizing external repair
canonical universal cross-mission arbitration
```

For current product status, use [`../../README.md`](../../README.md), [`../current-implementation.md`](../current-implementation.md), [`../architecture.md`](../architecture.md), and the canonical contract itself.
