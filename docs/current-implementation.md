# Current implementation snapshot

This document describes the implementation baseline promoted by PR #56 at commit `b26487a6efe3933c5d92d637b522eac211e153c1` (2026-08-27). Documentation-only closure commits may advance repository `main` without changing this runtime/contract baseline.

This file is explanatory. Canonical product semantics remain owned by `contracts/`.

## Project boundary

Portable Runtime is a provider-neutral durable agent/workflow runtime with a canonical persistent-responsibility layer.

The current product has two related but distinct responsibilities:

```text
durable execution
= Work / Run / Step / Attempt / recovery / effect integrity

persistent responsibility
= durable responsibility identity + current assessment/proposal/commitment state
  that can outlive a Work, Run, provider, model, process or reasoning session
```

Neither layer owns permanent execution authority. External effects continue to cross the existing Decision / Authorization / RealityBoundary path.

The older `experiments/` package is retained as historical/prototyping lineage. It is not the semantic owner of `persistent-responsibility-v1`; experiment-only supervisor/arbitration concepts remain non-canonical unless separately promoted.

The project does not claim continual model/policy learning.

## Compatibility axes

| Axis | Current value |
| --- | --- |
| Contract catalog | `portable-runtime-contracts-v1` |
| Control Plane schema | `official-1.0.0` |
| Implementation milestone | `R2.0` |
| Runtime protocol | `2.0` |
| External provider protocol | `1` (`stdio-jsonl`) |
| Persistent Responsibility | `persistent-responsibility-v1` |
| Distinction Governance | `distinction-governance-1.0` |
| Experience Use Admission | `experience-use-admission-v1` |
| Historical Experience Use | `historical-experience-use-v1` |
| Python package | `0.1.0` |

These axes are intentionally independent.

## Canonical packaging

`contracts/` is the only canonical semantic/interoperability owner. `contracts/catalog.toml` is packaged into installed wheels through `portable_runtime/_contracts` so interpretation does not depend on a Git checkout.

`persistent-responsibility-v1` is cataloged as a canonical contract and has a structural schema under `contracts/schemas/responsibility/`.

The Python reference implementation lives under:

```text
src/portable_runtime/responsibility/models.py
src/portable_runtime/responsibility/persistence.py
src/portable_runtime/responsibility/domain.py
src/portable_runtime/responsibility/service.py
src/portable_runtime/responsibility/reference_profiles.py
src/portable_runtime/responsibility/inspection.py
```

## Runtime composition

The execution runtime composes:

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

Persistent-responsibility objects reuse the configured runtime store/event journal rather than creating a second orchestration engine.

## Durable execution

Implemented execution integrity includes:

- durable `Work`, `Run`, `Step` and `StepAttempt` identities;
- checkpoints and compensation records;
- idempotency/effect semantics;
- lease acquire/renew/release with fencing;
- stale-step recovery inspection;
- interruption/resume/cancel operations;
- reconciliation/recovery paths that fail closed when reality is ambiguous.

Provider success is execution evidence only. It does not automatically become objective completion.

## Persistent responsibility

The canonical responsibility chain is:

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

The implementation contains typed objects for the responsibility identity/lifecycle, expectations, assessments, proposals, priority/portfolio decisions, reservations, commitments and continuity records.

`ResponsibilityKernel` enforces current responsibility version/activity, freshness, append-only identity, resource bounds and the proposal/admission/commitment chain. `materialize_work()` preserves responsibility provenance and marks external effect authority as separately required; it never creates an `AuthorizationGrant`.

## Persistence and restart

`ResponsibilityJournal` stores canonical responsibility objects through the existing Event/StateStore layer. SQLite therefore gives the responsibility layer the same durable process-restart boundary as the runtime store.

State export/import and bundle portability preserve responsibility identity/history but do not synthesize authority:

```text
imported responsibility history
-/-> AuthorizationGrant
-/-> InvocationPermit
-/-> external effect
```

## Provider/model/session continuity

The canonical continuity objects are:

```text
ReasoningSessionBinding
ResponsibilityContextSnapshot
ResponsibilityHandoff
ContinuityValidation
```

A reasoning provider/model/session is execution context, not the durable responsibility owner.

`validate_handoff()` rechecks at least responsibility activity, current scope/version, assessment freshness, expectations, proposals and reservations. It always marks execution authorization for revalidation. Handoff itself does not transfer or extend authority.

## Current truth and historical state

Historical state remains append-only history. Current-use eligibility is separately re-evaluated.

Canonical negative invariants include:

```text
HistoricalAssessment -/-> CurrentWorkAdmission
ProviderChange -/-> ResponsibilityIdentityChange
ContextReset -/-> ResponsibilityLoss
ResponsibilityHandoff -/-> AuthorityTransfer
NoObservedFailure -/-> ConditionVerifiedHealthy
TaskCompleted -/-> ResponsibilityDischarged
```

A later fact may supersede a historical assessment/proposal for current use without deleting the historical record.

## Provider and capability routing

Providers are registered independently of workflows. Callers request capabilities rather than owning provider selection.

The architecture separates:

```text
workflow intent
!= provider selection
!= policy allow
!= execution authorization
!= external effect
```

