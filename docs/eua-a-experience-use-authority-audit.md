# EUA-A — Experience Use Authority audit

Base: `main@cae050a71574821366f7b2ffe4e28d4bb3a9f3d2`.

This slice is audit-only. It changes no production source and authorizes no Experience Governance production.

## Question

The question is not whether the runtime needs another knowledge-qualification record. The question is:

> Given canonical experience truth, what authority proves that one concrete judgment may rely on that experience in this exact scope, subject-version and environment now?

## Current-state findings

`KnowledgeProjection` is already the canonical experience/knowledge projection surface. It carries current assertion refs, evidence summary refs, epistemic judgment refs, authorization refs, scope-version refs, validity scope, environment bindings, counterexample refs, negative-knowledge refs, reopen conditions and lifecycle state.

Legacy `KnowledgeItem` is a compatibility projection only. It cannot mint official knowledge authority; promotion is fail-closed and must go through canonical `KnowledgeProjection` handling.

The surface `promote_to_official()` helper performs local prerequisite checks, but durable state-graph validation goes further: official projection refs are resolved as typed local objects; promotion authorization is structurally checked; epistemic-judgment refs must resolve to supported epistemic judgments rather than approval assertions; and the assertion/judgment/derivation/evidence/scope graph is checked for structural binding.

The existing qualification resolver provides the relevant engineering pattern for a later experience-use evaluator: the request boundary carries refs, the store resolves authoritative facts, the resolver freezes a deeply immutable snapshot and a digest binds the facts actually checked. Its current reference vocabulary does not treat `KnowledgeProjection` as a first-class qualification source.

## Verdicts

```text
ExperienceQualification
= NOT REQUIRED BY CURRENT EVIDENCE

ExperienceUseAdmission
= JUSTIFIED

immutable experience-use snapshot semantics
= JUSTIFIED

durable placement of that snapshot
= NOT YET DECIDED
```

The last verdict is deliberate. A read-only evaluator snapshot is not yet a historical use fact. Persisting every allowed evaluation before a concrete judgment consumes it would record evaluator activity rather than responsibility history.

## Minimal topology frozen by this audit

```text
canonical KnowledgeProjection graph
        ↓
ExperienceUseRequirement
        ↓
store-owned current graph resolution
        ↓
ExperienceUseAdmission
        ↓
immutable resolved experience-use snapshot
        ↓
STOP
```

No durable `ExperienceUseSnapshot` object is authorized by EUA-A. No `DomainJudgment` object is authorized. No permit/dispatch integration is authorized.

## Counterexamples

EUA-001

```text
official projection
!= usable in this concrete context
```

EUA-002

```text
retrieval hit
!= qualified experience use
```

EUA-003

```text
evidence exists
!= usable experience
```

EUA-004

```text
knowledge promotion authorization
!= experience-use authorization
!= responsibility authorization
```

EUA-005

```text
experience-use eligibility
!= permission to execute
```

EUA-006

```text
scope match
!= environment/version match
```

EUA-007

```text
projection identity
!= immutable currently usable semantic state
```

EUA-008

```text
absence of a counterexample in caller/retrieval input
!= absence of canonical counterexample or negative knowledge
```

EUA-009

```text
open revalidation/reopen blocker
!= still usable
```

EUA-010

```text
deprecated or archived projection
!= usable experience
```

The audit also preserves these long-lived separations:

```text
historical ExperienceUseSnapshot
!= current KnowledgeProjection state

well-qualified domain judgment
!= responsibility authorization

OutcomeConfirmed
!= automatic experience invalidation
```

The last relation is only a boundary note for a future EUA-F audit. This slice defines no Experience Impact API or production model.

## Durable placement remains open

EUA-A intentionally does not decide where a future historical use binding belongs. The next historical-use audit must compare at least:

```text
A. atomic ExperienceUseSnapshot + exact judgment binding
B. snapshot embedded/bound inside judgment authority
C. standalone durable snapshot optionally linked later
```

The design preference is not a production decision. A durable historical fact should ultimately answer what an actual judgment relied on, not merely what an evaluator once found eligible.

## Capability ceiling after this audit

```text
canonical KnowledgeProjection qualification truth
= EXISTING / SUPPORTED

ExperienceQualification
= NOT REQUIRED BY CURRENT EVIDENCE

ExperienceUseAdmission architecture
= JUSTIFIED / NOT IMPLEMENTED

immutable experience-use snapshot semantics
= JUSTIFIED / NOT DURABLE

durable historical experience-use authority
= UNDECIDED

Domain Judgment binding
= NOT AUDITED

Responsibility / Permit / dispatch integration
= CLOSED

Outcome -> Experience Impact
= CLOSED
```

STOP after this audit merge. EUA-B must be an independent read-only production slice from the new exact main.