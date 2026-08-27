# Architecture

Portable Runtime R2.0 is a provider-neutral durable execution runtime with a stable canonical persistent-responsibility layer. Canonical product semantics remain owned by `contracts/`; this document is explanatory and cannot redefine those contracts.

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
> Responsibility Inspector
```

`contracts/catalog.toml` is the machine-readable contract index. External research/proof repositories, experiments and historical documents may provide evidence or lineage but are not normative inputs unless explicitly promoted into `contracts/`.

`persistent-responsibility-v1` has been promoted and is therefore part of the canonical product layer. The historical `experiments/` implementation is no longer the owner of the promoted semantics.

## 2. Product layering

The current architecture is:

```text
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
verification -> responsibility reassessment / revalidation / recovery / reopen
```

Responsibility and execution share the existing StateStore/Event durability substrate. The responsibility layer is not a second workflow engine.

## 3. Responsibility identity and continuity

A `StandingResponsibility` is durable identity plus bounded statement/scope. It is not a task, provider identity or authority grant.

```text
StandingResponsibility
!= Work / Run
!= provider / model / reasoning session
!= PermanentAuthority
```

Continuity across provider/model/session/process changes is represented through:

```text
ReasoningSessionBinding
ResponsibilityContextSnapshot
ResponsibilityHandoff
ContinuityValidation
```

The provider/model/session is a temporary worker context. A handoff preserves responsibility history but must recheck activity, scope/version, assessment/proposal freshness, expectations and reservations. It always requires execution-authorization revalidation before a later external effect.

Therefore:

```text
ProviderChange -/-> ResponsibilityIdentityChange
ContextReset -/-> ResponsibilityLoss
ResponsibilityHandoff -/-> AuthorityTransfer
```

## 4. Current truth versus history

Responsibility history is append-only. Historical existence does not imply current eligibility.

```text
HistoricalAssessment -/-> CurrentWorkAdmission
NoObservedFailure -/-> ConditionVerifiedHealthy
```

A new current observation can supersede an older assessment/proposal for current-use purposes without deleting the old record. Responsibility scope/version changes also make prior current-use eligibility stale until revalidated.

This is why continuity snapshots are history/context carriers, not current-truth or authority tokens.

## 5. Work admission

Persistent responsibility may materialize Work only through the explicit bounded chain:

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

`ResponsibilityAssessment` alone does not create Work. `WorkProposal` alone does not create a commitment. `Commitment` does not create effect authorization.

Materialized Work keeps responsibility/proposal/commitment/reservation provenance. For external effects it explicitly records that effect authority is required separately.

## 6. Authorization and RealityBoundary

Authority remains isolated from responsibility coordination, model judgment and policy allow.

```text
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

The RealityBoundary is the runtime control point before provider/external effects. Provider replacement, process restart, state import or responsibility handoff cannot mint or transfer authority.

## 7. Durable execution model

The execution layer includes:

- `Work`: durable task/request identity;
- `Run`: one workflow execution for a Work item;
- `Step`: durable procedure position;
- `StepAttempt`: one execution attempt and request/provider lineage;
- `Checkpoint`: recoverable progress boundary;
- `Compensation`: explicit compensation intent/state.

The runtime supports interruption/resume, stale-step recovery inspection, CAS where required, idempotent paths, leases/fencing and explicit reconciliation behavior. Ambiguous external failure is not permission to repeat a side effect.

## 8. Capability/provider boundary

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

Workflows request capabilities rather than owning concrete providers. Provider protocol compatibility is independent of durable responsibility identity.

The architecture distinguishes:

```text
workflow intent
!= provider selection
!= policy allow
!= execution authorization
!= external effect
```

## 9. Semantic record plane

Canonical separations include:

```text
judgment != authorization
provider/execution success != verified objective completion
supported != current-use qualified
historical provenance != current qualification
dependency impact != discharge
repair selection != repair realization
current-use admission != execution authority
```

Record type, epistemic status and lifecycle status remain orthogonal. Provenance is retained and `produces` is not silently promoted into `causes`.

## 10. Revision, revalidation and lifecycle

Historical success is not permanent current validity. Typed dependency impact, revalidation disposition and reopen state preserve history while requiring current justification after change.

