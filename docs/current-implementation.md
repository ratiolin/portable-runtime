# Current implementation snapshot

This file is explanatory. Canonical product semantics remain owned by `contracts/`; exact executable status is defined by GitHub CI for the exact commit.

## Project boundary

Agent Kernel currently has three connected product responsibilities:

```text
cognitive control
= durable ControllerState + version-bound ControllerDecision
  + capability invocation / WorkProposal handoff / close-reopen-wait

persistent responsibility
= durable responsibility identity + current assessment/proposal/commitment state
  that can outlive a Work, Run, provider, model, process or reasoning session

durable execution
= Work / Run / Step / Attempt / recovery / effect integrity
```

None owns permanent execution authority. External effects continue to cross the existing Decision / Authorization / RealityBoundary path.

The `experiments/` package remains historical/prototyping lineage. Promoted semantics are owned by `contracts/` and canonical implementation modules, not by experiment code.

## Compatibility axes

| Axis | Current value |
| --- | --- |
| Repository/product | `agent-kernel` |
| Contract catalog | `portable-runtime-contracts-v1` |
| Python distribution | `portable-runtime` |
| Python namespace | `portable_runtime` |
| Runtime protocol | `2.0` |
| External provider protocol | `1` (`stdio-jsonl`) |
| Persistent Responsibility | `persistent-responsibility-v1` |
| Cognitive Control | `cognitive-control-v1` |
| Distinction Governance | `distinction-governance-1.0` |
| Experience Use Admission | `experience-use-admission-v1` |
| Historical Experience Use | `historical-experience-use-v1` |

The repository rename does not silently change the compatibility identifiers above.

## Canonical packaging

`contracts/` is the only canonical semantic/interoperability owner. It is packaged into installed wheels through `portable_runtime/_contracts` so interpretation does not depend on a Git checkout.

Canonical cognitive-control semantics are in:

```text
contracts/semantics/core/cognitive-control-v1.md
```

The Python reference implementation is:

```text
src/portable_runtime/controller/models.py
src/portable_runtime/controller/service.py
```

Persistent responsibility remains under:

```text
src/portable_runtime/responsibility/
```

## Cognitive control implementation

The promoted controller is deliberately small.

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
last_decision_ref
last_result_ref
```

It does not define a second Observation, Assertion, Knowledge, Outcome, provider, or authorization plane.

`ControllerDecision` supports only:

```text
invoke-capability
propose-work
close
reopen
wait
```

Every decision is bound to one exact `ControllerState.version`. A stale decision raises and does not silently become the current selection.

### Capability invocation

`invoke-capability` builds a read-class `CapabilityRequest` and calls the existing `Runtime.invoke()` path. The existing `CapabilityContractRegistry`, `ConstraintRouter`, `ProviderRegistry`, policy/authorization checks, and RealityBoundary remain authoritative.

The returned `CapabilityResult` is persisted in a `ControllerCapabilityResultObserved` Event and referenced by the next controller state. It is not automatically converted into current truth, official knowledge, Work, verified outcome, or authorization.

The controller records an intermediate waiting state before invoking the capability. If execution is interrupted at that boundary, restart preserves the pending reference; the controller does not infer permission to repeat an ambiguous operation.

### Work handoff

`propose-work` requires an existing standing responsibility and current `ResponsibilityAssessment`. It calls `ResponsibilityKernel.propose()` and therefore creates only a canonical `WorkProposal`.

It does not perform:

```text
PriorityJudgment
PortfolioAdmissionDecision
ResourceReservation
Commitment
Work materialization
Decision / Authorization
provider execution
```

Those remain downstream responsibilities.

### Close and reopen

Controller close changes only controller state. It does not complete Work or discharge a standing responsibility.

An explicit `reopen` is required before a waiting controller accepts a new selection. `reopen-required` is separately recordable with reason provenance.

## Controller persistence and restart

Controller snapshots use the existing append-only Event journal:

```text
ControllerStateRecorded
ControllerDecisionSelected
ControllerCapabilityResultObserved
ControllerWorkProposalHandedOff
ControllerReopenRequired
```

No new StateStore method or SQLite table was introduced. Reconstruction scans state events for the controller identity and loads the highest recorded version.

SQLite restart therefore preserves controller identity/state through the same durability substrate already used by the runtime.

## Runtime composition

The runtime still composes:

```text
StateStore
ArtifactStore (optional)
ProviderRegistry
CapabilityContractRegistry
ConstraintRouter
policy engine (optional)
RealityBoundary
CapabilityService
```

Cognitive control reuses this composition rather than introducing a second provider/model router.

## Durable execution

Implemented execution integrity remains unchanged:

- durable `Work`, `Run`, `Step`, and `StepAttempt` identities;
- checkpoints and compensation records;
- idempotency/effect semantics;
- lease acquire/renew/release with fencing;
- stale-step recovery inspection;
- interruption/resume/cancel operations;
- reconciliation/recovery paths that fail closed when reality is ambiguous.

Provider success remains execution evidence only. It does not automatically become objective completion.

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
    -> existing Decision / Authorization boundary
    -> RealityBoundary
    -> External Effect
    -> verification / Outcome
    -> responsibility reassessment
```

