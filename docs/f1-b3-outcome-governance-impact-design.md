# F1-B3 Outcome Governance Impact Design Freeze

## Baseline and scope

F1-B2 semantic baseline: `448e121dcfd9b92de3e85ba2266e23bf0793f6cd`.

This design branch starts from the clean F1-B2 implementation head `19e4a73b4e421c73ce8cdcd80df7c8979fd7495b`, whose only delta from the semantic baseline is removal of the temporary P6 workbench.

F1-B3 answers exactly one question:

```text
confirmed Outcome
    ↓
explicit applicability / dependency
    ↓
OutcomeImpactJudgment
    ↓
RevalidationDisposition
    ↓
ReviewObligation
```

It does not authorize qualification application, review discharge, terminal completion, or recovery closure.

## Frozen non-equivalences

```text
confirmed Outcome
    != governance impact judgment
    != revalidation disposition
    != qualification decision
    != qualification application
```

In particular:

```text
objective_result = pass
    != qualification remains valid

objective_result = fail
    != automatic disqualification
    != automatic reopen
```

Objective verification and governance consequence are separate responsibilities.

## Canonical trigger

F1-B2 emits two deterministic authority events for one verification closure:

```text
ObjectiveVerificationAccepted
OutcomeConfirmed
```

F1-B3 freezes exactly one governance-impact trigger:

```text
OutcomeConfirmed
    = governance-impact EventInstance trigger

ObjectiveVerificationAccepted
    = supporting authority provenance
    != independent governance trigger
```

The processed EventInstance identity must therefore be the exact `OutcomeConfirmed` event identity. Replaying the same event may not open duplicate review obligations. A new verification closure that produces a new confirmed Outcome / `OutcomeConfirmed` identity is a new governance event and must not be collapsed into an old replay.

## Explicit applicability responsibility

An Outcome is not globally relevant merely because its Action belongs to some Work or Run. Governance impact requires an explicit dependency/applicability fact binding at least:

```text
confirmed Outcome
exact Action
exact governed scheme / basis relation
compatible context
compatible governed scope
compatible subject/version anchors
```

The applicability resolver must not infer an affected distinction scheme from `work_id`, `run_id`, Action ownership, provider identity, or objective result alone.

Mismatch or incomplete binding is not `no-governance-impact`. It is an unavailable/failed applicability judgment and must fail closed for any caller that requires a governance-impact conclusion.

## OutcomeImpactJudgment

F1-B3 introduces a responsibility object conceptually named `OutcomeImpactJudgment`. It answers only:

> What governance meaning does this exact verified Outcome have for this exact governed target, context, scope, and version?

Minimum frozen vocabulary:

```text
no-governance-impact
recovery-only
revalidation-required
qualification-challenged
unknown
```

The judgment does not mutate distinction state and does not itself open or discharge a review obligation.

`unknown` or judgment unavailability is not equivalent to `no-governance-impact`.

## RevalidationDisposition remains separate

Existing revalidation code already separates structural dependency impact, risk interpretation, and governance disposition. F1-B3 preserves that separation.

Outcome is not a new alias for any existing `ChangeType`. In particular, do not coerce an Outcome into:

```text
state_space
environment
model
code
or any other existing dependency-change type
```

A policy/profile may explicitly map an `OutcomeImpactJudgment` to the existing disposition vocabulary:

```text
none
warn
background-revalidate
block-next-use
require-human-review
reopen
```

The mapping is policy responsibility, not a property of `objective_result`.

Suggested default policy shape is deliberately non-authoritative and remains configurable; F1-B3 does not freeze a global `pass -> ...` or `fail -> ...` rule.

## Review projection and authority boundary

For dispositions that require review, F1-B3 should reuse the existing distinction-governance lifecycle rather than create a second qualification workflow:

```text
OutcomeConfirmed
        ↓
explicit applicability
        ↓
OutcomeImpactJudgment
        ↓
RevalidationDisposition
        ↓
ReviewObligation
        ── authority boundary ──
GovernanceDecision
        ↓
GovernedApplication
        ↓
qualification / activation effect
        or review discharge
```

Existing objects and operations remain authoritative after the boundary:

```text
ReviewObligation
GovernanceDecision
GovernedApplication
DECIDE_REVIEW
DECIDE_QUALIFICATION
APPLY_REVIEW_DISCHARGE
APPLY_QUALIFICATION
```

A disposition such as `reopen` may justify projection of a review obligation and closure requirements, but it is not reopen authority and may not directly mutate qualification or activation.

Likewise:

```text
verified Outcome(pass)
    != discharge an existing ReviewObligation

verified Outcome(fail)
    != satisfy an existing ReviewObligation closure requirement
```

Review discharge still requires its own GovernanceDecision and GovernedApplication under the existing authority/freshness rules.

## Qualification-axis non-substitution

Record-level epistemic state and distinction-level qualification remain separate axes:

```text
Assertion.epistemic_status
    != DistinctionState.qualification
```

`records.qualification_transition` changes Assertion epistemic status and explicitly states that its audit event grants no mutation authority. F1-B3 must not use that helper as a shortcut for distinction-governance qualification changes.

## Counterexample freeze

The required design conformance set is:

1. `B3-001` confirmed pass + no explicit dependency → no Q and no qualification mutation.
2. `B3-002` confirmed fail + no explicit dependency → no automatic disqualification or reopen.
3. `B3-003` explicit dependency with mismatched context/scope/version → no guessed applicability; fail closed.
4. `B3-004` impact `recovery-only` or `no-governance-impact` → no ReviewObligation.
5. `B3-005` impact mapped to `block-next-use | require-human-review | reopen` → may open Q, but distinction state itself remains unchanged.
6. `B3-006` `RevalidationDisposition(action="reopen")` is not reopen authority and cannot directly mutate state.
7. `B3-007` confirmed pass does not discharge an existing ReviewObligation.
8. `B3-008` confirmed fail does not satisfy existing Q closure requirements.
9. `B3-009` replay of the same `OutcomeConfirmed` EventInstance is idempotent and does not duplicate Q.
10. `B3-010` a new verification closure with a new confirmed Outcome / event identity is a new governance event, not old replay.
11. `B3-011` explicit dependency + unavailable impact judgment → unavailable is not no-impact.
12. `B3-012` F1-B3 does not change CompletionAuthority and does not gain recovery-closure authority.

At the design-freeze commit, 001/002/006/007/008/012 were already required non-substitution locks and 003/004/005/009/010/011 were strict xfails. B3-P1 through B3-P3 have now graduated all B3-001 through B3-012, plus B3-A01, into required conformance without adding qualification, review-discharge, terminal, or recovery authority.

## Production graduation after this freeze

The authorized implementation sequence completed as:

```text
B3-P1a authoritative OutcomeConfirmed trigger replay
B3-P1b explicit applicability
B3-P2a pure OutcomeImpactJudgment
B3-P2b durable store-owned judgment/disposition commit
B3-P3  projection into existing ReviewObligation lifecycle
```

P1-P3 deliberately stop at `ReviewObligation`. They do not include qualification application. Whether an additional B3-P4 connection to existing `DECIDE_QUALIFICATION / APPLY_QUALIFICATION` is necessary remains an independent future decision and is not implied by this graduation.

## Explicit non-goals

This design freeze does not modify or redefine:

- F1-B2 verified Outcome authority;
- `CompletionAuthority`;
- distinction decision/application authority;
- ReviewObligation discharge;
- qualification or activation mutation;
- recovery/reconciliation closure;
- provider or transport protocols.

F1-B3 production must preserve the F1-B2 semantic baseline rather than reinterpret a confirmed Outcome as downstream governance authority.