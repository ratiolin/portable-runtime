# Responsibility separation — v1

Status: stable
Owner: `agent-kernel/contracts`
Contract: `responsibility-separation-v1`

These are canonical product responsibility-separation contracts. They prevent one responsibility object, state, observation, or model output from silently substituting for another.

| ID | Canonical product contract |
|---|---|
| RSC-001 | A qualification-state change keeps the subject and provenance addressable and produces an append-only transition audit fact. |
| RSC-002 | An Assertion used as positive current-use qualification must be current and supported; stale or revalidation-required assertions cannot issue a new invocation permit. |
| RSC-003 | Dependency impact is not discharge. |
| RSC-004 | Selecting a repair is not realizing the repair. |
| RSC-005 | Provider or execution success is not terminal objective completion. |
| RSC-006 | A known semantic mismatch remains explicit; runtime direct typed impact is not rewritten into a different historical or transitive impact semantics. |
| RSC-007 | Domain or framework-level judgment, `GovernanceDecision`, and Responsibility Record Plane `Decision` are distinct responsibility objects; none silently mints action authorization. |
| RSC-008 | `GovernedApplication` is a committed governance-state application, not evidence that a real-world Responsibility Record Plane `Action` occurred. |
| RSC-009 | Responsibility Record Plane `epistemic_status=supported` is not Distinction Governance `qualification=qualified`; qualification requires its own governed responsibility edge. |
| RSC-010 | `PolicyDecision=allow` is not `AuthorizationGrant`; policy admission does not mint authority. |
| RSC-011 | `resolve_allowed` / `existing_assignment_use_allowed` may use an assignment already registered in the adopted partition; it does not classify reality, mutate partition membership, or assert ontic truth. |
| RSC-012 | Governance admissibility validation does not prove external source truth; missing, ambiguous, stale, or mismatched identity, provenance, freshness, authority, or required source material fails closed for new positive use. |
| RSC-013 | `ReasonerOutput` is not `ControllerDecision`; provider cognition may inform selection but cannot select itself. |
| RSC-014 | `ReasonerOutput` is not `CognitiveClosure`; fluent or repeated model output cannot independently establish temporary closure. |
| RSC-015 | `CognitiveClosure` is not `WorkProposal`, Work admission, or execution authority. |
| RSC-016 | `ControllerDecision` is not Work admission or action authorization. |
| RSC-017 | `FailureObserved` is not retry permission; failure evidence must not silently repeat an operation. |
| RSC-018 | `RevisionAssessment` is not a retry, Work mutation, controller reopen, responsibility revision, or action authorization. |
| RSC-019 | `ControllerClose` is not `ResponsibilityDischarge`. |
| RSC-020 | Historical closure/revision existence is not current-use eligibility; current controller state/version remains authoritative for coordination. |

## Authority ceiling

No RSC entry authorizes execution by itself. In particular:

```text
judgment -/-> authorization
policy allow -/-> AuthorizationGrant
current-use admission -/-> InvocationPermit
GovernedApplication -/-> real-world Action
provider success -/-> confirmed Outcome
historical use -/-> current qualification
ReasonerOutput -/-> CognitiveClosure
CognitiveClosure -/-> Work
CognitiveClosure -/-> ActionAuthorization
FailureObserved -/-> RetryRun
RevisionAssessment -/-> RetryRun
RevisionAssessment -/-> Reopen
ControllerClose -/-> ResponsibilityDischarge
```

## Closed cognitive loop

The canonical closed cognitive loop preserves explicit intermediate responsibility positions:

```text
open cognition
    -> CognitiveClosure
    -> WorkProposal
    -> admission / commitment / authorization
    -> Work / Run / external effect
    -> verification / Outcome
    -> RevisionAssessment
    -> later retry / revise / reopen / wait / close decision
```

No arrow grants permission to skip the intermediate owner. In particular, a deep reopen cannot directly mint a replacement Work; it must return through explicit controller reopen, a new closure, and the normal WorkProposal/admission chain.

## Formal and research evidence

A formal theorem, checker result, historical repository, or research correspondence may provide evidence for an RSC entry. Such evidence does not own the product contract and cannot redefine its runtime meaning. If formal evidence and this contract differ, the difference remains explicit until this contract is deliberately versioned.

## Change rule

Any change that collapses two responsibility objects above, expands authority, or converts an observation into a mutation entitlement is a semantic change and requires a versioned contract update plus conformance vectors/tests.
