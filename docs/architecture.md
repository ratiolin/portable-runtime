# Architecture

Agent Kernel is a provider-neutral kernel for durable cognitive control, persistent responsibility, and governed Work/Run execution. Canonical product semantics remain owned by `contracts/`; this document is explanatory and cannot redefine those contracts.

## 1. Canonical ownership

The semantic precedence is:

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

`contracts/catalog.toml` is the machine-readable contract index. External research/framework documents, experiments, and historical commits may motivate a product change but are not runtime inputs unless a distinction is explicitly promoted into `contracts/`.

The repository/product owner is now `agent-kernel`. Existing `portable-runtime-*` identifiers and the `portable_runtime` Python namespace remain compatibility axes until a separately justified migration changes them.

## 2. Product layering

The current architecture is:

```text
EXISTING CONTEXT / RECORDS / RESPONSIBILITY STATE
        |
        v
CANONICAL COGNITIVE CONTROL
ControllerState -> ControllerDecision
        |              |
        |              +-> invoke-capability
        |              |      |
        |              |      v
        |              |  existing Runtime / Capability / Provider path
        |              |      |
        |              |<----- result/event
        |              |
        |              +-> propose-work -> canonical WorkProposal only
        |              +-> close / reopen / wait
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
        | bounded Work admission; no effect authority shortcut
        v
CANONICAL DURABLE EXECUTION
Work / Run / Step / StepAttempt
        |
        v
Semantic Records + Procedure
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
Observation / Evidence
        |
        v
verification -> reassessment / revalidation / recovery / reopen
```

Controller, responsibility, and execution reuse the existing StateStore/Event durability substrate. Cognitive control is not a second evidence store, provider router, authorization system, or workflow engine.

## 3. Cognitive controller

The controller owns only the selection of the next cognitive/work direction.

Canonical v1 decisions are:

```text
invoke-capability
propose-work
close
reopen
wait
```

Key separations:

```text
ReasonerOutput != ControllerDecision
ControllerDecision != WorkAdmission
ControllerDecision != ActionAuthorization
ControllerClose != ResponsibilityDischarge
CapabilityResult != VerifiedOutcome
```

`ControllerState` keeps references to existing context, candidate, issue, subject, and responsibility objects plus a monotonic state version and small coordination state. It does not create a second truth/knowledge ontology.

Every `ControllerDecision` binds one exact state version. Stale selections fail closed. State snapshots are append-only Event-journal entries and therefore survive the same SQLite/export/import durability boundary without adding a new store schema.

`invoke-capability` always goes through the existing Runtime/RealityBoundary/provider path. Cognitive control requests a capability; it does not select or identify a product/model implementation directly.

`propose-work` hands off to `ResponsibilityKernel.propose()`. It stops at `WorkProposal`; priority judgment, portfolio admission, resource reservation, commitment, Work materialization, authorization, and execution remain downstream responsibilities.

## 4. Responsibility identity and continuity

A `StandingResponsibility` is durable identity plus bounded statement/scope. It is not a task, provider identity, model/session identity, or authority grant.

```text
StandingResponsibility
!= Work / Run
!= provider / model / reasoning session
!= PermanentAuthority
```

Continuity across provider/model/session/process changes is represented through `ReasoningSessionBinding`, `ResponsibilityContextSnapshot`, `ResponsibilityHandoff`, and `ContinuityValidation`.

```text
ProviderChange -/-> ResponsibilityIdentityChange
ContextReset -/-> ResponsibilityLoss
ResponsibilityHandoff -/-> AuthorityTransfer
```

## 5. Current truth versus history

Historical existence does not imply current eligibility.

```text
HistoricalAssessment -/-> CurrentWorkAdmission
HistoricalControllerDecision -/-> CurrentControllerSelection
NoObservedFailure -/-> ConditionVerifiedHealthy
```

A controller decision is current only for the exact state version it names. A later observation, result, scope change, reopen, or state transition makes the old decision stale without deleting history.

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

Controller selection cannot skip this chain.

## 7. Authorization and RealityBoundary

Authority remains isolated from cognitive control, responsibility coordination, model judgment, and policy allow.

