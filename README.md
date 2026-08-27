# portable-runtime

[![CI](https://github.com/xiongweilin/portable-runtime/actions/workflows/ci.yml/badge.svg)](https://github.com/xiongweilin/portable-runtime/actions/workflows/ci.yml) [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=portable-runtime&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=portable-runtime) [![Coverage](https://sonarcloud.io/api/project_badges/measure?project=portable-runtime&metric=coverage)](https://sonarcloud.io/summary/new_code?id=portable-runtime) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](pyproject.toml)

Provider-neutral runtime for durable agent/workflow execution and persistent governed responsibility.

> **R2.0 motto:** Portable Runtime does not guarantee correctness; it guarantees that judgment, authorization, execution, verification and revision are never silently conflated, and that errors remain traceable, recoverable and reopenable.

## Product status

Durable Work/Run execution is a product surface, and `persistent-responsibility-v1` is now also a **stable canonical product contract** owned by `portable-runtime/contracts`.

The promoted responsibility layer is implemented under `src/portable_runtime/responsibility/` and defines durable responsibility state that may outlive any individual Work, Run, provider, model, process or reasoning session.

The core claim is deliberately bounded:

```text
StandingResponsibility
!= Work / Run
!= provider / model / reasoning session
!= permanent execution authority
```

A reasoning provider is a temporary worker, not the responsibility owner. Process/context replacement may preserve the same responsibility identity and history, but every later external effect still requires the existing current authorization / RealityBoundary path.

The older code under `experiments/` remains useful as historical/prototyping lineage. It is **not** the semantic owner of the promoted contract, and experiment-only supervisor/arbitration ideas remain non-canonical unless separately promoted later.

## Canonical contract boundary

Canonical product semantics and interoperability contracts live under [`contracts/`](contracts/README.md). `contracts/catalog.toml` is the machine-readable contract index.

The precedence rule is:

```text
contracts semantic/schema/canonicalization/vector artifacts
> Python reference implementation
> HTTP adapters
> TypeScript client/workflow helpers
> Responsibility Inspector
```

External research repositories, proofs, documents, experiments and historical commits may provide evidence or lineage, but they are not normative dependencies for current runtime state, transition, authority, qualification or wire meaning unless explicitly promoted into `contracts/`.

`persistent-responsibility-v1` follows that same rule. Its canonical semantic owner is [`contracts/semantics/core/persistent-responsibility-v1.md`](contracts/semantics/core/persistent-responsibility-v1.md), not the historical persistent-agency experiment.

## Version axes

These identifiers describe different compatibility surfaces:

| Axis | Current value |
|---|---|
| Contract catalog | `portable-runtime-contracts-v1` |
| Control Plane schema | `official-1.0.0` |
| Portable Runtime implementation milestone | `R2.0` |
| Runtime protocol | `2.0` |
| External provider protocol | `1` (`stdio-jsonl`) |
| Persistent Responsibility | `persistent-responsibility-v1` |
| Distinction Governance | `distinction-governance-1.0` |
| Experience Use Admission | `experience-use-admission-v1` |
| Historical Experience Use | `historical-experience-use-v1` |
| Python package | `0.1.0` |

These axes are intentionally independent. A documentation-only commit or a provider-protocol change does not silently advance the persistent-responsibility contract.

## Persistent responsibility

The stable product boundary is:

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

Important negative invariants include:

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

Continuity is represented explicitly through `ReasoningSessionBinding`, `ResponsibilityContextSnapshot`, `ResponsibilityHandoff` and `ContinuityValidation`. Handoff preserves durable history and requires current revalidation; it does not carry or extend effect authority.

Responsibility objects are persisted through the existing StateStore/Event/SQLite/export/import durability path rather than a second workflow engine.

## Downstream executable evidence

The canonical contract is exercised by independent downstream fault domains rather than only by local examples.

- **Commerce / listing integrity:** `commerce-orchestrator` consumes the exact canonical responsibility kernel with SQLite restart durability while keeping PostgreSQL/DBOS business facts and Commerce Decision/ExecutionAuthorization/effect truth in their existing owners. A restart preserves responsibility identity/history and does not mint `AuthorizationGrant`.
- **Operations / deployment health:** `control-plane` consumes the exact vendored runtime and proves process restart plus provider/model/session replacement while re-reading current Prometheus facts. A historical unhealthy assessment/proposal remains history; fresh healthy evidence prevents the historical proposal from becoming current Work, responsibility remains active, and handoff mints no authority.

These downstream results support a narrow product claim: the runtime can hold responsibility identity and current-use governance independently of a specific model/session/process. They do **not** imply universal autonomy, self-authorizing repair, continual learning or self-expanding permissions.

## Other core capabilities

- **Execution Integrity:** `Step / StepAttempt / Checkpoint / Compensation`, CAS, lease/fencing, idempotency and explicit effect semantics prevent silent double execution after ambiguous failures.
- **Semantic Records:** `record_type`, `epistemic_status` and `lifecycle_status` remain orthogonal; provenance and `produces != causes` are enforced.
- **Revision & Revalidation:** retained history plus typed dependency impact, explicit revalidation disposition and reopen responsibilities.
- **Authorization & Policy:** `AuthorizationGrant` is isolated from judgment and policy allow; subject-version binding prevents stale authority reuse.
- **Knowledge & Experience Use:** current-use admission is separate from historical reliance, task/domain judgment and execution authority.
- **Failure-domain Routing:** deterministic routing over provider/failure-domain constraints.
- **Validation & Reliability:** closed verification remains separate from open validation and reliability policy.
- **Protocol:** append-only event journal, portable bundle validation, HTTP/CLI explain surfaces and strict negative-path conformance.

## Architecture

```text
StandingResponsibility / current assessment / proposal / commitment
        |
        |  no authority shortcut
        v
Work / Run / Step / Attempt
        |
        v
Semantic Records + Procedure
        |
        v
Capability Router + Authorization
        |
        v
RealityBoundary -> Provider / external effect
        |
        v
Observation / Evidence -> verification -> reassessment / revalidation / recovery / reopen
```

Cross-cutting: append-only history, provenance, versioning, authorization, revalidation, recovery and portability.

- **Provider** — implements `CapabilityProvider`; provider/model identity is execution context, not durable responsibility identity.
- **Trigger** — ingress/wakeup only; a trigger does not by itself justify Work.
- **Store** — `StateStore / ArtifactStore / EventStore`, with SQLite and in-memory/filesystem implementations plus portable bundles.
- **Workflow** — orchestrates capabilities and explicit procedure gates; built-ins include generic task, incident repair, daily scan and knowledge consolidation.

See [`docs/architecture.md`](docs/architecture.md) and [`docs/current-implementation.md`](docs/current-implementation.md) for the synchronized implementation view.

## Executable status

The exact-head executable status is defined by the repository's GitHub CI checks. Do not infer current pass counts from documentation snapshots.

Local verification commands:

```powershell
uv sync --locked --extra dev
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run python -m portable_runtime.public_contracts.vectors
```

## Quick start

```powershell
uv sync
uv run runtime init
uv run runtime start
```

In another terminal:

```powershell
uv run runtime provider list
uv run runtime plugin install examples/echo-provider
uv run runtime work submit --kind generic-task --title "Echo test" --capability text.echo --description "hello"
uv run runtime work list
```

Export/import state:

```powershell
.venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db state export runtime-state.json
.venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db state import runtime-state.json
.venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db state export bundle.tar.zst
```

## Public contract HTTP surface

Current canonical public-contract HTTP routes are:

- `GET /v1/contracts`
- `POST /v1/experience/use/evaluate`
- `POST /v1/experience/historical-use/commit`
- `GET /v1/experience/historical-use/{judgment_id}`

Persistent responsibility is canonical even though its typed runtime objects are not currently exposed as mintable public HTTP DTOs. HTTP exposure and semantic canonicality are different compatibility surfaces. Internal authority objects such as `InvocationPermit` remain non-public.

The built-in HTTP control plane is local-control infrastructure, not an authenticated multi-user enterprise boundary. Remote deployments must place an authenticated and authorized deployment boundary in front of it.

## Historical experiments and non-goals

[`docs/experiments/persistent-agency.md`](docs/experiments/persistent-agency.md) now documents the historical precursor to the promoted responsibility contract. Experiment-only supervisor/arbitration ideas remain outside the stable contract until separately justified.

The current product does **not** claim:

```text
continual model/policy learning
universal value/priority arbitration
automatic permanent mission creation
self-expanding permissions
handoff-based authority transfer
self-authorizing external repair
```

External operational repair remains an ordinary governed effect chain: current assessment -> proposal/commitment -> separate current Decision/Authorization -> effect -> fresh verification -> responsibility reassessment.

## Development

```powershell
uv sync --locked --extra dev
uv run ruff check .
uv run mypy src
uv run pytest -q
```

Python is the reference execution oracle subject to `contracts/`. TypeScript helpers and the Responsibility Inspector are non-authoritative consumers.

---

Standalone portable runtime for durable execution and provider/model/session-independent persistent responsibility, with authority and current-truth boundaries kept explicit.
