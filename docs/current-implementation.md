# Current implementation snapshot

This file is explanatory. Canonical product semantics remain owned by `contracts/`; exact executable status is defined by GitHub CI for the exact commit.

## Project boundary

Agent Kernel currently has three connected product responsibilities:

```text
cognitive control
= durable ControllerState + version-bound ControllerDecision
  + capability invocation
  + CognitiveClosure / WorkProposal handoff
  + RevisionAssessment / close-reopen-wait coordination

persistent responsibility
= durable responsibility identity + current assessment/proposal/commitment state
  that can outlive Work, Run, provider, model, process or reasoning session

durable execution
= Work / Run / Step / Attempt / recovery / effect integrity
```

None owns permanent execution authority. External effects continue to cross the existing Decision / Authorization / RealityBoundary path.

## Compatibility axes

| Axis | Current value |
|---|---|
| Repository/product | `agent-kernel` |
| Contract catalog | `portable-runtime-contracts-v1` |
| Python distribution | `portable-runtime` |
| Python namespace | `portable_runtime` |
| Runtime protocol | `2.0` |
| External provider protocol | `1` (`stdio-jsonl`) |
| Persistent Responsibility | `persistent-responsibility-v1` |
| Cognitive Control | `cognitive-control-v2` |
| Cognitive Closure | `cognitive-closure-v1` |
| Revision Control | `revision-control-v1` |
| Distinction Governance | `distinction-governance-1.0` |

## Canonical packaging

`contracts/` is the only canonical semantic/interoperability owner and is packaged into installed wheels. Current cognitive semantics are:

```text
contracts/semantics/core/cognitive-control-v2.md
contracts/semantics/core/cognitive-closure-v1.md
contracts/semantics/core/revision-control-v1.md
```

Reference implementation:

```text
src/portable_runtime/controller/models.py
src/portable_runtime/controller/service.py
src/portable_runtime/controller/closure.py
src/portable_runtime/controller/revision.py
src/portable_runtime/controller/handoff.py
```

## Cognitive-control implementation

`ControllerState` contains:

```text
identity
optional responsibility_ref / subject_ref
context_refs
candidate_refs
open_issue_refs
status: open | waiting | closed | reopen-required
monotonic version
pending_ref
active_closure_ref
work_proposal_ref
last_revision_ref
last_decision_ref
last_result_ref
```

It does not define a second Observation, Assertion, Knowledge, Outcome, provider, or authorization plane.

`ControllerDecision` supports:

```text
invoke-capability
form-closure
propose-work
assess-revision
close
reopen
wait
```

Every decision is bound to one exact state version. Stale decisions fail closed.

### Capability invocation

`invoke-capability` builds a read-class `CapabilityRequest` and calls the existing runtime path. The result is persisted as controller evidence/provenance and is not automatically converted into truth, knowledge, closure, Work, verified outcome, or authorization.

### Cognitive closure

`form-closure` records a `CognitiveClosure` bound to the exact controller state. Structural validation requires a basis, selected direction, acceptance criteria, verification plan, reopen conditions, and explicit deferral of every current open issue.

After a closure is active, ordinary exploration is rejected. The controller may only propose Work from the closure, wait, or close until an explicit reopen clears current closure eligibility.

### Work handoff

`propose-work` requires the active closure. Requested capabilities must remain within the closure and the effect class must match. It calls `ResponsibilityKernel.propose()` and creates only `WorkProposal`, then moves the controller to WAITING.

It does not perform priority judgment, portfolio admission, resource reservation, commitment, Work materialization, Decision/Authorization, or provider execution.

### Revision

`assess-revision` records a `RevisionAssessment` grounded in the active closure, Work identity, and Outcome or verification references. The assessment distinguishes retry, Work revision, cognitive reopen, evidence acquisition, authorization, reconciliation, wait, and verified close.

The assessment is not self-executing. Recommendations that invalidate the closure move to `reopen-required`; explicit `reopen` returns OPEN and clears current closure/WorkProposal eligibility while preserving history.

### Close and responsibility

Controller close ends only the current cognitive episode. It does not complete Work or discharge standing responsibility.

## Controller persistence and restart

Controller/closure/revision history uses the existing append-only Event journal:

