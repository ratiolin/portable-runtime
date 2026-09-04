# agent-kernel

[![CI](https://github.com/xiongweilin/agent-kernel/actions/workflows/ci.yml/badge.svg)](https://github.com/xiongweilin/agent-kernel/actions/workflows/ci.yml) [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=portable-runtime&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=portable-runtime) [![Coverage](https://sonarcloud.io/api/project_badges/measure?project=portable-runtime&metric=coverage)](https://sonarcloud.io/summary/new_code?id=portable-runtime) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](pyproject.toml)

Provider-neutral kernel for durable cognitive control, persistent responsibility, and governed Work/Run execution.

> Agent Kernel does not guarantee correctness. It preserves the boundaries between open cognition, temporary closure, Work admission, authorization, execution, verification, revision, reopen, and durable responsibility so failures remain traceable and recoverable.

## Product boundary

Agent Kernel has three connected surfaces:

```text
Cognitive Controller
    -> selects the next cognitive/work direction
    -> may invoke read-class cognition/observation capabilities
    -> forms a temporary CognitiveClosure
    -> may hand off a closure only to WorkProposal
    -> receives reality feedback through RevisionAssessment
    -> may explicitly reopen, wait, or close the current cognitive episode

Persistent Responsibility
    -> keeps durable responsibility identity/current-use coordination
    -> outlives Work, Run, provider, model, process, and reasoning session

Durable Runtime
    -> Work / Run / Step / Attempt
    -> capability routing / policy / authorization
    -> RealityBoundary / provider execution
    -> verification / recovery / revalidation / reconciliation
```

Core separations:

```text
ReasonerOutput != ControllerDecision
ReasonerOutput != CognitiveClosure
CognitiveClosure != WorkProposal
ControllerDecision != WorkAdmission
ControllerDecision != ActionAuthorization
FailureObserved != RetryPermission
RevisionAssessment != RetryRun
RevisionAssessment != Reopen
ProviderSuccess != VerifiedOutcome
ControllerClose != ResponsibilityDischarge
TaskCompleted != ResponsibilityDischarged
```

The controller is intentionally small. It references existing records and responsibility objects rather than creating a second evidence, knowledge, outcome, provider, or model-routing system.

## Canonical contracts

Canonical product semantics live under [`contracts/`](contracts/README.md). `contracts/catalog.toml` is the machine-readable contract index.

Current core contracts include:

- `persistent-responsibility-v1`
- `cognitive-control-v2`
- `cognitive-closure-v1`
- `revision-control-v1`
- `responsibility-record-plane-1.0`
- `distinction-governance-1.0`
- `action-responsibility-1.0`

Precedence:

```text
contract semantics / schemas / canonicalization / vectors
> Python reference implementation
> HTTP adapters
> TypeScript helpers
> inspection surfaces
```

External research/framework documents can motivate product changes but are not runtime authority unless a distinction is explicitly promoted into `contracts/`.

## Compatibility axes

| Axis | Current value |
|---|---|
| Contract catalog | `portable-runtime-contracts-v1` |
| Python distribution | `portable-runtime` |
| Python namespace | `portable_runtime` |
| Runtime protocol | `2.0` |
| External provider protocol | `1` (`stdio-jsonl`) |
| Persistent Responsibility | `persistent-responsibility-v1` |
| Cognitive Control | `cognitive-control-v2` |
| Cognitive Closure | `cognitive-closure-v1` |
| Revision Control | `revision-control-v1` |
| Distinction Governance | `distinction-governance-1.0` |
| Experience Use Admission | `experience-use-admission-v1` |
| Historical Experience Use | `historical-experience-use-v1` |

These axes are intentionally independent. Repository or implementation changes do not silently rewrite persisted state, contract IDs, imports, or wire meaning.

## Closed cognitive loop

The canonical controller implementation lives under `src/portable_runtime/controller/` and uses the existing append-only Event journal for durable state snapshots.

The v2 decision vocabulary is:

```text
invoke-capability
form-closure
propose-work
assess-revision
close
reopen
wait
```

The intended loop is:

```text
existing context / records / responsibility state
        |
        v
OPEN cognition
  |  invoke-capability: observe / explore / compare
  |
  +-> form-closure
        |
        v
CognitiveClosure
  |  basis / selected direction / deferred issues
  |  acceptance criteria / verification plan
  |  stop + reopen conditions / capability + effect ceiling
        |
        v
WorkProposal
        |
priority / portfolio / reservation / commitment
        |
        v
Work / Run / Step / Attempt
        |
Capability Router + Policy + Authorization
        |
RealityBoundary -> provider / external effect
        |
        v
Observation / Evidence -> verification -> Outcome
        |
        v
RevisionAssessment
  |      |        |         |          |
 retry  revise   reopen   reconcile   close/wait
  |               |
  |          explicit REOPEN
  |               |
  +---------------+-------------------------> OPEN cognition
```

### Temporary closure

`CognitiveClosure` records why exploration is temporarily paused for one bounded scope. It must include a basis, selected direction, acceptance criteria, verification plan, reopen conditions, and explicit treatment of current open issues. It is not truth, Work, admission, or authority.

While a closure is active, ordinary exploration is blocked. The controller may hand the closure to `WorkProposal`, wait, or close. Renewed exploration requires explicit reopen.

### Work handoff

`propose-work` must reference the active closure. Requested capabilities cannot exceed the closure capability set and the effect class must match the closure. It creates only `WorkProposal`; priority judgment, portfolio admission, resource reservation, commitment, Work materialization, authorization, and execution remain downstream.

After WorkProposal handoff the controller waits for downstream reality feedback rather than continuing to generate competing Work from the same closure.

### Revision

After execution and independent verification, a `RevisionAssessment` records where the current closure may have failed and recommends one bounded disposition:

```text
retry-run
revise-work
reopen-cognition
acquire-evidence
request-authorization
reconcile-effect
wait
close
```

The assessment is not self-executing. Failure does not authorize retry. Deep scopes cannot recommend retry-run, ambiguous external effects must be reconciled through the runtime boundary, and close requires verification evidence.

Recommendations that invalidate the current closure move the controller to `reopen-required`; only explicit `reopen` restores OPEN cognition and clears current closure eligibility while preserving closure/revision history.

## Legacy reopen boundary

Historical `records.reopen` objects remain readable for compatibility and observation tooling, but the old `create_reopen_work()` shortcut is retired and fails loudly.

A cognitive failure that requires new Work must follow:

```text
RevisionAssessment
    -> explicit controller reopen
    -> new CognitiveClosure
    -> WorkProposal
    -> normal admission / authorization / execution
```

There is no `reopen -> Work` shortcut.

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

Important invariants:

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

## Runtime capabilities

- **Execution integrity:** durable `Work / Run / Step / StepAttempt`, checkpoints, compensation, CAS, lease/fencing, idempotency, and explicit reconciliation semantics.
- **Semantic records:** record type, epistemic status, and lifecycle remain orthogonal; provenance is retained and `produces != causes`.
- **Authorization:** `AuthorizationGrant` remains separate from judgment, policy allow, commitment, closure, revision, and controller selection.
- **Revision and revalidation:** historical state can remain true while losing current-use eligibility.
- **Capability routing:** callers request capabilities; provider selection stays behind the existing registry/router boundary.
- **Verification and reliability:** provider execution success remains separate from objective verification and long-term responsibility reassessment.
- **Portability:** append-only event history plus SQLite/export/import/bundle support survives process/provider replacement without minting authority.

## Provider boundary

Kernel code does not need to know whether a provider is internally a model, program, service, human-mediated system, or another agent product. It requests capabilities through the existing `CapabilityProvider` interface and routing layer.

Model identity is not a semantic role and grants no capability or authority. No separate agent registry, cross-agent protocol, or model catalog is part of cognitive control.

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

Cognitive control is canonical but is not exposed as a mintable public HTTP authority surface. The built-in HTTP control plane is local-control infrastructure, not an authenticated multi-user enterprise boundary.

Legacy `/v1/reopen` cannot mint replacement Work under the v2 cognitive-control architecture.

## Non-goals

Agent Kernel does not claim:

```text
candidate-generation theory
universal search-allocation or closure policy
universal revision-depth policy
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

Python remains the reference execution oracle subject to `contracts/`. Downstream deployment profiles should consume Agent Kernel as their core and retain only profile-specific integrations, policy, ingress, notification, verification, provider, and deployment behavior.