Standing-responsibility lifecycle is explicit:

```text
active
suspended
discharged
```

Work completion, provider success, UI state or absence of recent failures do not discharge the responsibility. Discharge and reopen require explicit decision provenance plus an applied lifecycle transition.

## 11. Stores and portability

Responsibility objects use the existing StateStore/Event/SQLite/export/import/bundle durability path.

```text
state or bundle import
-/-> AuthorizationGrant
-/-> InvocationPermit
-/-> external effect
```

SQLite can therefore preserve both durable execution state and persistent-responsibility history across process restarts without coupling either identity to a model session.

## 12. Downstream fault-domain evidence

The architecture has independent downstream executable evidence.

### Commerce / listing integrity

Commerce keeps PostgreSQL/DBOS as the owner of business facts, Decisions, ExecutionAuthorization, effects and verified outcomes while consuming the portable responsibility kernel for durable responsibility coordination. SQLite restart preserves responsibility identity/history and does not mint effect authority.

### Operations / deployment health

Control-plane keeps Alertmanager/Prometheus operational facts profile-owned. Its responsibility adapter converts those facts into canonical assessments/read-only proposals only. A real SQLite close/reopen plus provider/model/session replacement preserves the same responsibility, and fresh Prometheus healthy evidence supersedes a still-fresh historical diagnostic proposal for current use. No Work or authorization is minted by continuity/handoff.

These domains exercise different fault boundaries and support the narrow claim that responsibility identity/current-use state can be provider/model/session/process-independent.

## 13. Trigger boundary

Triggers are ingress/wakeup, not Work admission:

```text
Trigger != Observation proof
Observation != ResponsibilityAssessment
ResponsibilityAssessment != Work
```

Missing signals are meaningful only relative to explicit expectations and evidence requirements.

## 14. HTTP/public surfaces

The built-in FastAPI control plane is local-control infrastructure, not an authenticated multi-user enterprise API.

Current public-contract HTTP routes expose the contract catalog and Experience-use surfaces. Persistent responsibility remains canonical even without mintable public HTTP responsibility DTOs; HTTP exposure is a separate compatibility surface.

Internal authority objects such as `InvocationPermit` remain non-public.

## 15. Historical experiments

`experiments/persistent_agency.py` and `docs/experiments/persistent-agency.md` were precursors to the promoted responsibility contract. Their promoted subset is now owned by `persistent-responsibility-v1` and `src/portable_runtime/responsibility/`.

Experiment-only concepts may still be useful for future falsification, including broader supervisor/autonomy/arbitration ideas. They remain non-canonical unless a later explicit contract version promotes them.

## 16. Current autonomy ceiling

The product now owns durable provider/model/session-independent responsibility state in addition to durable execution. It does **not** thereby claim unrestricted autonomous operation.

Not part of v1:

```text
continual model/policy learning
universal value/priority arbitration
automatic permanent mission creation
self-expanding permissions
handoff-based authority transfer
self-authorizing external repair
canonical universal cross-mission arbitration
```

External operational effects remain governed by current assessment/proposal/commitment plus a separate current Decision/Authorization, followed by fresh reality verification and responsibility reassessment.

## 17. Source-of-truth map

| Concern | Primary source |
| --- | --- |
| Canonical semantic ownership | `contracts/README.md`, `contracts/catalog.toml`, `contracts/semantics/` |
| Persistent responsibility | `contracts/semantics/core/persistent-responsibility-v1.md`, `src/portable_runtime/responsibility/` |
| Current implementation snapshot | `docs/current-implementation.md` |
| Runtime composition | `src/portable_runtime/core/runtime.py` |
| HTTP control plane | `src/portable_runtime/api/http.py` |
| Public contract HTTP | `src/portable_runtime/public_contracts/http.py` |
| Workflows | `docs/workflow-authoring.md`, `src/portable_runtime/workflows/` |
| Provider interface/protocol | `docs/provider-api.md`, `docs/provider-protocol.md` |
| Historical persistent-agency precursor | `docs/experiments/persistent-agency.md`, `experiments/` |
| Exact executable status | GitHub CI for the exact commit |

When explanatory prose and implementation disagree, update explanatory prose to the canonical contract/implementation. Documentation cannot demote a stable canonical contract back into an experiment.
