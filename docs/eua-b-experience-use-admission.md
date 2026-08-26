# EUA-B — Read-only ExperienceUseAdmission

Base: `main@2ae76b047bb6014ef6f6b1c5b1172d2158029ecc`.

This slice implements only current experience-use eligibility. It creates no durable historical use authority and changes no Responsibility Runtime authority.

## Production topology

```text
ExperienceUseRequirement
    projection_refs
    use_scope
    subject_version_refs
    environment_bindings
    use_context
        ↓
StateStore.export_state() exactly once
        ↓
store-owned current KnowledgeProjection graph resolution
        ↓
ExperienceUseAdmission
    status
    requirement_digest
    snapshot_digest
    ResolvedExperienceUseSnapshot
        ↓
STOP
```

`ResolvedExperienceUseSnapshot` is an immutable evaluator value. It is deliberately not the durable `ExperienceUseSnapshot`/historical-use authority whose placement EUA-C must decide.

## Status semantics

```text
not-applicable
allowed
blocked
stale
unavailable
```

`allowed` means only that the selected canonical experience is currently usable for this exact requirement. It is not proof that a proposition is universally true, is not Responsibility authorization, and is not permission to execute.

`unavailable` includes unresolved/invalid canonical graph facts or non-official candidate input.

`stale` includes lifecycle deprecation, subject-version/environment drift, stale epistemic/evidence state, or canonical `requires-revalidation` facts.

`blocked` includes explicit canonical counterexample/negative-knowledge refs or canonical contradiction facts.

`not-applicable` covers no selected projection or scope mismatch.

## Authority and provenance boundaries

Caller input does not contain assertion, evidence, epistemic-judgment, counterexample, negative-knowledge, promotion-authorization, derivation, or relation refs. Those are reconstructed from the canonical projection graph.

The evaluator consumes one coherent store export and performs no writes. It adds no store commit API and no authority event.

A historical `knowledge.promote` authorization remains projection provenance. EUA-B does not reinterpret that grant as current experience-use authorization or as authority to act.

```text
knowledge promotion authorization
!= experience-use admission
!= responsibility authorization
!= execution permission
```

Generic qualification vocabulary is not extended with `KnowledgeProjection` refs in this slice. Experience use remains an independent responsibility domain with explicit `requirement_digest` and `snapshot_digest`.

## Digest semantics

`requirement_digest` binds the normalized concrete use requirement.

`snapshot_digest` binds the actual current semantic state checked, including:

- exact selected KnowledgeProjection eligibility fields,
- exact assertion/evidence/epistemic-judgment/scope-version/promotion-provenance objects,
- exact counterexample and negative-knowledge objects,
- relevant derivations and canonical relations,
- use scope, subject versions, environment bindings and use context,
- unresolved refs when present.

`created_at`/`updated_at` are excluded as serialization noise; semantic fields are retained.

Same projection id with changed underlying semantics therefore changes the snapshot digest. A previously returned `ResolvedExperienceUseSnapshot` remains immutable and does not track later store mutations.

## Counterexample graduation

EUA-001..010 graduate against the real evaluator:

```text
official != usable in this scope
retrieval hit != usable experience
evidence exists != usable experience
promotion authorization != action authority
allowed != permission to execute
scope match != environment/version match
same projection id != same semantic snapshot
caller omission != canonical counterexample omission
requires-revalidation != usable
deprecated/archived != usable
```

## Capability ceiling

```text
ExperienceQualification
= NOT REQUIRED BY CURRENT EVIDENCE

ExperienceUseAdmission
= SUPPORTED / READ-ONLY

ResolvedExperienceUseSnapshot
= SUPPORTED / EPHEMERAL IMMUTABLE VALUE

durable historical Experience Use authority
= NOT SUPPORTED / EUA-C DECIDES PLACEMENT

DomainJudgment new record type
= NOT DECIDED

InvocationPermit / dispatch integration
= CLOSED

Outcome -> ExperienceImpact
= CLOSED

P5 Experience authority import
= CLOSED / NOT APPLICABLE
```

STOP after this production merge. The next independent slice is EUA-C, an audit of historical use binding and Domain Judgment semantics.