# Architecture

Portable Runtime R2.0 is a responsibility-preserving durable execution runtime. The repository also contains a deliberately non-canonical persistent-agency experiment above the runtime. Canonical product semantics remain owned by `contracts/`; experimental code and this document are explanatory/testing surfaces and cannot redefine those contracts.

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

`contracts/catalog.toml` is the machine-readable contract index. Source-checkout and installed-wheel consumers resolve the same repository-owned catalog; wheel builds package a distribution copy under `portable_runtime/_contracts` so public contract interpretation does not depend on a Git checkout.

External research repositories, proof repositories, experiments and historical documents may provide evidence or lineage, but they are not normative inputs to current runtime state, authority, qualification, transition or wire meaning unless explicitly promoted into `contracts/`.

## 2. Repository layering

The current repository has two distinct layers:

```text
EXPERIMENTAL / NON-CANONICAL
StandingResponsibility
  -> Observation / ExpectedSignal
  -> SituationAssessment
  -> WorkProposal
  -> PriorityJudgment
  -> Commitment + ResourceEnvelope
  -> ResponsibilitySupervisor
        |
        v
CANONICAL / PRODUCT RUNTIME
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
verification -> revalidation / recovery / reopen
```

The upper layer currently lives under `experiments/` and `docs/experiments/`. It is not imported as a public runtime API, is not listed in the canonical contract catalog, and is explicitly non-authority-bearing.

The lower layer is the current portable runtime product surface. Cross-cutting concerns include append-only history, provenance, versioning, idempotency, leases/fencing, explicit authority, failure-domain routing, recovery, conformance and state portability.

## 3. Durable execution model

The basic orchestration objects are:

- `Work`: durable task/request identity;
- `Run`: one workflow execution for a Work item;
- `Step`: durable procedure position;
- `StepAttempt`: one execution attempt and its request/provider lineage;
- `Checkpoint`: recoverable progress boundary;
- `Compensation`: explicit compensation intent/state rather than implicit rollback.

The runtime supports interruption/resume, stale-step recovery inspection, CAS where required by stores, idempotent execution paths, and run leases with fencing semantics. Lease acquire/renew/release attempts are journaled when the event store is available.

Ambiguous external failure is not treated as permission to blindly repeat a side effect. The compatibility `Runtime.reconcile(step_id)` path is intentionally fail-closed: a Step plus its latest attempt does not prove a unique reconciliation responsibility, so it cannot authorize an external reconciliation effect on its own.

## 4. Capability and provider boundary

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

Workflows and callers request a capability; they do not directly own provider selection. The RealityBoundary is the control point between runtime judgment/governance state and provider/external effects.

Provider protocol `1` is a separate compatibility axis from runtime protocol `2.0`. The stdio provider transport uses `stdio-jsonl`; changing provider transport does not silently redefine runtime state or responsibility semantics.

## 5. Responsibility and semantic record plane

The record plane preserves distinctions that ordinary agent/workflow stacks often collapse. Important canonical separations include:

```text
judgment != authorization
policy allow != AuthorizationGrant
provider/execution success != verified/confirmed objective completion
epistemic supported != governance qualified
governed state application != real-world Action
historical provenance != current qualification
dependency impact != discharge
repair selection != repair realization
current-use admission != execution authority
```

Record type, epistemic status and lifecycle status are intentionally orthogonal. Provenance is retained, and `produces` is not silently promoted into `causes`.

Generic relation ingress does not allow a caller to manufacture local governance edges by naming them. Authority-bearing local semantic relations require matching durable proof, such as a covering `AuthorizationUse` or the exact Revision endpoint relationship. Reopen lineage is committed through the reopen control action rather than fabricated by a generic relation payload.

The complete canonical separation set is owned by `contracts/semantics/core/responsibility-separation-v1.md`.

## 6. Authorization and current validity

Authorization is isolated from model judgment and from policy allow. Authority is bound to the subject/context that was actually authorized, including version references where required.

The architecture therefore distinguishes:

```text
judgment formed
        !=
policy says allowed
        !=
authority granted
        !=
authority used for this invocation/effect
        !=
external action actually occurred
```

