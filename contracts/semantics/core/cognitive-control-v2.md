# Cognitive control — v2

Status: stable
Owner: `agent-kernel/contracts`
Contract: `cognitive-control-v2`

This contract defines the minimum durable closed cognitive loop above the existing runtime. It does not define a reasoning algorithm, model policy, model router, evidence plane, Work admission policy or authorization system.

## Product boundary

```text
existing context / records / responsibility state
    -> ControllerState
    -> ControllerPolicy selection
    -> ControllerDecision
        -> invoke-capability
        -> form-closure
        -> propose-work
        -> assess-revision
        -> close / reopen / wait
```

The controller owns selection and durable coordination only. Facts, provider execution, Work admission, execution authority, effects, verification and standing-responsibility lifecycle remain owned by their existing layers.

## Canonical decisions

```text
invoke-capability
form-closure
propose-work
assess-revision
close
reopen
wait
```

`form-closure` creates a canonical `CognitiveClosure` bound to the exact controller state version. It does not create Work.

`propose-work` requires the active closure and creates only a canonical `WorkProposal`. The controller then waits for downstream admission/execution/reality feedback.

`assess-revision` records a canonical `RevisionAssessment`. It does not itself retry a Run, mutate Work, authorize an effect or redefine the standing responsibility.

## Canonical negative invariants

| ID | Contract |
| --- | --- |
| CC2-001 | `ReasonerOutput -/-> CurrentTruth`. |
| CC2-002 | `ReasonerOutput -/-> ControllerDecision`. |
| CC2-003 | `ReasonerOutput -/-> CognitiveClosure`. |
| CC2-004 | `CognitiveClosure -/-> Work`. |
| CC2-005 | `CognitiveClosure -/-> ActionAuthorization`. |
| CC2-006 | `ControllerDecision -/-> Work`. |
| CC2-007 | `ControllerDecision -/-> ActionAuthorization`. |
| CC2-008 | `CapabilityResult -/-> VerifiedOutcome`. |
| CC2-009 | `FailureObserved -/-> RetryPermission`. |
| CC2-010 | `RevisionAssessment -/-> RetryRun`. |
| CC2-011 | `RevisionAssessment -/-> Reopen`. |
| CC2-012 | `ControllerClose -/-> ResponsibilityDischarge`. |
| CC2-013 | Every controller decision is bound to one exact `ControllerState.version`; stale decisions fail closed. |
| CC2-014 | An active closure blocks further ordinary exploration until Work handoff, wait/close, or explicit reopen. |
| CC2-015 | `PROPOSE_WORK` must reference the active closure and stops at `WorkProposal`. |
| CC2-016 | Waiting controllers accept only explicit reopen or revision assessment. |
| CC2-017 | `reopen-required` and closed states accept only explicit reopen. |
| CC2-018 | Restart/reconstruction preserves state/history but mints no Work or authority. |
| CC2-019 | Cognitive capability invocation uses the existing capability/provider boundary. |
| CC2-020 | Framework/research text is not a runtime decision or authority source. |

## Durable state

The canonical state remains deliberately small:

```text
ControllerState
    identity
    optional responsibility/subject refs
    context refs
    candidate refs
    open-issue refs
    status: open | waiting | closed | reopen-required
    monotonic version
    pending ref
    active closure ref
    WorkProposal ref
    last revision ref
    latest decision/result refs
```

These are coordination references. They do not create a second truth, evidence, outcome, provider or authorization store.

## State transitions

Before closure:

```text
open(no active closure)
    -> invoke-capability | form-closure | close | wait
```

After closure:

```text
open(active closure)
    -> propose-work | close | wait
```

Work handoff:

```text
propose-work
    -> waiting(pending = WorkProposal)
```

Reality return:

```text
waiting
    -> assess-revision | reopen
```

Revision recommendations that invalidate closure move to `reopen-required`; retry/reconcile/authorization/wait recommendations remain waiting; verified close may close the controller episode.

```text
closed | reopen-required
    -> reopen
```

Explicit reopen returns OPEN and clears current closure/WorkProposal eligibility while preserving historical closure/revision records.

## Policy seam

`ControllerPolicy` remains the single replaceable selection seam. It may use any model, program, service or human-mediated cognition, but it only returns one version-bound `ControllerDecision`. Model identity conveys no authority.

## Provider neutrality

The controller requests capabilities, not model identities. Provider selection remains behind the existing registry/router boundary. A compatible provider may internally be a model, program, service, human-mediated system or another agent product.

## Promotion evidence

Conformance must demonstrate at least:

- reasoner output creates neither closure nor Work by itself;
- closure without basis, acceptance criteria, verification plan or reopen conditions is rejected;
- every current open issue is explicitly deferred before closure;
- further exploration is rejected while a closure is active;
- Work proposal without the active closure is rejected;
- Work handoff stops at `WorkProposal` and changes the controller to waiting;
- failure evidence does not automatically retry or reopen;
- close revision requires verification references;
- deep revision cannot recommend retry-run;
- explicit reopen clears current closure eligibility while retaining history;
- controller close does not discharge standing responsibility;
- controller state survives process restart.

## Non-goals

This contract does not define candidate-generation theory, search allocation, a universal closure policy, a universal revision-depth policy, continual learning, a universal priority function, model-tier semantics, provider-specific model routing or external-agent interoperability.
