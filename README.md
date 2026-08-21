# portable-runtime

[![CI](https://github.com/ratiolin/portable-runtime/actions/workflows/ci.yml/badge.svg)](https://github.com/ratiolin/portable-runtime/actions/workflows/ci.yml) [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=portable-runtime&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=portable-runtime) [![Coverage](https://sonarcloud.io/api/project_badges/measure?project=portable-runtime&metric=coverage)](https://sonarcloud.io/summary/new_code?id=portable-runtime) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](pyproject.toml)

Portable runtime for durable **Work / Run** orchestration with pluggable **Provider / Trigger / Store / Workflow** — now a **responsibility-preserving, evidence-linked, authorized and revisable** runtime (R1.1–R2.0).

> **R2.0 motto:** *Portable Runtime does not guarantee correctness; it guarantees that judgment, authorization, execution, verification and revision are never silently conflated, and that errors remain traceable, recoverable and reopenable.*

## Strict enforcement status

The RealityBoundary, SQLite Store, semantic-plane P1 work and protocol P2 work are locally closed with executable evidence. The current protocol-convergence sequence has this verified proof:

- `uv run ruff check .` and `uv run mypy src` — both clean;
- `uv run pytest -q` — `264 passed` (two existing collection/deprecation warnings only);
- strict-conformance — `59 passed`: E001–E023, S001–S006, semantic-contract, authorization-contract, P1 semantic, P2 protocol, routing and reliability gates;
- canonical `KnowledgeProjection` state is bundle-portable; legacy `KnowledgeItem` remains read-compatible but is not a new workflow write target;
- HTTP mutating control routes are loopback-only and explicitly not an authenticated multi-user boundary;
- the CI `strict-conformance` job runs the same focused suite and is a prerequisite for SonarCloud analysis;
- the prior remote proof for the already-pushed baseline remains green in [main CI run 32442371727](https://github.com/ratiolin/portable-runtime/actions/runs/32442371727); the current sequence is green in [main CI run 32446261971](https://github.com/ratiolin/portable-runtime/actions/runs/32446261971), including SonarCloud new-code coverage at `80.3%`.

The baseline link above is historical evidence; run `32446261971` is the authoritative post-push proof for this sequence.

The control-plane HTTP API is local-only and is not an authenticated multi-user boundary. Mutating governance routes (state import, provider enable/disable/reload, capability execution and reopen) reject non-loopback callers; remote deployments must place an authenticated, authorized deployment boundary in front of the process.

## Version axes

These identifiers intentionally describe different compatibility surfaces:

| Axis | Current value |
|---|---|
| Framework semantics | `1.0.0` |
| Control Plane schema | `official-1.0.0` |
| Portable Runtime implementation milestone | `R2.0` |
| Runtime protocol | `2.0` |
| Python package | `0.1.0` |
| Framework compatibility | `framework-v1` |

## Highlights (R1.1–R2.0)

- **Execution Integrity (R1.1):** `Step / StepAttempt / Checkpoint / Compensation` with `CAS / Lease+Fencing / idempotency` and `effect semantics` (`pure / idempotent / deduplicatable / reconcilable / irreversible-opaque → unknown`) — crash after provider no silent double-execution.
- **Semantic Records (V1.2):** `record_type ⊥ epistemic_status ⊥ lifecycle_status` — 13 types (`EvidenceArtifact / Observation / Assertion / Goal / Constraint / Experiment / Decision / Action / Outcome / Revision / ChangeObject / Policy / Derivation`) with `produces != causes` enforcement.
- **Revision & Revalidation (V1.3):** `Revision(revises→old, produces→new, supersedes)` with retained history; `typed dependency` (`validated-under / executed-with / …`) → `AffectedAssessment` (`block-next-use` / `background-revalidate` etc., no recursive invalidation).
- **Authorization & Policy (V1.4):** `AuthorizationGrant` isolated from `Decision` (`subject_version_refs` prevents v1→v2 reuse); `PolicyDecision(disposition=allow/deny/defer/require, obligations[])` with `deny > defer > union(needs) > allow` algebra and `waivable:false` hard boundaries; `ProcedureProfile` (`minimal / standard / enhanced`).
- **Knowledge & Reopen (V1.5):** `KnowledgeProjection` selective consolidation (never drops counterexamples); `ReopenAssessment(9 scopes) → superseding Work`.
- **Failure-domain Routing (V1.6):** `ProviderDescriptor` 9 domains (`provider_family / credential_domain / …`) + `ConstraintRouter` (`hard constraints → eligible → deterministic → cost`).
- **Validation & Reliability (V1.7–1.8):** `ClosedVerification(pass/fail)` vs `OpenValidation(supports/weakens/…)` + `ExperimentPlan` + `CircuitBreaker / ReliabilityControls`; structural observations, risk assessments and the versioned `DefaultLocalReliabilityPolicy` remain separate.
- **Protocol (R2.0):** `Event Journal` append-only, `Bundle v1` (`manifest + 17 kinds jsonl + artifacts/ + sha256 checksums`) with full ref/lifecycle validation, 4-category HTTP API + `explain/why/lineage/affected-by/reopen` CLI, and strict negative-path conformance.
- **P1/P2 strict semantics:** qualification facts resolve from typed store references into an immutable assessment/permit and authority-sensitive invocation snapshot; compatibility views are non-reentrant into canonical consolidation; derivation and verification judgment remain distinct; deep reopen reroutes to reframing without auto-rerunning the original workflow; dependency impact, risk assessment and revalidation disposition remain separate; state/bundle imports are graph-validated atomically.

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
# module entry:
# .venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db status
# .venv\Scripts\python.exe -m portable_runtime plugin validate examples/echo-provider
# .venv\Scripts\python.exe -m portable_runtime work submit --title "Echo test" --description "hello" --kind generic-task --capability text.echo
```

Export / import state without any model or network:

```powershell
.venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db state export runtime-state.json
.venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db state import runtime-state.json
# bundle (portable + artifacts + checksums)
.venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db state export bundle.tar.zst
```

New CLI why queries:

```powershell
.venv\Scripts\python.exe -m portable_runtime explain <record_id>
.venv\Scripts\python.exe -m portable_runtime why <action_id>
.venv\Scripts\python.exe -m portable_runtime lineage <record_id>
.venv\Scripts\python.exe -m portable_runtime affected-by <change_ref> --change-type evaluator
.venv\Scripts\python.exe -m portable_runtime revalidation pending
.venv\Scripts\python.exe -m portable_runtime authorization list
.venv\Scripts\python.exe -m portable_runtime recovery status
.venv\Scripts\python.exe -m portable_runtime knowledge list --negative
```

## Architecture

```
Intelligence / Domain Layer (model / human / solver → generate / compare / validate)
                    |
              Work Layer (Work / Run / Step / Attempt / Checkpoint / reopen)
                    |
     Semantic Records (EvidenceArtifact / Assertion / Decision / Revision / Outcome)  +  Procedure (minimal/standard/enhanced)
                    |
              Capability Router (hard constraints / failure-domains / authorization)
                    |
                Reality (processes / APIs / files / Git)
                    |
           Observation / Evidence → revalidation → correction → reopen  ↺
```

Cross-cutting: `append-only history / provenance / versioning / authorization / revalidation / recovery / portability`.

- **Provider** – implements `CapabilityProvider`; open capability strings (`text.echo`, `verify.http`, `code.edit`, `human.approve`, …). `effect_semantics` and `reconcile()` are part of the contract.
- **Trigger** – creates Work (`webhook`, `schedule`, `alertmanager`-compatible with `IdempotencyStore` + HMAC).
- **Store** – `StateStore / ArtifactStore / EventStore` on `src/portable_runtime/interfaces`; `SQLite` (WAL, CAS, Lease) and `InMemory` / `Filesystem` included, plus `Bundle` tar.zst with manifest validation.
- **Workflow** – orchestrates `context.invoke(capability, ...)` and `context.require("purpose-identified")`; built-ins: `generic_task`, `incident_repair`, `daily_scan`, `knowledge_consolidation` + `ProcedureProfile` gates.

See [docs/architecture.md](docs/architecture.md),
[docs/portable-runtime-reality-boundary-authoritative-plan.md](docs/portable-runtime-reality-boundary-authoritative-plan.md),
[docs/portable-runtime-strict-enforcement-closure-plan.md](docs/portable-runtime-strict-enforcement-closure-plan.md),
[docs/portable-runtime-strict-enforcement-plan.md](docs/portable-runtime-strict-enforcement-plan.md),
[docs/provider-api.md](docs/provider-api.md),
[docs/provider-protocol.md](docs/provider-protocol.md),
[docs/plugin-authoring.md](docs/plugin-authoring.md),
[docs/workflow-authoring.md](docs/workflow-authoring.md),
[docs/store-api.md](docs/store-api.md),
[docs/state-migration.md](docs/state-migration.md) and
[docs/deployment-local.md](docs/deployment-local.md).

## HTTP API (4 categories)

- **Operational:** `/v1/work`, `/v1/runs`, `/v1/steps`, `/v1/artifacts`, `/v1/events`
- **Semantic:** `/v1/records`, `/v1/relations`, `/v1/evidence`, `/v1/revalidation/pending`, `/v1/revalidation/affected-by/{change_ref}`
- **Governance:** `/v1/authorizations`, `/v1/policies`, `/v1/procedures/{work_id}`, `/v1/reopen/{record_id}`
- **Knowledge & explain:** `/v1/knowledge?negative=true`, `/v1/explain/{record_id}`, `/v1/why/{action_id}`, `/v1/lineage/{record_id}`, `/v1/recovery/status`

## Plugin authoring

Copy a template and declare capabilities – no Core change required:

```powershell
Copy-Item -Recurse templates/provider-python my-provider  # optional local template
# or start from examples/echo-provider
```

`examples/echo-provider/manifest.json`:

```json
{
  "id": "echo",
  "name": "Example Echo Provider",
  "version": "1.0.0",
  "protocol_version": "1",
  "transport": "stdio-jsonl",
  "command": ["python", "provider.py"],
  "capabilities": ["text.echo"]
}
```

Validate and test:

```powershell
uv run runtime plugin validate examples/echo-provider
# or
.venv\Scripts\python.exe -m portable_runtime plugin test examples/echo-provider
```

## Deployment

Local (no Docker required):

```python
from pathlib import Path
from portable_runtime.deployment.local import create_local_runtime

runtime = create_local_runtime(Path("data/portable-runtime.db"), Path("data/artifacts"))
```

Reference profile: `examples/personal-platform-profile` is a minimal trigger/provider mapping example (Schedule/Alertmanager + verifiers) you can adapt to your own deployment.

## Development

```powershell
uv sync --extra dev
uv run ruff check .
uv run mypy src
uv run pytest              # 264 tests; current local verification
uv run pytest --cov=src --cov-report=xml  # for SonarCloud
```

The fresh local coverage run reports 77% overall coverage; SonarCloud reports 80.3% new-code coverage for the current sequence. The quality gate is enforced in CI: `sonar-project.properties` pins `sonar.python.version=3.12`, `sonar.qualitygate.wait=true`, `sonar.cpd.exclusions=tests/**,...`, and `sonar.issue.ignore.multicriteria` for the 2 intentional `tests/**` S5779 and the 2 retained `hashlib.sha1` compat branches.

---

Standalone portable runtime for durable execution — now with responsibility-preserving protocol and conformance suite.