External provider transport is a separate compatibility axis from runtime state and responsibility identity.

## Authorization and governance

Authorization remains separate from model judgment, policy allow, commitment and Work materialization.

The current implementation includes authorization grants/use, subject-version binding, governance-use admission/dispatch and the RealityBoundary.

Public views are non-authority-bearing; internal objects such as `InvocationPermit` cannot be reconstructed or minted from a view.

## Revision, revalidation and reopen

The runtime retains provenance/history and supports typed dependency impact, explicit revalidation disposition and reopen semantics.

A historical judgment/use can remain historically true while becoming ineligible for current use because its governing basis changed.

Responsibility lifecycle transitions are also explicit. Work completion, provider success or absence of observed failures cannot discharge a standing responsibility. Discharge/reopen require explicit decision provenance.

## Knowledge and Experience use

Current Experience-use admission remains separate from historical reliance, task/domain judgment and execution authority.

Public Experience contracts include current-use requirements/admission and durable historical-use records. Historical use cannot self-qualify experience for current use.

## HTTP/public-contract surface

`portable_runtime.public_contracts.http.create_public_app()` currently exposes canonical contract catalog/Experience routes such as:

```text
GET  /v1/contracts
POST /v1/experience/use/evaluate
POST /v1/experience/historical-use/commit
GET  /v1/experience/historical-use/{judgment_id}
```

Persistent responsibility is canonical even though its runtime objects are not currently exposed as mintable public HTTP DTOs. Semantic canonicality and HTTP exposure are separate compatibility surfaces.

The built-in FastAPI control plane is local-control infrastructure, not an authenticated multi-user enterprise API.

## Downstream executable evidence

The stable responsibility contract is exercised outside portable-runtime itself.

### Commerce

`commerce-orchestrator` consumes the exact `b26487a6...` responsibility implementation and persists its responsibility journal in SQLite while retaining PostgreSQL/DBOS as owners of Commerce business facts, Decision/ExecutionAuthorization, effects and verified outcomes.

Its crash/restart test demonstrates same responsibility identity/version/status/history after reopening, continuation without duplicate Work, no `AuthorizationGrant`, bounded Work completion through existing `CompletionAuthority`, and responsibility remaining `ACTIVE`.

### Deployment Health

`control-plane` vendors the exact `src/portable_runtime` tree from `b26487a6...` and adds only a profile-owned monitoring fact adapter.

Its downstream continuity test closes/reopens SQLite, replaces provider/model/session, validates the same active `StandingResponsibility`, then reads a fresh Prometheus health fact. The earlier unhealthy assessment/proposal remains historical evidence while the fresh healthy assessment prevents that old proposal from becoming current Work. No priority/portfolio admission, commitment, Work or `AuthorizationGrant` is created by the adapter/handoff.

The test deliberately performs the fresh-health update while the historical diagnostic proposal is still within its TTL, proving current-fact supersession rather than expiry.

## Historical experiment status

`experiments/persistent_agency.py` and `experiments/responsibility_supervisor.py` preceded the canonical promotion and remain useful for research/prototyping.

The promoted subset is now owned by `persistent-responsibility-v1` and `src/portable_runtime/responsibility/`. Experiment-only concepts such as a general-purpose `ResponsibilitySupervisor`, universal cross-mission arbitration or broader autonomy policies remain experimental.

Do not use the experiment documents as the current product-status authority.

## Current autonomy ceiling

Canonical now:

```text
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
responsibility persistence in StateStore/SQLite/bundles
```

Not claimed by v1:

```text
continual model/policy learning
universal value or priority function
automatic permanent mission creation
self-expanding permissions
handoff-based authority transfer
self-authorizing external repair
canonical universal cross-mission arbitration
```

The bounded product claim is therefore:

```text
durable execution
+
durable provider/model/session-independent responsibility identity/current-use state
+
separate current authority and verification boundaries
```

This is sufficient to call the runtime a persistent governed agent runtime in the responsibility-state sense; it is not a claim of unrestricted autonomous operation.

## Source-of-truth map

| Concern | Primary source |
| --- | --- |
| Canonical semantics | `contracts/README.md`, `contracts/catalog.toml`, `contracts/semantics/` |
| Persistent responsibility | `contracts/semantics/core/persistent-responsibility-v1.md`, `src/portable_runtime/responsibility/` |
| Runtime implementation | `src/portable_runtime/core/runtime.py` |
| Core HTTP API | `src/portable_runtime/api/http.py` |
| Public contract HTTP | `src/portable_runtime/public_contracts/http.py` |
| Workflow authoring | `docs/workflow-authoring.md`, `src/portable_runtime/workflows/` |
| Provider API/protocol | `docs/provider-api.md`, `docs/provider-protocol.md` |
| Architecture explanation | `docs/architecture.md` |
| Historical persistent-agency precursor | `docs/experiments/persistent-agency.md`, `experiments/` |
| Exact executable status | GitHub CI for the exact commit |

When prose and code disagree, explanatory prose must be synchronized to the canonical contract/implementation. Documentation cannot demote or redefine a stable canonical contract.
