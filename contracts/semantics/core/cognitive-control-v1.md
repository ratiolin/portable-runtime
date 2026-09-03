# Cognitive control — v1

Status: stable
Owner: `agent-kernel/contracts`
Contract: `cognitive-control-v1`

This contract defines the minimum durable separation required for cognitive
control above the existing portable runtime. It does not define a reasoning
algorithm, model policy, agent product, model router, new evidence plane or new
authorization system.

## Product boundary

```text
existing context / records / responsibility state
    -> ControllerState
    -> ControllerDecision
        -> cognitive capability invocation
        -> WorkProposal handoff
        -> close / reopen / wait
```

The controller owns selection of the next cognitive/work direction. Existing
owners continue to own facts, provider execution, Work admission, execution
authority, external effects, verification and responsibility lifecycle.

`ControllerState` references existing records and responsibility objects. It
must not duplicate the Responsibility Record Plane or promote provider output
into a second truth store.

## Canonical negative invariants

| ID | Contract |
| --- | --- |
| CC-001 | `ReasonerOutput -/-> CurrentTruth`. |
| CC-002 | `ReasonerOutput -/-> ControllerDecision`. A reasoner result may inform a later selection but does not select itself. |
| CC-003 | `ControllerDecision -/-> Work`. `PROPOSE_WORK` may create only a canonical `WorkProposal`; existing responsibility admission still owns Work materialization. |
| CC-004 | `ControllerDecision -/-> ActionAuthorization`. |
| CC-005 | `ControllerClose -/-> ResponsibilityDischarge`. |
| CC-006 | `ControllerClose -/-> ActionAuthorization`. |
| CC-007 | `CapabilityResult -/-> VerifiedOutcome`. Provider success remains execution evidence only. |
| CC-008 | A controller decision is bound to one exact `ControllerState.version`; stale decisions fail closed. |
| CC-009 | A waiting controller state requires an explicit reopen before another controller selection. |
| CC-010 | Controller restart/reconstruction preserves state identity/history but mints no Work or authority. |
| CC-011 | Cognitive capability invocation uses the existing capability/provider boundary; cognitive control does not create a second provider registry or model router. |
| CC-012 | Framework/research text is not a runtime decision or authority source. Only promoted product contracts and current runtime state govern this contract. |

## Durable state

The canonical implementation keeps the controller state deliberately small:

```text
ControllerState
    identity
    optional responsibility/subject refs
    context refs
    candidate refs
    open-issue refs
    open / waiting / closed / reopen-required status
    monotonic version
    pending request ref
    latest decision/result refs
```

These are coordination references, not new epistemic statuses. Evidence,
assertions, outcomes, knowledge and responsibility objects remain owned by their
existing contracts.

A durable implementation may persist controller snapshots in the existing
append-only Event journal. Storage representation does not make Event the
semantic owner.

## Decisions

The v1 decision vocabulary is intentionally small:

```text
invoke-capability
propose-work
close
reopen
wait
```

`invoke-capability` creates a read-class `CapabilityRequest` through the
existing Runtime/RealityBoundary/provider path. The provider result is retained
as controller evidence/provenance for reassessment; it is not automatically
written as knowledge or current truth.

`propose-work` hands off to the existing persistent-responsibility
`WorkProposal` contract. The controller does not perform priority judgment,
portfolio admission, resource reservation, commitment or Work materialization.

`close` ends only the current cognitive-control loop. It does not complete a
Work, discharge a responsibility or authorize an effect.

`reopen` and `wait` are controller coordination states only. A restart while
waiting preserves the pending request reference and requires explicit handling;
it is not permission to repeat an ambiguous external operation.

## Provider neutrality

The controller requests capabilities, not product/model identities. Existing
provider routing owns provider selection. A provider may internally be a model,
program, service, human-mediated system or another agent product without any
special controller semantics.

No separate agent registry, cross-agent protocol or model catalog is introduced
by this contract.

## Promotion evidence

The initial promoted implementation must demonstrate at least:

- a reasoning capability result remains evidence/candidate material and creates
  neither Work nor knowledge/current truth by itself;
- `PROPOSE_WORK` stops at canonical `WorkProposal`;
- controller close leaves an active standing responsibility active;
- stale controller decisions are rejected;
- controller state survives SQLite process restart through the existing durable
  store/event substrate.

## Non-goals

This contract does not define candidate-generation theory, search allocation,
revision-depth policy, continual learning, a universal priority function,
conversation/UI semantics, provider-specific model routing or external-agent
interoperability features. Such distinctions are promoted only after a concrete
runtime failure shows that the existing contract cannot preserve a necessary
responsibility boundary.
