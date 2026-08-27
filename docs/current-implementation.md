# Current implementation snapshot

This document describes the implementation present at `main` commit `bec27d0e6c723007d33ac7031bb89c4e44a07fc7` (2026-08-27). It is a code-oriented snapshot, not a second semantic owner. Canonical product semantics remain under `contracts/`.

## Project boundary

Portable Runtime is a standalone durable Work/Run orchestration runtime with pluggable providers, triggers, stores and workflows. Its distinguishing implementation goal is responsibility preservation: judgment, authorization, execution, verification, historical use and revision are represented as separate facts rather than collapsed into one success state.

The repository also contains an executable persistent-agency experiment under `experiments/`. That experiment models candidate Stage-4 positions above Work/Run, but it is explicitly **experimental, non-canonical and non-authority-bearing**. It does not change `src/portable_runtime`, the canonical contract catalog or public runtime APIs.

The current repository therefore has two different claims:

```text
portable-runtime product/runtime
    = canonical durable orchestration + responsibility-preserving contracts

persistent-agency experiment
    = tested candidate semantics above Work/Run
      that have not been promoted into canonical runtime contracts
```

The project does not claim continual model/policy learning.

## Current compatibility axes

| Axis | Current value |
| --- | --- |
| Contract catalog | `portable-runtime-contracts-v1` |
| Control Plane schema | `official-1.0.0` |
| Implementation milestone | `R2.0` |
| Runtime protocol | `2.0` |
| External provider protocol | `1` (`stdio-jsonl`) |
| Distinction Governance | `distinction-governance-1.0` |
| Experience Use Admission | `experience-use-admission-v1` |
| Historical Experience Use | `historical-experience-use-v1` |
| Python package | `0.1.0` |

These axes are intentionally independent. Experimental Stage-4 types do not create an additional public compatibility axis because they are not canonical contracts.

## Canonical contract packaging

`contracts/` is the only canonical semantic/interoperability owner. The precedence rule is documented in `contracts/README.md`.

`src/portable_runtime/public_contracts/catalog.py` resolves the catalog from either:

```text
source checkout: contracts/catalog.toml
installed wheel: portable_runtime/_contracts/catalog.toml
```

The installed distribution therefore does not need a repository checkout to expose the canonical public contract catalog. The packaged copy is distribution data; semantic ownership remains `contracts/`.

The persistent-agency experiment is intentionally absent from `contracts/catalog.toml` and from the packaged public-contract surface.

## Runtime composition

`src/portable_runtime/core/runtime.py` currently composes:

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

`Runtime.create_work()` persists a `Work`. `Runtime.start_run()` creates a durable `Run` and advances the Work into running state. Capability execution is constructed through `InvocationFactory` and crosses `RealityBoundary` through the capability service.

The model/provider is not itself the durable owner of Work history. Runtime state remains in the configured store and can survive provider replacement where the deployment/store supports persistence.

## Execution integrity

The current execution model includes:

- `Work` and `Run` identities;
- durable `Step` and `StepAttempt` state;
- checkpoints and compensation records;
- idempotency/effect semantics;
- lease acquire/renew/release with fencing behavior;
- stale-step recovery inspection;
- interruption/resume/cancel operations;
- event journal entries around control/recovery transitions where available.

Lease/fencing is explicit rather than inferred from process ownership. Ambiguous dispatch does not grant permission to repeat a side effect.

`Runtime.reconcile(step_id)` remains as a compatibility surface but is deliberately fail-closed. A Step plus latest attempt does not uniquely identify a reconciliation responsibility, so the method returns an unknown/authoritative-reconciliation-required result instead of crossing the provider boundary.

## Provider and capability routing

Providers are registered independently of workflows. Callers request capabilities and the routing/boundary layer resolves execution subject to contracts, constraints and policy.

The current architecture separates:

```text
workflow intent
!= provider selection
!= policy allow
!= execution authorization
!= external effect
```

External providers can be enabled/disabled/reloaded through local control-plane routes. Provider health and capability inventory are observable through HTTP and metrics surfaces.

## Workflow implementation

Workflows use `WorkflowContext` and request capabilities rather than importing concrete providers.

Current built-ins documented and registered in the repository include:

- `generic-task`;
- `incident-repair`;
- `daily-scan`;
- `knowledge-consolidation`.

`generic-task` is intentionally fail-closed. Provider execution success does not automatically become terminal objective success. Without an explicit objective verifier returning literal `True`, the workflow returns/waits rather than manufacturing completion.

## Trigger implementation

