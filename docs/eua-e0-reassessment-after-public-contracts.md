# EUA-E0 reassessment after public-contract extraction

Status: **CLOSED / NOT OPENED**
Date: 2026-08-26

## Question

Did cross-language contract extraction expose a responsibility gap between durable Historical Experience Use and a later responsibility Decision that cannot be represented without a new responsibility object?

## Observed public handoff

The extracted public contract preserves:

```text
ExperienceUseAdmission
        |
        v
task/domain Assertion
        |
        v
HistoricalExperienceUse
        |
       STOP
```

The historical-use fact records exact reliance semantics for an exact judgment identity. It does not create a Decision, AuthorizationGrant, GovernanceUseRequirement, InvocationPermit, provider dispatch, Action or confirmed Outcome.

The TypeScript workflow helper keeps `evaluateExperience`, domain judgment construction and `bindHistoricalUse` as separate steps. Execution remains on a separate runtime authorization path. Public views are non-authoritative and cannot be fed back to mint authority.

## Counterexample search

No extracted consumer is forced to perform any of these shortcuts:

```text
HistoricalExperienceUse -> implicit Decision
HistoricalExperienceUse -> implicit Authorization
HistoricalExperienceUse -> implicit InvocationPermit
ExperienceUseAdmission -> implicit execution authority
```

No concrete cross-language counterexample currently requires an additional responsibility object between historical reliance and a later domain/governance decision.

## Verdict

```text
EUA-E0 status = CLOSED / NOT OPENED
reason = contract extraction produced no concrete counterexample requiring a new responsibility object
```

Do not implement EUA-E0 speculatively.

## Reopen trigger

Reopen EUA-E0 only when a concrete cross-language workflow cannot preserve the judgment-to-responsibility handoff without silently collapsing judgment, decision, authorization, invocation permission, action, or verification into another responsibility object.