```text
ControllerStateRecorded
ControllerDecisionSelected
ControllerCapabilityResultObserved
ControllerCognitiveClosureFormed
ControllerWorkProposalHandedOff
ControllerRevisionAssessed
ControllerReopenRequired
```

No controller-specific database table is required. SQLite restart reconstructs current state from durable events.

## Durable execution

Existing execution integrity remains:

- durable `Work`, `Run`, `Step`, and `StepAttempt` identities;
- checkpoints and compensation records;
- idempotency/effect semantics;
- lease acquire/renew/release with fencing;
- stale-step recovery inspection;
- interruption/resume/cancel operations;
- reconciliation/recovery paths that fail closed when reality is ambiguous.

Provider success remains execution evidence only. It does not automatically become objective completion, and failure does not automatically permit retry.

## Persistent responsibility

The canonical responsibility chain remains:

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
    -> Decision / Authorization
    -> RealityBoundary
    -> External Effect
    -> verification / Outcome
    -> responsibility reassessment
```

Controller integration does not weaken those checks.

## Current truth and historical state

Canonical negative invariants include:

```text
ReasonerOutput -/-> CurrentTruth
ReasonerOutput -/-> ControllerDecision
ReasonerOutput -/-> CognitiveClosure
CognitiveClosure -/-> Work
CognitiveClosure -/-> ActionAuthorization
ControllerDecision -/-> Work
ControllerDecision -/-> ActionAuthorization
CapabilityResult -/-> VerifiedOutcome
FailureObserved -/-> RetryRun
RevisionAssessment -/-> RetryRun
RevisionAssessment -/-> Reopen
HistoricalClosure -/-> CurrentWorkEligibility
HistoricalAssessment -/-> CurrentWorkAdmission
ProviderChange -/-> ResponsibilityIdentityChange
ContextReset -/-> ResponsibilityLoss
ResponsibilityHandoff -/-> AuthorityTransfer
ControllerClose -/-> ResponsibilityDischarge
TaskCompleted -/-> ResponsibilityDischarged
```

## Legacy reopen migration

`src/portable_runtime/records/reopen.py` remains readable for historical/observation compatibility. `create_reopen_work()` is retained only as a fail-loud compatibility symbol and cannot mint Work.

New Work after cognitive failure must pass through:

```text
RevisionAssessment
-> explicit controller reopen
-> CognitiveClosure
-> WorkProposal
-> normal admission
```

## Provider and model neutrality

Providers remain registered independently of workflows and cognitive control. Callers request capabilities rather than model identities. A provider may be a model, program, service, human-mediated system or another agent product.

Model identity does not grant capability or authority, and no model-tier semantics are part of the kernel.

## Authorization and governance

Authorization remains separate from closure, revision, controller selection, model judgment, policy allow, commitment, and Work materialization. Public views remain non-authority-bearing.

## Current autonomy ceiling

Canonical now includes:

```text
minimal durable cognitive-control state/selection
read-class cognitive capability invocation
explicit temporary CognitiveClosure
WorkProposal handoff without Work shortcut
reality-grounded RevisionAssessment
explicit close/reopen/wait coordination
durable Work / Run execution
provider-independent capability execution
explicit RealityBoundary
authorization / policy separation
semantic/provenance history
revalidation / recovery / reconciliation
StandingResponsibility durability
resource reservation / portfolio admission primitives
provider/model/session/process continuity records
```

Not claimed:

```text
candidate-generation theory
universal search-allocation or closure policy
universal revision-depth policy
continual model/policy learning
universal value or priority function
automatic permanent mission creation
self-expanding permissions
self-authorizing external repair
provider-specific model routing
special cross-agent interoperability semantics
```

## Source-of-truth map

| Concern | Primary source |
|---|---|
| Canonical semantics | `contracts/README.md`, `contracts/catalog.toml`, `contracts/semantics/` |
| Cognitive control | `contracts/semantics/core/cognitive-control-v2.md`, `src/portable_runtime/controller/` |
| Cognitive closure | `contracts/semantics/core/cognitive-closure-v1.md` |
| Revision control | `contracts/semantics/core/revision-control-v1.md` |
| Persistent responsibility | `contracts/semantics/core/persistent-responsibility-v1.md`, `src/portable_runtime/responsibility/` |
| Runtime implementation | `src/portable_runtime/core/runtime.py` |
| Exact executable status | GitHub CI for the exact commit |