The trigger interface supports ingress that creates Work from webhook/schedule/alert-compatible inputs, with authentication/idempotency where a trigger implementation requires them.

Canonical Trigger semantics remain ingress semantics. Trigger wake-up is not itself current proof that a Work is justified, prioritized, resource-admitted or execution-authorized.

The persistent-agency experiment tests that missing layer explicitly rather than silently upgrading Trigger semantics.

## Responsibility and semantic records

The runtime contains a responsibility/semantic record plane with canonical separations owned by `contracts/semantics/core/responsibility-separation-v1.md`.

Important implemented distinctions include:

```text
judgment != authorization
policy allow != AuthorizationGrant
provider success != verified/confirmed objective completion
supported != qualified
governed application != real-world Action
historical provenance != current qualification
dependency impact != discharge
repair selection != repair realization
Experience-use admission != execution authority
```

Record type, epistemic status and lifecycle status are separate axes. Relations preserve provenance, and `produces` is not treated as `causes` without an explicit basis.

Generic relation writes cannot fabricate protected local governance relations merely by naming an edge type. Local governance edges require matching durable authority/revision proof; reopen lineage is owned by the reopen action.

## Authorization / governance boundary

Authorization is represented separately from judgment and policy.

The current implementation includes authorization grants/use, subject-version binding and governance admission/dispatch logic. Public contract/view surfaces are deliberately non-authority-bearing and do not expose internal objects such as `InvocationPermit` or `GovernanceUseRequirement` as mintable public DTOs.

The persistent-agency experiment preserves the same ceiling:

```text
WorkProposal
!= Commitment
!= ExecutionAuthorization
```

A `Commitment` may bind bounded resources, stop conditions and escalation conditions, but it does not mint authority for an external effect.

## Revision, revalidation and reopen

The runtime retains historical state/provenance and supports typed dependency impact, revalidation state/disposition and reopen semantics.

A historical judgment/use can remain true as a historical fact while becoming ineligible for current use because its governing basis changed. Revalidation therefore updates current qualification/responsibility without rewriting prior history.

CLI/HTTP inspection surfaces include lineage, affected-by, pending revalidation, authorization/recovery and reopen-related views/actions.

## Knowledge and Experience contracts

Knowledge projection and experience use are implemented as separate responsibilities.

Public Experience contracts currently cover:

- `ExperienceUseRequirementV1`;
- `ExperienceUseAdmissionV1`;
- resolved Experience-use snapshot;
- `HistoricalExperienceUseV1` and its commit command.

The runtime distinguishes current admission from durable historical reliance. Historical reliance cannot self-qualify selected experience for current use, and an existing historical record cannot be silently rebound to a different judgment identity.

## Public contract HTTP surface

`portable_runtime.public_contracts.http.create_public_app()` attaches canonical public-contract routes to the existing control-plane app:

```text
GET  /v1/contracts
POST /v1/experience/use/evaluate
POST /v1/experience/historical-use/commit
GET  /v1/experience/historical-use/{judgment_id}
```

The historical-use commit route applies a loopback/local mutation guard and maps contract failures into stable problem codes such as identity rebound, self-qualification/backfill rejection and digest mismatch.

No persistent-agency experiment object is exposed through these canonical public-contract routes.

## Control-plane HTTP boundary

The built-in FastAPI control plane is intentionally local-control infrastructure, not an authenticated multi-user enterprise API.

Mutating control/governance paths invoke a loopback guard. Remote deployments are expected to place a separate authenticated/authorized deployment boundary in front of the runtime.

The core HTTP app exposes, among other surfaces:

```text
runtime / health / metrics
providers / capabilities
work / runs
state import/export
knowledge and semantic records
governance / authorization / revalidation / recovery controls
```

Exact route inventory is owned by `src/portable_runtime/api/http.py` and the public-contract router.

## Stores and portability

The implementation separates state, artifacts and events behind interfaces. The repository includes in-memory state for embedded/test use and SQLite/filesystem-backed local deployment, plus state export/import and portable bundle support.

Portable bundle/state operations preserve durable records and identity. Importing state is a persistence operation; it does not synthesize authority or qualification beyond the imported canonical facts and their contracts.

Persistent-agency experiment state is currently in-process dataclass state under `experiments/`. It is not integrated into the canonical StateStore/bundle protocol.

## Public consumers

Python is the reference execution oracle subject to `contracts/`.

The repository also contains non-authoritative consumers:

- TypeScript contract client/workflow helpers;
- Responsibility Inspector.

Their typechecking/conformance/build checks are part of CI. They must not reinterpret a public view as an authority-bearing runtime object.

## Persistent-agency experiment

