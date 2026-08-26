# EUA-B — Experience Use Admission production freeze

## Scope

EUA-B is a read-only current-use authority surface. It answers one question:

> May the exact experience set already selected by the caller be relied on in this exact context now?

It does not retrieve, rank, persist a historical use fact, create a domain judgment, authorize responsibility, issue an InvocationPermit, or authorize execution.

Topology:

```text
upstream retrieval / selection
        ↓
ExperienceUseRequirement
  exact projection_refs
  exact use scope
  exact subject versions
  exact environment
  exact use context
        ↓
StateStore.export_state() exactly once
  AND backend guarantees one coherent point-in-time snapshot
        ↓
store-owned exact KnowledgeProjection graph reconstruction
        ↓
ExperienceUseAdmission
  status
  requirement_digest
  snapshot_digest
  immutable resolved snapshot
        ↓
STOP
```

## Responsibility boundary

`ExperienceUseRequirement.projection_refs` is the exact intended reliance set, not a candidate retrieval set. EUA-B performs no top-k selection, ranking, fallback, substitution, or automatic choice.

Default composition is AND:

```text
P1 allowed + P2 blocked
→ whole requirement blocked
```

If callers can rely on either P1 or P2, the selection must happen before this authority boundary and only the chosen exact set may cross it.

Therefore:

```text
retrieval relevance
!= experience-use admissibility
```

## Five statuses

The vocabulary is intentionally closed to:

```text
not-applicable
allowed
blocked
stale
unavailable
```

Semantics:

```text
not-applicable
= this use declares no experience reliance (`projection_refs` empty)

allowed
= every projection in the exact chosen set is currently admissible

blocked
= authoritative facts resolve and prove the exact chosen set cannot currently be relied on
  examples: scope mismatch, applicable contradiction, non-usable projection lifecycle,
  refuted/contested current assertion

stale
= the semantic basis is structurally known but freshness has drifted
  examples: subject-version drift, environment drift, open requires-revalidation edge

unavailable
= the evaluator cannot obtain enough authoritative facts, or cannot reliably reconstruct
  the required graph/applicability
```

Important distinctions:

```text
missing fact != blocked
resolved contradictory fact != unavailable
snapshot exists != admission allowed
```

Only `status == allowed` is positive current-use authority.

For exact-set composition, a resolved blocker is decisive even if another required projection is unavailable; staleness is also a decisive current freshness failure. Missing facts alone are `unavailable`.

## Negative knowledge and counterexamples

Negative knowledge is part of experience truth and MUST NOT be dropped from the resolved snapshot.

EUA-B explicitly rejects the over-strong rule:

```text
counterexample_refs or negative_knowledge_refs present
→ blocked
```

The frozen rule is:

```text
negative knowledge exists
→ resolve it and retain it in the immutable snapshot

applicable contradiction
+ binds a current projection assertion
+ matches current use scope
+ matches current subject-version context
+ matches current environment
→ blocked

known limitation definitively outside current applicability
→ visible in snapshot
→ does not automatically block

applicability missing or conflicting
→ unavailable / fail closed

negative fact applicable to current context but not bound to a current assertion
→ unavailable / fail closed
```

No applicability is inferred merely because a negative fact is listed by a projection. Current applicability is reconstructed from authoritative scope/version/environment facts on the negative record and/or its contradiction relation. A definitive mismatch in any applicability dimension is sufficient to establish that the limitation is outside this use; otherwise missing/conflicting dimensions stay unknown.

Thus:

```text
negative knowledge != disqualification
applicable contradiction = potential disqualification
omitted or unresolved negative knowledge = invalid resolution
```

## Coherent snapshot requirement

`export_state() exactly once` is necessary but not sufficient. The returned state must itself represent one coherent point-in-time graph.

The production backends satisfy this as follows:

- Memory: `export_state()` holds the store RLock across the complete semantic serialization/copy. A writer cannot cross the snapshot while it is being materialized.
- SQLite: `export_state()` obtains all runtime rows with one `SELECT ... fetchall()` while holding the store lock. SQLite statement-snapshot semantics fix the database view for that SELECT, and all rows are materialized before the lock is released. Later commits may occur while copied rows are parsed, but cannot appear in only part of that export.

EUA-B conformance tests deliberately interleave writers at those seams and require the export to be entirely before or after a commit, never a Q1/Q2/Q3 mixed graph.

This coherence guarantee is what permits `snapshot_digest` to mean "the exact semantic state actually resolved by this admission" rather than merely "values fetched by one Python call".

## Digests and immutable snapshot

`requirement_digest` binds the exact intended reliance request.

`snapshot_digest` binds the semantic facts actually checked, including:

- exact selected projection identities and eligibility fields;
- current assertions;
- evidence;
- projection-internal epistemic judgments;
- promotion authorization provenance;
- scope/version/environment facts;
- counterexamples and negative knowledge;
- relevant derivations and canonical relation facts;
- current revalidation facts;
- unresolved refs when reconstruction fails;
- the concrete use context.

Timestamp/logging noise such as `created_at` / `updated_at` is excluded from semantic digest identity.

The snapshot is deeply immutable from the evaluator's perspective, but it is not durable historical-use authority.

```text
evaluator computed immutable snapshot S
!= a judgment actually relied on S
```

Durable placement remains outside EUA-B.

## Promotion provenance is not action authority

Historical `knowledge.promote` authorization remains canonical projection provenance. EUA-B resolves it as part of the projection graph, but does not reinterpret it as live action authority.

```text
authority to promote knowledge
!= authority to rely on knowledge
!= responsibility authorization
!= permission to execute
```

## Non-authorizations / hard ceilings

EUA-B does not authorize or implement:

- `ExperienceQualification` as a second knowledge truth family;
- durable `ExperienceUseSnapshot` persistence;
- `DomainJudgment` or another new judgment type;
- historical experience-use binding;
- changes to `InvocationPermit`;
- experience fields folded into generic `qualification_digest`;
- Responsibility Runtime integration;
- dispatch freshness integration;
- `Outcome -> ExperienceImpact` authority;
- P5 authority import;
- fresh invocation authority;
- retry/recovery reopening.

The next gate, if opened, is EUA-C audit-only and asks only whether the existing record/relation surface can prove:

```text
this exact task/domain judgment J
actually relied on
this exact resolved experience semantic state S
```

No EUA-C production follows from this freeze.
