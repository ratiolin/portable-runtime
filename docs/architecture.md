# Architecture

Agent Kernel is a provider-neutral kernel for durable cognitive control, persistent responsibility, and governed Work/Run execution. Canonical product semantics remain owned by `contracts/`; this document is explanatory and cannot redefine those contracts.

## 1. Canonical ownership

```text
contracts semantic contracts
> structural schemas
> canonicalization rules
> conformance vectors
> Python reference implementation
> HTTP adapters
> TypeScript consumers
> inspection surfaces
```

External framework/research material may motivate a change but is not a runtime input unless a distinction is explicitly promoted into `contracts/`.

## 2. Product layering

```text
EXISTING CONTEXT / RECORDS / RESPONSIBILITY STATE
        |
        v
CANONICAL COGNITIVE CONTROL
ControllerState -> ControllerPolicy -> ControllerDecision
        |
        +-> invoke-capability -> Runtime / Capability / Provider -> result/event
        |
        +-> form-closure -> CognitiveClosure
        |                       |
        |                       v
        +----------------> propose-work -> WorkProposal only
        |
        +-> assess-revision -> RevisionAssessment
        |
        +-> close / reopen / wait
        |
        v
CANONICAL PERSISTENT RESPONSIBILITY
StandingResponsibility
  -> Observation / Evidence
  -> ResponsibilityAssessment
  -> WorkProposal
  -> PriorityJudgment
  -> PortfolioAdmissionDecision
  -> ResourceReservation
  -> Commitment
        |
        v
CANONICAL DURABLE EXECUTION
Work / Run / Step / StepAttempt
        |
        v
Capability Contract + Constraint Router + Authorization / Policy
        |
        v
RealityBoundary
        |
        v
Provider / external effect
        |
        v
Observation / Evidence -> verification -> Outcome
        |
        v
RevisionAssessment -> later retry / revise / reopen / reconcile / wait / close
```

Cognitive control is not a second evidence store, provider router, authorization system, or workflow engine.

## 3. Cognitive-control v2

Canonical decisions:

```text
invoke-capability
form-closure
propose-work
assess-revision
close
reopen
wait
```

Key separations:

```text
ReasonerOutput != ControllerDecision
ReasonerOutput != CognitiveClosure
CognitiveClosure != WorkProposal
ControllerDecision != WorkAdmission
ControllerDecision != ActionAuthorization
FailureObserved != RetryPermission
RevisionAssessment != RetryRun
RevisionAssessment != Reopen
ControllerClose != ResponsibilityDischarge
CapabilityResult != VerifiedOutcome
```

Every `ControllerDecision` binds one exact `ControllerState.version`. Stale selections fail closed.

### Open cognition

An OPEN controller without an active closure may invoke read-class cognition/observation capabilities, form a closure, wait, or close.

### Cognitive closure

`CognitiveClosure` records a temporary stopping point for one bounded scope. It carries basis references, selected direction, candidate/issue disposition, acceptance criteria, verification plan, stop/reopen conditions, requested capabilities, effect class, policy provenance, and a cognitive handoff envelope.

An active closure blocks ordinary exploration. Further cognition requires explicit reopen. A closure cannot create Work or authority.

### Work handoff

`propose-work` requires the current active closure and calls `ResponsibilityKernel.propose()`. It creates only a canonical `WorkProposal`, then moves the controller to WAITING. Priority judgment, portfolio admission, reservation, commitment, Work materialization, authorization, and execution remain downstream.

### Revision and reopen

After reality returns Outcome/verification evidence, `RevisionAssessment` identifies a bounded revision scope and recommends one of:

```text
retry-run
revise-work
reopen-cognition
acquire-evidence
request-authorization
reconcile-effect
wait
close
```

The recommendation is not self-executing. Deep revision cannot silently retry. Recommendations that invalidate current closure move the controller to `reopen-required`; an explicit later `reopen` returns OPEN and clears current closure/WorkProposal eligibility without erasing history.

## 4. Responsibility identity and continuity

A `StandingResponsibility` is durable identity plus bounded statement/scope. It is not a task, provider/model/session identity, or authority grant.

