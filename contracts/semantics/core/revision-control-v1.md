# Revision control — v1

Status: stable
Owner: `agent-kernel/contracts`
Contract: `revision-control-v1`

This contract defines the minimum durable assessment required after execution/verification returns reality evidence to cognitive control. It separates failure evidence from the decision to retry, revise, reopen, reconcile, wait or close.

## Boundary

```text
Work / Run / external effect
    -> verification / Outcome
    -> RevisionAssessment
    -> later controller/runtime disposition
```

Canonical separations:

```text
FailureObserved != RetryPermission
ProviderFailure != EffectAbsent
RevisionAssessment != ControllerDecision
RevisionAssessment != WorkMutation
RevisionAssessment != Reopen
RevisionAssessment != ActionAuthorization
VerifiedFailure != AutomaticProblemRedefinition
```

## Revision scopes

Canonical v1 scopes are:

```text
execution
work-spec
decision
representation
inputs
evidence-acquisition
verification
goal
authorization
problem-definition
```

They identify where current closure may have failed. They are not a total theory of error attribution.

## Dispositions

Canonical v1 recommendations are:

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

A recommendation is not self-executing. Runtime/controller owners still apply their own admissibility and authority checks.

## Evidence grounding

Every revision assessment must reference the closure it is revising, the relevant Work identity, and at least one Outcome or verification reference. Closing requires explicit verification references.

`retry-run` is inadmissible for deep scopes such as representation, inputs, evidence-acquisition, verification, goal, authorization or problem-definition. `reconcile-effect` is only admissible for execution scope. `request-authorization` is only admissible for authorization scope.

## Reopen

Recommendations that invalidate current cognitive closure (`revise-work`, `reopen-cognition`, `acquire-evidence`) move the controller to `reopen-required`. Only an explicit later `reopen` restores OPEN cognition and clears current closure eligibility.

A retry/reconciliation/authorization/wait recommendation keeps cognitive control waiting. It does not itself start a Run or mint authority.

## Handoff

Revision carries a `CognitiveHandoffEnvelope` with explicit carry-forward, reconsider, invalidated and unresolved references. Reopen must preserve history rather than reconstructing context from mutable Work metadata.

## Legacy reopen boundary

Record-level reopen assessments may remain historical/observation objects, but they cannot create Work. New Work after cognitive failure must re-enter through:

```text
RevisionAssessment
    -> explicit controller reopen
    -> new CognitiveClosure
    -> WorkProposal
    -> normal admission
```

## Non-goals

This contract does not define a universal failure classifier, a model-specific retry policy, automatic permanent mission creation or automatic authorization. It only preserves the distinctions required to keep failure handling inspectable and reopenable.