`ResponsibilityKernel` enforces current responsibility version/activity, freshness, append-only identity, resource bounds, and the proposal/admission/commitment chain. Controller integration does not weaken those checks.

## Current truth and historical state

Canonical negative invariants now include:

```text
ReasonerOutput -/-> CurrentTruth
ReasonerOutput -/-> ControllerDecision
ControllerDecision -/-> Work
ControllerDecision -/-> ActionAuthorization
ControllerClose -/-> ResponsibilityDischarge
CapabilityResult -/-> VerifiedOutcome
HistoricalControllerDecision -/-> CurrentControllerSelection
HistoricalAssessment -/-> CurrentWorkAdmission
ProviderChange -/-> ResponsibilityIdentityChange
ContextReset -/-> ResponsibilityLoss
ResponsibilityHandoff -/-> AuthorityTransfer
TaskCompleted -/-> ResponsibilityDischarged
```

## Provider and capability routing

Providers remain registered independently of workflows and cognitive control. Callers request capabilities rather than owning provider selection.

The architecture continues to separate:

```text
controller/workflow intent
!= provider selection
!= policy allow
!= execution authorization
!= external effect
```

The kernel does not add a special external-agent registry or cross-agent protocol. A compatible implementation remains an ordinary capability provider regardless of its internal product shape.

## Authorization and governance

Authorization remains separate from controller selection, model judgment, policy allow, commitment, and Work materialization.

Public views remain non-authority-bearing; internal objects such as `InvocationPermit` cannot be reconstructed or minted from a view.

## Revision, revalidation and reopen

The runtime retains provenance/history and supports typed dependency impact, explicit revalidation disposition, controller reopen state, and persistent-responsibility reopen semantics.

Controller reopen and standing-responsibility reopen are different operations and do not substitute for each other.

## Public surface

Cognitive control is canonical without a new public HTTP endpoint. HTTP exposure is a separate compatibility surface.

Existing contract/catalog and experience-use HTTP routes remain unchanged.

## Deployment/profile boundary

Downstream deployment profiles should consume Agent Kernel as their core and retain only profile-specific integrations, ingress, policy, providers, verification, notification, and deployment behavior. A profile does not own a second copy of generic runtime semantics.

## Promotion evidence

`tests/conformance/test_cognitive_control_v1.py` exercises the initial promotion boundary, including:

- reasoning result does not create Work or knowledge/current truth;
- stale controller selections fail closed;
- `propose-work` stops at `WorkProposal`;
- controller close does not discharge standing responsibility;
- waiting requires explicit reopen;
- controller state survives SQLite close/reopen.

## Current autonomy ceiling

Canonical now includes:

```text
minimal durable cognitive-control state/selection
read-class cognitive capability invocation through existing runtime
WorkProposal handoff without Work shortcut
controller close/reopen/wait coordination
trigger/event ingress
durable Work / Run execution
provider-independent capability execution
explicit RealityBoundary
authorization / policy separation
semantic/provenance history
revalidation / reopen
recovery / fencing
knowledge/experience-use governance
StandingResponsibility durability
ResponsibilityAssessment / WorkProposal / Commitment separation
resource reservation / portfolio admission primitives
provider/model/session/process continuity records
```

Not claimed by v1:

```text
continual model/policy learning
universal value or priority function
automatic permanent mission creation
self-expanding permissions
handoff-based authority transfer
self-authorizing external repair
provider-specific model routing
special cross-agent interoperability semantics
```

## Source-of-truth map

| Concern | Primary source |
| --- | --- |
| Canonical semantics | `contracts/README.md`, `contracts/catalog.toml`, `contracts/semantics/` |
| Cognitive control | `contracts/semantics/core/cognitive-control-v1.md`, `src/portable_runtime/controller/` |
| Persistent responsibility | `contracts/semantics/core/persistent-responsibility-v1.md`, `src/portable_runtime/responsibility/` |
| Runtime implementation | `src/portable_runtime/core/runtime.py` |
| Provider API/protocol | `docs/provider-api.md`, `docs/provider-protocol.md` |
| Architecture explanation | `docs/architecture.md` |
| Exact executable status | GitHub CI for the exact commit |

When prose and code disagree, explanatory prose must be synchronized to the canonical contract/implementation. Documentation cannot demote or redefine a stable canonical contract.