```text
StandingResponsibility
!= Work / Run
!= provider / model / reasoning session
!= PermanentAuthority
```

Provider/model/session/process changes do not change responsibility identity, and handoff never transfers authority by itself.

## 5. Current truth versus history

```text
HistoricalAssessment -/-> CurrentWorkAdmission
HistoricalControllerDecision -/-> CurrentControllerSelection
HistoricalClosure -/-> CurrentWorkEligibility
HistoricalRevision -/-> CurrentDisposition
NoObservedFailure -/-> ConditionVerifiedHealthy
```

History is retained while current eligibility is recomputed from current state/version and downstream freshness rules.

## 6. Work admission

Persistent responsibility may materialize Work only through:

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

Controller selection and cognitive closure cannot skip this chain.

## 7. Authorization and RealityBoundary

```text
ReasonerOutput
!= CognitiveClosure
!= ControllerDecision
!= assessment / proposal / priority / commitment
!= Decision
!= AuthorizationGrant / AuthorizationUse
!= InvocationPermit
!= provider execution
!= verified Outcome
```

The RealityBoundary remains the runtime control point before provider/external effects. Provider replacement, restart, import, responsibility handoff, closure, revision, close, or reopen cannot mint authority.

## 8. Durable execution

The execution layer remains `Work`, `Run`, `Step`, `StepAttempt`, checkpoints, compensation, leases/fencing, CAS, interruption/resume/cancel, idempotency, and explicit reconciliation.

Ambiguous external failure is not permission to repeat a side effect.

## 9. Capability/provider boundary

Callers request capabilities rather than concrete providers. The kernel does not need a special concept for a particular model or external agent product.

```text
controller/workflow intent
!= provider selection
!= policy allow
!= execution authorization
!= external effect
```

Model identity grants no semantic role or authority.

## 10. Semantic record plane

Record type, epistemic status, and lifecycle remain orthogonal. Provenance is retained and `produces` is not silently promoted into `causes`.

Reasoner results, closure events, and revision events are coordination/provenance facts; none automatically become current truth, official knowledge, Work, verified outcome, or authorization.

## 11. Legacy reopen boundary

`records/reopen.py` remains only for historical/observation compatibility. `create_reopen_work()` is retired and fails loudly.

New Work after cognitive failure must follow:

```text
RevisionAssessment
-> explicit controller reopen
-> new CognitiveClosure
-> WorkProposal
-> normal admission
```

## 12. Stores and portability

Controller snapshots, closures, revisions, and responsibility objects use the existing append-only Event/StateStore/SQLite/export/import substrate. Import preserves history but mints no controller decision, Work, authorization, invocation permit, or external effect.

## 13. Deployment/profile boundary

Agent Kernel owns generic semantics and implementation. Downstream profiles retain only environment-specific ingress, integrations, providers, policy, verification, notification, and deployment behavior. A profile is not a second runtime semantic owner.

## 14. Trigger boundary

```text
Trigger != Observation proof
Observation != ResponsibilityAssessment
ResponsibilityAssessment != Work
```

Wakeups are ingress, not admission or authority.

## 15. Non-goals

Agent Kernel does not define candidate-generation theory, universal search allocation, a universal closure policy, a universal revision-depth policy, continual learning, universal value/priority arbitration, self-expanding permissions, provider-specific model routing, or special cross-agent interoperability semantics.

Additional cognitive concepts are promoted only after a concrete runtime failure demonstrates that the current minimal contract cannot preserve a necessary distinction.

## 16. Source-of-truth map

| Concern | Primary source |
|---|---|
| Canonical semantic ownership | `contracts/README.md`, `contracts/catalog.toml`, `contracts/semantics/` |
| Cognitive control | `contracts/semantics/core/cognitive-control-v2.md`, `src/portable_runtime/controller/` |
| Cognitive closure | `contracts/semantics/core/cognitive-closure-v1.md` |
| Revision control | `contracts/semantics/core/revision-control-v1.md` |
| Persistent responsibility | `contracts/semantics/core/persistent-responsibility-v1.md`, `src/portable_runtime/responsibility/` |
| Runtime composition | `src/portable_runtime/core/runtime.py` |
| Exact executable status | GitHub CI for the exact commit |