Public consumers may inspect non-authority-bearing views, but cannot reconstruct internal authority objects from those views. `InvocationPermit` and `GovernanceUseRequirement` remain internal; public surfaces expose bounded views only.

The persistent-agency experiment does not weaken this boundary. `Commitment` and resource allocation in the experiment are explicitly non-authority-bearing; an external effect still requires the existing authorization path.

## 7. Revision, revalidation and reopen

Historical success is not permanent current validity.

The runtime retains dependency/provenance history and can represent typed impact, pending revalidation, explicit revalidation disposition and reopen responsibility. A changed evaluator, policy, dependency or other governing basis may invalidate current use without rewriting the historical fact that an earlier judgment or action occurred.

The resulting rule is:

```text
historically accepted / qualified / used
        !=
currently eligible for reuse
```

Reopen creates new responsibility/history; it does not erase the earlier closed state.

## 8. Knowledge and Experience use

`KnowledgeProjection` is selectively consolidated state, not a synonym for reality or authority.

The Experience contracts distinguish:

```text
current ExperienceUseAdmission
        !=
HistoricalExperienceUse
        !=
task/domain judgment
        !=
execution authorization
```

Historical use records what experience was actually relied on for a judgment. Current-use admission is re-evaluated independently; the existence of historical use does not self-qualify the same experience for current use.

The canonical public DTOs/schemas and semantics are under `contracts/schemas/experience/` and `contracts/semantics/experience/`.

## 9. Workflow boundary

Workflows describe procedure and capability use, not concrete provider ownership. They call `WorkflowContext.invoke(capability, ...)` and stores rather than importing a concrete provider implementation.

Built-in workflows currently include:

- `generic-task`;
- `incident-repair`;
- `daily-scan`;
- `knowledge-consolidation`.

`generic-task` is intentionally fail-closed: provider `status="succeeded"` proves execution only. Durable outputs/evidence prove delivery only. Without an explicitly injected objective verifier returning literal `True`, the workflow waits rather than declaring terminal success.

## 10. Trigger boundary

Triggers can create Work from webhook/schedule/alert-compatible ingress and may apply ingress authentication/idempotency as appropriate.

Canonical Trigger semantics remain ingress semantics. A Trigger does not itself prove that a new Work is justified, prioritized or authorized.

The persistent-agency experiment specifically tests a richer sequence above Work:

```text
Observation / ExpectedSignal
!= SituationAssessment
!= WorkProposal
!= Commitment
!= ExecutionAuthorization
```

`ResponsibilitySupervisor` requires a registered SituationAssessment before a WorkProposal can be registered, preserving the distinction between being awakened by an event and committing Work.

## 11. Persistent-agency experiment

`experiments/persistent_agency.py` currently defines non-canonical candidate objects including:

- `StandingResponsibility` and its active/suspended/discharged lifecycle;
- `Observation` and `ExpectedSignal`;
- `SituationAssessment`;
- `WorkProposal` and proposal lifecycle;
- multidimensional `PriorityJudgment`;
- `ResourceRequest` and `ResourceEnvelope`;
- `Commitment`;
- `WorkRecord`;
- `RoleDelegation`;
- `EscalationPolicy`;
- `ResponsibilityPortfolio`.

`experiments/responsibility_supervisor.py` adds a non-canonical coordinator that:

- refuses a WorkProposal without a registered SituationAssessment under the same standing responsibility;
- enforces committed resource ceilings through explicit `ResourceConsumption` records;
- can turn an overdue `ExpectedSignal` with absent evidence into a SituationAssessment;
- keeps bounded Work completion separate from standing-responsibility discharge.

Candidate non-equivalences are documented in `docs/experiments/persistent-agency.md`. They are intentionally not canonical. Promotion requires repeated domain evidence that collapsing a candidate responsibility position causes a real shortcut, ambiguity or unsafe state.

The experiment therefore demonstrates executable candidate semantics, not a public Stage-4 product contract.

## 12. Stores and portability

The runtime separates state, artifacts and events through interfaces such as `StateStore`, `ArtifactStore` and event-journal operations.

