# agent-kernel

[![CI](https://github.com/xiongweilin/agent-kernel/actions/workflows/ci.yml/badge.svg)](https://github.com/xiongweilin/agent-kernel/actions/workflows/ci.yml) [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=portable-runtime&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=portable-runtime) [![Coverage](https://sonarcloud.io/api/project_badges/measure?project=portable-runtime&metric=coverage)](https://sonarcloud.io/summary/new_code?id=portable-runtime) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](pyproject.toml)

Provider-neutral kernel for durable cognitive control, persistent responsibility, and governed Work/Run execution.

> Agent Kernel does not guarantee correctness. It preserves the boundaries between cognitive selection, Work admission, authorization, execution, verification, revision, and durable responsibility so errors remain traceable, recoverable, and reopenable.

## Product boundary

Agent Kernel has three connected surfaces:

```text
Cognitive Controller
    -> selects the next cognitive/work direction
    -> may invoke an existing capability
    -> may hand off only to WorkProposal

Persistent Responsibility
    -> keeps durable responsibility identity/current-use coordination
    -> outlives Work, Run, provider, model, process, and reasoning session

Durable Runtime
    -> Work / Run / Step / Attempt
    -> capability routing / policy / authorization
    -> RealityBoundary / provider execution
    -> verification / recovery / revalidation
```

The core separations are deliberate:

```text
ReasonerOutput != ControllerDecision
ControllerDecision != WorkAdmission
ControllerDecision != ActionAuthorization
ProviderSuccess != VerifiedOutcome
TaskCompleted != ResponsibilityDischarged
```

The controller is intentionally small. It references existing records and responsibility objects rather than creating a second evidence, knowledge, outcome, provider, or model-routing system.

## Canonical contracts

Canonical product semantics live under [`contracts/`](contracts/README.md). `contracts/catalog.toml` is the machine-readable contract index.

Current core contracts include:

- `persistent-responsibility-v1`
- `cognitive-control-v1`
- `responsibility-record-plane-1.0`
- `distinction-governance-1.0`
- `action-responsibility-1.0`

The precedence rule remains:

```text
contract semantics / schemas / canonicalization / vectors
> Python reference implementation
> HTTP adapters
> TypeScript helpers
> inspection surfaces
```

External research/framework documents can motivate product changes but are not runtime authority unless a distinction is explicitly promoted into `contracts/`.

## Compatibility axes

The repository/product name is `agent-kernel`. Existing implementation and wire identifiers are retained where renaming would create compatibility work without changing semantics.

| Axis | Current value |
|---|---|
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

These axes are intentionally independent. The repository rename does not silently rewrite persisted state, contract IDs, imports, or wire meaning.

## Cognitive control

The canonical controller implementation lives under `src/portable_runtime/controller/` and uses the existing append-only Event journal for durable state snapshots.

The v1 decision vocabulary is deliberately small:

```text
invoke-capability
propose-work
close
reopen
wait
```

`invoke-capability` sends a read-class `CapabilityRequest` through the existing runtime/provider path. A provider result is retained as controller evidence/provenance and is not automatically promoted to current truth or knowledge.

`propose-work` stops at the existing persistent-responsibility `WorkProposal`; priority judgment, portfolio admission, resource reservation, commitment, Work materialization, authorization, and execution remain owned by their existing layers.

`close` closes only the current cognitive-control loop. It does not complete a Work or discharge a standing responsibility.

Controller decisions bind an exact state version, so stale selections fail closed. State survives process restart through the same StateStore/Event/SQLite substrate used by the runtime.

## Persistent responsibility

The durable responsibility path remains:

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

Important invariants include:

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

Responsibility objects reuse the existing StateStore/Event/SQLite/export/import durability path rather than creating a second workflow engine.

## Runtime capabilities

- **Execution integrity:** durable `Work / Run / Step / StepAttempt`, checkpoints, compensation, CAS, lease/fencing, idempotency, and explicit reconciliation semantics.
- **Semantic records:** record type, epistemic status, and lifecycle remain orthogonal; provenance is retained and `produces != causes`.
- **Authorization:** `AuthorizationGrant` remains separate from judgment, policy allow, commitment, and controller selection.
- **Revision and revalidation:** historical state can remain true while losing current-use eligibility.
- **Capability routing:** callers request capabilities; provider selection stays behind the existing registry/router boundary.
- **Verification and reliability:** provider execution success remains separate from objective verification and long-term responsibility reassessment.
- **Portability:** append-only event history plus SQLite/export/import/bundle support survives process/provider replacement without minting authority.

## Architecture

```text
existing records / responsibility / context
        |
        v
CognitiveController
        |  invoke-capability
        |---------------------------> existing Capability / Provider path
        |                                  |
        |<----------- result/event --------|
        |
        +-- close / reopen / wait
        |
        +-- propose-work
                 |
                 v
StandingResponsibility admission chain
        |
        v
Work / Run / Step / Attempt
        |
        v
Capability Router + Policy + Authorization
        |
        v
RealityBoundary -> Provider / external effect
        |
        v
Observation / Evidence -> verification -> reassessment / revalidation / recovery
```

Cross-cutting concerns remain append-only history, provenance, versioning, current-use qualification, authorization, revalidation, recovery, and portability.

## Provider boundary

Kernel code does not need to know whether a provider is internally a model, program, service, human-mediated system, or another agent product. It requests capabilities through the existing `CapabilityProvider` interface and routing layer.

No separate agent registry, cross-agent protocol, or model catalog is part of cognitive control.

## Executable status

The exact-head executable status is defined by GitHub CI for the exact commit. Local verification:

```powershell
uv sync --locked --extra dev
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run python -m portable_runtime.public_contracts.vectors
```

## Quick start

The compatibility CLI and Python namespace remain unchanged:

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

State export/import:

```powershell
.venv\Scripts\python.exe -m portable_runtime --state data/agent-kernel.db state export runtime-state.json
.venv\Scripts\python.exe -m portable_runtime --state data/agent-kernel.db state import runtime-state.json
```

## Public surfaces

Current canonical public-contract HTTP routes remain focused on existing contract/catalog and experience-use surfaces. Cognitive control is canonical but is not exposed as a mintable public HTTP authority surface.

The built-in HTTP control plane is local-control infrastructure, not an authenticated multi-user enterprise boundary.

## Non-goals

Agent Kernel does not claim:

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

New controller concepts are promoted only when a concrete runtime failure shows that the current minimal contract cannot preserve a necessary distinction.

## Development

```powershell
uv sync --locked --extra dev
uv run ruff check .
uv run mypy src
uv run pytest -q
```

Python remains the reference execution oracle subject to `contracts/`. Existing downstream deployment profiles should consume Agent Kernel as their core and keep only profile-specific integrations, policy, ingress, notification, and deployment behavior.