PR #52 added a falsifiable Stage-4 candidate layer without promoting it into product semantics.

`experiments/persistent_agency.py` currently defines:

```text
StandingResponsibility
Observation
ExpectedSignal
SituationAssessment
WorkProposal
PriorityDimensions / PriorityJudgment
ResourceRequest / ResourceEnvelope
Commitment
WorkRecord
RoleDelegation
EscalationPolicy
ResponsibilityPortfolio
```

The candidate flow is:

```text
StandingResponsibility
  -> Observation / ExpectedSignal
  -> SituationAssessment
  -> WorkProposal
  -> PriorityJudgment
  -> Commitment + ResourceEnvelope
  -> Work
  -> completion
  -> StandingResponsibility remains independently active
```

The experiment also models missing expected signals: elapsed time plus absent expected evidence may create a `SituationAssessment`, but absence has meaning only relative to an explicit `ExpectedSignal`.

`experiments/responsibility_supervisor.py` adds `ResponsibilitySupervisor` and `ResourceConsumption`. The supervisor currently enforces:

1. WorkProposal requires a registered SituationAssessment under the same standing responsibility;
2. Commitment requires an admitted PriorityJudgment and a resource allocation within the governing envelope;
3. accumulated resource consumption cannot exceed the exact Commitment allocation;
4. bounded Work completion does not discharge the StandingResponsibility;
5. escalation policy can keep financial/irreversible effects on a human-review route while allowing other autonomous coordination.

The associated experiment tests live in:

```text
tests/test_persistent_agency_experiment.py
tests/test_responsibility_supervisor_experiment.py
```

Candidate non-equivalences include:

```text
Observation != SituationAssessment
SituationAssessment != WorkProposal
WorkProposal != Commitment
Commitment != ExecutionAuthorization
PriorityJudgment != ValueTruth
ResourceAllocation != ExternalEffectAuthority
TaskCompleted != StandingResponsibilityDischarged
StandingResponsibility != PermanentAuthority
RoleDelegation != SubdelegationRight
NoObservedFailure != ConditionVerifiedHealthy
```

These are experimental hypotheses, not canonical contracts.

## Current autonomy ceiling

Implemented in the canonical runtime now:

```text
trigger/event ingress
Work / Run durability
provider-independent capability execution
explicit reality boundary
authorization / policy separation
semantic/provenance history
revalidation / reopen
recovery / fencing
knowledge/experience-use governance
```

Implemented and tested experimentally, but not canonicalized:

```text
StandingResponsibility
SituationAssessment
WorkProposal
PriorityJudgment
Commitment
ResourceEnvelope / ResourceConsumption
ResponsibilityPortfolio
ExpectedSignal missing-event assessment
EscalationPolicy
ResponsibilitySupervisor
```

Still not a canonical product/runtime responsibility:

```text
GoalPortfolio as a public runtime abstraction
persistent responsibility persistence in StateStore/bundles
a canonical WorkProposal/Commitment API
a canonical autonomous task-generation contract
canonical cross-mission priority/resource arbitration
continual model/policy learning
```

The important current distinction is:

```text
executable experiment
!= canonical contract
!= public runtime API
!= authority-bearing production layer
```

## Source-of-truth map

| Concern | Primary source |
| --- | --- |
| Canonical semantics | `contracts/README.md`, `contracts/catalog.toml`, `contracts/semantics/` |
| Runtime implementation | `src/portable_runtime/core/runtime.py` |
| Core HTTP API | `src/portable_runtime/api/http.py` |
| Public contract HTTP | `src/portable_runtime/public_contracts/http.py` |
| Public contract catalog loading | `src/portable_runtime/public_contracts/catalog.py` |
| Workflow authoring | `docs/workflow-authoring.md`, `src/portable_runtime/workflows/` |
| Provider API/protocol | `docs/provider-api.md`, `docs/provider-protocol.md` |
| Architecture explanation | `docs/architecture.md` |
| Persistent-agency experiment | `docs/experiments/persistent-agency.md`, `docs/experiments/responsibility-supervisor.md`, `experiments/` |
| Distinction governance | canonical contracts + `docs/distinction-governance-implementation.md` |
| Responsibility separation | canonical contracts + `docs/responsibility-separation-contracts.md` |
| State migration | `docs/state-migration.md` |
| Exact executable status | GitHub CI for the exact commit |

When prose and code disagree during an implementation synchronization pass, explanatory prose should be updated to match implementation unless the implementation violates a canonical contract. A canonical-contract violation must be fixed in code; documentation must not redefine the contract to make the implementation appear conformant.
