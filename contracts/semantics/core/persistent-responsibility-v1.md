# Persistent responsibility — v1

Status: stable
Owner: `portable-runtime/contracts`
Contract: `persistent-responsibility-v1`

This contract defines durable coordination semantics for responsibilities that
outlive any single Work, Run, provider, model, process or reasoning session.
It is a downstream portable product contract. Upstream research/framework
sources may motivate or evidence the distinctions, but runtime meaning is
owned here and changes only through an explicit versioned contract update.

## Product boundary

```text
StandingResponsibility
    -> Observation / Evidence
    -> ResponsibilityAssessment
    -> WorkProposal
    -> PriorityJudgment
    -> PortfolioAdmissionDecision
    -> ResourceReservation
    -> Commitment
    -> Work
    -> existing Decision / Authorization boundary
    -> RealityBoundary
    -> External Effect
    -> verification / Outcome
    -> responsibility reassessment
```

No arrow authorizes skipping an intermediate responsibility object.

`StandingResponsibility` is durable identity plus bounded statement/scope. Its
current lifecycle is derived from explicit admission/lifecycle-transition
history. It contains no provider/model/session identity and no execution
authority.

The durable implementation may store responsibility objects in the runtime
event journal. Storage representation does not make Event the semantic owner;
the typed objects and this contract own product meaning.

## Canonical negative invariants

| ID | Contract |
| --- | --- |
| PR-001 | `TaskCompleted -/-> ResponsibilityDischarged`. |
| PR-002 | `StandingResponsibility -/-> PermanentAuthority`. |
| PR-003 | `Trigger -/-> Work`. |
| PR-004 | `Observation -/-> Work`. |
| PR-005 | `ResponsibilityAssessment -/-> Commitment`. |
| PR-006 | `WorkProposal -/-> Commitment`. |
| PR-007 | `Commitment -/-> ExecutionAuthorization`. |
| PR-008 | `ResourceReservation -/-> EffectAuthority`. |
| PR-009 | `HistoricalAssessment -/-> CurrentWorkAdmission`. |
| PR-010 | Responsibility scope/version change makes prior proposal/assessment current-use eligibility stale until revalidated. |
| PR-011 | Replay of the same logical wakeup must not duplicate its logical missing-signal assessment or Work materialization. |
| PR-012 | `ProviderChange -/-> ResponsibilityIdentityChange`. |
| PR-013 | `ContextReset -/-> ResponsibilityLoss`. |
| PR-014 | `ResponsibilityHandoff -/-> AuthorityTransfer`. |
| PR-015 | `BundleImport -/-> AuthorityGrant`. |
| PR-016 | `PortfolioAdmissionDecision -/-> EffectAuthorization`. |
| PR-017 | `SchedulingPreemption -/-> UndoExternalEffect`. |
| PR-018 | `NoObservedFailure -/-> ConditionVerifiedHealthy`. |
| PR-019 | `ResponsibilityDischargeDecision -/-> LifecycleMutation`; a separate applied transition records the lifecycle fact. |
| PR-020 | Completion/discharge of one responsibility does not discharge another responsibility. |

## Lifecycle

The lifecycle vocabulary is deliberately small:

```text
active
suspended
discharged
```

Admission establishes the initial active state. A later change is represented
by an append-only `ResponsibilityLifecycleTransition`.

Discharge and reopen require an explicit decision reference. Work completion,
provider success, absence of recent failures, model output, UI state and
historical success are insufficient.

## Durable expectations and wakeups

A `ResponsibilityExpectation` records what signal is expected, from which
subject, and by when. Scheduler delivery is not itself an observation or an
assessment:

```text
Wakeup != Observation
Trigger != ResponsibilityAssessment
ResponsibilityAssessment != Work
```

The same logical due expectation is replay-safe. If a due expectation has no
qualifying evidence, the runtime may create one deterministic missing-signal
assessment. It still cannot create Work without the proposal/admission chain.

## Work admission

A persistent responsibility may materialize a bounded Work only through:

```text
active responsibility
+ current responsibility version
+ current assessment
+ WorkProposal
+ admitted PriorityJudgment
+ admitted PortfolioAdmissionDecision
+ current ResourceReservation
+ Commitment
-> Work
```

Work carries provenance back to responsibility/proposal/commitment/reservation.
For external effects it also carries the explicit marker that effect authority
is required separately. Materialization never mints an `AuthorizationGrant`.

## Resource arbitration

Resource dimensions are non-negative and independently inspectable:

```text
compute
API calls
money
human attention
concurrency slots
domain-specific quota
```

A versioned portfolio policy is referenced explicitly. The product contract
does not define one universal weighted priority score. Reservation must fail
closed on overcommit. Release, expiry and preemption are explicit historical
facts; preemption changes scheduling/resource ownership only.

## Continuity

Reasoning providers are temporary workers, not responsibility owners.
`ReasoningSessionBinding`, `ResponsibilityContextSnapshot`,
`ResponsibilityHandoff` and `ContinuityValidation` preserve structured durable
state across model/provider/session/process changes.

A handoff rechecks at least responsibility activity, scope/version,
assessment freshness, expectations, proposals and reservations. It always
requires execution-authorization revalidation before a later external effect;
handoff itself transfers no authority.

## Portability and authority ceiling

Responsibility objects use existing StateStore/Event/SQLite/export/import/bundle
durability. Import preserves identity and history.

```text
imported responsibility history
-/-> AuthorizationGrant
-/-> InvocationPermit
-/-> external effect
```

Authorization remains owned by the existing portable authorization contract and
RealityBoundary path.

## Promotion evidence

The contract is promoted only with independent-domain counterexamples showing
that collapsing adjacent responsibility positions creates materially wrong
behavior. The initial conformance baseline uses:

- Commerce listing-integrity responsibility;
- software/service-operations deployment-health responsibility.

Both domains preserve at least:

```text
Assessment != Proposal
Proposal != Commitment
Task completion != Responsibility discharge
```

## Non-goals

This contract does not define continual learning, model training, a universal
value function, automatic permanent mission creation, self-expanding
permissions, a second authorization framework or a second workflow engine.
