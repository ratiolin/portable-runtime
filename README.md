# portable-runtime

[![CI](https://github.com/xiongweilin/portable-runtime/actions/workflows/ci.yml/badge.svg)](https://github.com/xiongweilin/portable-runtime/actions/workflows/ci.yml) [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=portable-runtime&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=portable-runtime) [![Coverage](https://sonarcloud.io/api/project_badges/measure?project=portable-runtime&metric=coverage)](https://sonarcloud.io/summary/new_code?id=portable-runtime) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](pyproject.toml)

Portable runtime for durable **Work / Run** orchestration with pluggable **Provider / Trigger / Store / Workflow** — a responsibility-preserving, evidence-linked, authorized and revisable runtime (R1.1–R2.0).

> **R2.0 motto:** *Portable Runtime does not guarantee correctness; it guarantees that judgment, authorization, execution, verification and revision are never silently conflated, and that errors remain traceable, recoverable and reopenable.*

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

## Executable status

The exact-head executable status is defined by the repository's GitHub CI checks. Do not infer current pass counts from documentation snapshots.

For a code-oriented snapshot of the current canonical runtime and the separate non-canonical persistent-agency experiment, see [`docs/current-implementation.md`](docs/current-implementation.md).

Local verification commands:

```powershell
uv sync --locked --extra dev
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run python -m portable_runtime.public_contracts.vectors
```

The control-plane HTTP API is local-only and is not an authenticated multi-user boundary. Mutating governance routes reject non-loopback callers; remote deployments must place an authenticated, authorized deployment boundary in front of the process.

## Version axes

These identifiers describe different compatibility surfaces:

| Axis | Current value |
|---|---|
| Contract catalog | `portable-runtime-contracts-v1` |
| Control Plane schema | `official-1.0.0` |
| Portable Runtime implementation milestone | `R2.0` |
| Runtime protocol | `2.0` |
| External provider protocol | `1` (`stdio-jsonl`) |
| Distinction Governance | `distinction-governance-1.0` |
| Experience Use Admission | `experience-use-admission-v1` |
| Historical Experience Use | `historical-experience-use-v1` |
| Python package | `0.1.0` |

`Runtime protocol 2.0` covers state, bundle, HTTP and CLI compatibility surfaces. Provider protocol `1` is a separate adapter boundary; changing one axis does not imply changing another.

## Highlights

- **Execution Integrity:** `Step / StepAttempt / Checkpoint / Compensation`, CAS, lease/fencing, idempotency and explicit effect semantics prevent silent double execution after ambiguous failures.
- **Semantic Records:** `record_type`, `epistemic_status` and `lifecycle_status` remain orthogonal; provenance and `produces != causes` are enforced.
- **Revision & Revalidation:** retained history plus typed dependency impact, explicit revalidation disposition and reopen responsibilities.
- **Authorization & Policy:** `AuthorizationGrant` is isolated from judgment and policy allow; subject-version binding prevents stale authority reuse.
- **Knowledge & Experience Use:** `KnowledgeProjection` is selectively consolidated; current-use admission is separate from task/domain judgment, durable historical use and execution authority.
- **Failure-domain Routing:** deterministic routing over provider/failure-domain constraints.
- **Validation & Reliability:** closed verification remains separate from open validation and reliability policy.
- **Protocol:** append-only event journal, portable bundle validation, HTTP/CLI explain surfaces, strict negative-path conformance.
- **Public contracts:** Python is the reference execution oracle; TypeScript and the Responsibility Inspector are non-authoritative consumers.
- **Persistent-agency experiment:** `experiments/` tests non-canonical `StandingResponsibility -> SituationAssessment -> WorkProposal -> PriorityJudgment -> Commitment -> Work` semantics without promoting them into public runtime contracts or authority.

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

Explain/why queries:

```powershell
.venv\Scripts\python.exe -m portable_runtime explain <record_id>
.venv\Scripts\python.exe -m portable_runtime why <action_id>
.venv\Scripts\python.exe -m portable_runtime lineage <record_id>
.venv\Scripts\python.exe -m portable_runtime affected-by <change_ref> --change-type evaluator
.venv\Scripts\python.exe -m portable_runtime revalidation pending
.venv\Scripts\python.exe -m portable_runtime authorization list
.venv\Scripts\python.exe -m portable_runtime recovery status
```

## Architecture

```text
Intelligence / Domain Layer
        |
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
Observation / Evidence -> verification -> revalidation / recovery / reopen
```

Cross-cutting: append-only history, provenance, versioning, authorization, revalidation, recovery and portability.

- **Provider** — implements `CapabilityProvider`; effect semantics are explicit and reconciliation is an optional recovery hook behind the RealityBoundary.
- **Trigger** — creates Work from webhook/schedule/alert-compatible ingress with idempotency/authentication where applicable.
- **Store** — `StateStore / ArtifactStore / EventStore`, with SQLite and in-memory/filesystem implementations plus portable bundles.
- **Workflow** — orchestrates capabilities and explicit procedure gates; built-ins include generic task, incident repair, daily scan and knowledge consolidation.

A separate non-canonical experiment models a persistent responsibility layer above Work/Run; see [`docs/experiments/persistent-agency.md`](docs/experiments/persistent-agency.md) and [`docs/experiments/responsibility-supervisor.md`](docs/experiments/responsibility-supervisor.md).

See [`contracts/README.md`](contracts/README.md), [`contracts/catalog.toml`](contracts/catalog.toml), [docs/current-implementation.md](docs/current-implementation.md), [docs/architecture.md](docs/architecture.md), [docs/distinction-governance-implementation.md](docs/distinction-governance-implementation.md), [docs/formal-kernel-relationship.md](docs/formal-kernel-relationship.md), [docs/responsibility-separation-contracts.md](docs/responsibility-separation-contracts.md), [docs/provider-api.md](docs/provider-api.md), [docs/provider-protocol.md](docs/provider-protocol.md), [docs/workflow-authoring.md](docs/workflow-authoring.md) and [docs/state-migration.md](docs/state-migration.md).

## Public contract HTTP API

- `GET /v1/contracts`
- `POST /v1/experience/use/evaluate`
- `POST /v1/experience/historical-use/commit` (local mutation boundary)
- `GET /v1/experience/historical-use/{judgment_id}`

These surfaces expose contract DTOs/views only. They do not expose runtime-internal authority objects such as `InvocationPermit` or `GovernanceUseRequirement`, and they do not expose the experimental persistent-agency objects as canonical DTOs.

## Development

Python:

```powershell
uv sync --locked --extra dev
uv run ruff check .
uv run mypy src
uv run pytest -q
```

Public consumers after Node workspace installation:

```powershell
npm ci
npm run typecheck --workspace=@portable-runtime/contracts-client
npm run conformance --workspace=@portable-runtime/contracts-client
npm run typecheck --workspace=@portable-runtime/responsibility-inspector
npm run build --workspace=@portable-runtime/responsibility-inspector
```

The CI workflow is the exact-head source of truth for pass/fail status.

---

Standalone portable runtime for durable execution with responsibility-preserving contracts and conformance.