```text
ControllerDecision
        !=
assessment / proposal / priority / commitment
        !=
Decision
        !=
AuthorizationGrant / AuthorizationUse
        !=
InvocationPermit
        !=
provider execution
        !=
verified Outcome
```

The RealityBoundary remains the runtime control point before provider/external effects. Provider replacement, process restart, state import, responsibility handoff, or controller close/reopen cannot mint or transfer authority.

## 8. Durable execution model

The execution layer remains:

- `Work`: durable task/request identity;
- `Run`: one workflow execution for a Work item;
- `Step`: durable procedure position;
- `StepAttempt`: one execution attempt and request/provider lineage;
- `Checkpoint`: recoverable progress boundary;
- `Compensation`: explicit compensation intent/state.

The runtime supports interruption/resume, stale-step recovery inspection, CAS where required, idempotent paths, leases/fencing, and explicit reconciliation behavior. Ambiguous external failure is not permission to repeat a side effect.

## 9. Capability/provider boundary

`Runtime` composes:

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

Callers and the controller request capabilities rather than owning concrete providers. The kernel does not need a special concept for an external agent product; any compatible implementation remains behind the existing capability/provider boundary.

```text
controller/workflow intent
!= provider selection
!= policy allow
!= execution authorization
!= external effect
```

## 10. Semantic record plane

Record type, epistemic status, and lifecycle remain orthogonal. Provenance is retained and `produces` is not silently promoted into `causes`.

Controller result events are coordination/provenance records. A reasoning provider result does not automatically become an Assertion, official KnowledgeItem, qualification, Decision, or verified Outcome.

## 11. Revision, revalidation and lifecycle

Historical success is not permanent current validity. Typed dependency impact, revalidation disposition, controller reopen state, and responsibility lifecycle preserve history while requiring current justification after change.

Standing-responsibility lifecycle remains:

```text
active
suspended
discharged
```

Controller status remains separate:

```text
open
waiting
closed
reopen-required
```

Closing one does not mutate the other.

## 12. Stores and portability

Controller snapshots and responsibility objects use the existing StateStore/Event/SQLite/export/import/bundle durability path.

```text
state or bundle import
-/-> ControllerDecision
-/-> Work
-/-> AuthorizationGrant
-/-> InvocationPermit
-/-> external effect
```

No controller-specific database table is required by v1.

## 13. Deployment/profile boundary

Agent Kernel owns generic product semantics and implementation. Downstream deployment profiles should consume the kernel as their core and retain only environment-specific ingress, integrations, providers, policy, verification, notification, and deployment behavior.

A profile is not a second runtime semantic owner.

## 14. Trigger and public-surface boundary

Triggers remain ingress/wakeup, not Work admission:

```text
Trigger != Observation proof
Observation != ResponsibilityAssessment
ResponsibilityAssessment != Work
```

Cognitive control is canonical without requiring a new public HTTP API. HTTP exposure is a separate compatibility surface.

## 15. Non-goals

Agent Kernel does not define:

```text
continual model/policy learning
universal value/priority arbitration
automatic permanent mission creation
self-expanding permissions
handoff-based authority transfer
self-authorizing external repair
provider-specific model routing
special cross-agent interoperability semantics
```

Additional cognitive concepts are promoted only after a concrete runtime failure demonstrates that the current minimal contract cannot preserve a necessary distinction.

## 16. Source-of-truth map

| Concern | Primary source |
| --- | --- |
| Canonical semantic ownership | `contracts/README.md`, `contracts/catalog.toml`, `contracts/semantics/` |
| Cognitive control | `contracts/semantics/core/cognitive-control-v1.md`, `src/portable_runtime/controller/` |
| Persistent responsibility | `contracts/semantics/core/persistent-responsibility-v1.md`, `src/portable_runtime/responsibility/` |
| Runtime composition | `src/portable_runtime/core/runtime.py` |
| Current implementation snapshot | `docs/current-implementation.md` |
| Provider interface/protocol | `docs/provider-api.md`, `docs/provider-protocol.md` |
| Workflows | `docs/workflow-authoring.md`, `src/portable_runtime/workflows/` |
| Exact executable status | GitHub CI for the exact commit |

When explanatory prose and implementation disagree, update explanatory prose to the canonical contract/implementation. Documentation cannot demote or redefine a stable canonical contract.