Current implementations include in-memory and SQLite/filesystem-backed local operation, plus portable export/import and bundle support. Runtime protocol `2.0` covers the state/bundle/HTTP/CLI compatibility surface.

Portable state preserves durable identity/history; importing state does not grant new semantic authority by itself.

The persistent-agency experiment currently uses in-process dataclass state and is not part of the canonical portable state/bundle protocol.

## 13. HTTP control-plane boundary

The FastAPI control plane intentionally does not pretend to be an authenticated multi-user service.

Mutating control/governance routes call a local-control guard and reject non-loopback callers. A remote deployment must put an authenticated and authorized deployment boundary in front of this process rather than treating the built-in HTTP server as an enterprise IAM boundary.

Core HTTP surfaces include runtime/health/provider/work/run/state/knowledge and governance inspection/control routes. Canonical public-contract routes are attached by `portable_runtime.public_contracts.http.create_public_app()`:

```text
GET  /v1/contracts
POST /v1/experience/use/evaluate
POST /v1/experience/historical-use/commit
GET  /v1/experience/historical-use/{judgment_id}
```

The historical-use commit endpoint is a local mutation boundary.

No persistent-agency experiment object is exposed as a canonical HTTP contract.

## 14. Public contract packaging and conformance

`contracts/` is the semantic owner; Python is the reference execution oracle. TypeScript packages and the Responsibility Inspector are non-authoritative consumers.

The installed Python wheel packages the canonical contract catalog and required public contract artifacts for downstream consumers. Conformance vectors verify public DTO/canonical behavior and negative paths.

The persistent-agency experiment is covered by ordinary repository tests, not canonical conformance vectors. Passing those tests does not promote its semantics into the public contract catalog.

## 15. Current autonomy ceiling

Portable Runtime currently provides substantial infrastructure useful for persistent governed agency: durable tasks, event ingress, provider-independent execution, authority separation, long-lived state/history, revalidation, recovery/reopen and explicit reality boundaries.

The repository now also contains an executable Stage-4 candidate experiment for standing responsibility, proposal/commitment separation, priority dimensions, resource envelopes, missing-signal assessment and responsibility supervision.

However, the canonical runtime still does **not** own these as public/product responsibilities:

```text
StandingResponsibility / Mission
Goal Portfolio
SituationAssessment -> WorkProposal admission
Proposal -> Commitment
priority/resource arbitration
resource/budget commitment
role-level perpetual responsibility lifecycle
autonomous task generation as a canonical responsibility contract
continual model/policy learning
```

The correct current claim is therefore:

```text
implemented and tested experimentally
!= canonicalized
!= publicly authority-bearing
!= integrated into durable Work/Run persistence
```

These concepts must not be inferred from Trigger, Work, KnowledgeProjection or Experience-use support, and the experiment must not be described as if it had already become the production runtime layer.

## 16. Documentation/source-of-truth map

| Concern | Primary source |
| --- | --- |
| Canonical semantic ownership | `contracts/README.md`, `contracts/catalog.toml`, `contracts/semantics/` |
| Current implementation snapshot | `docs/current-implementation.md` |
| Runtime composition | `src/portable_runtime/core/runtime.py` |
| HTTP control plane | `src/portable_runtime/api/http.py` |
| Public contract HTTP | `src/portable_runtime/public_contracts/http.py` |
| Workflows | `docs/workflow-authoring.md`, `src/portable_runtime/workflows/` |
| Provider interface/protocol | `docs/provider-api.md`, `docs/provider-protocol.md` |
| Persistent-agency experiment | `docs/experiments/persistent-agency.md`, `docs/experiments/responsibility-supervisor.md`, `experiments/` |
| Distinction governance | `docs/distinction-governance-implementation.md` and canonical contracts |
| Responsibility separations | `docs/responsibility-separation-contracts.md` and canonical contracts |
| State/bundle migration | `docs/state-migration.md` |
| Exact executable status | GitHub CI for the exact commit |

When explanatory prose and implementation disagree during a documentation synchronization pass, update explanatory prose to the implementation unless the mismatch is a canonical-contract violation. Canonical contract violations must be fixed in implementation rather than documented away.
