# EUA-C — Historical Experience Use / Judgment Binding audit

Base: `main@d8fd7f280d4c43c7287ea0a13f22346ad9495886`.

Audit-only. Zero production source changes.

## Question

EUA-B now answers:

```text
these exact KnowledgeProjection semantics
are currently admissible
under this exact use context
```

EUA-C asks only the missing historical-responsibility question:

```text
which exact task/domain judgment J
actually relied on
which exact resolved experience semantic state S?
```

This audit does **not** reopen knowledge qualification. Official `KnowledgeProjection` qualification remains the canonical epistemic source; EUA-B remains the current-use evaluator.

## Current-state findings

### Existing Assertion is sufficient as the judgment carrier

The canonical `Assertion` already owns proposition-level epistemic status and inherits scope, source refs, environment versions, version, metadata, limitations, invalidation conditions, and lifecycle. A task/domain judgment can therefore remain an `Assertion` with a validated domain-judgment semantic role.

Current evidence does not justify a new `DomainJudgment` record type.

```text
DomainJudgment new class
= NOT REQUIRED BY CURRENT EVIDENCE
```

This does **not** mean arbitrary Assertion metadata is historical-use authority. A future store-owned commit path must validate the exact judgment role and binding semantics.

### Projection-internal epistemic judgment is a different responsibility

`KnowledgeProjection.epistemic_judgment_refs` proves the projection's own epistemic qualification graph. It does not prove that a later task/domain judgment consumed that projection.

```text
projection-internal epistemic judgment
!= task/domain judgment that relied on experience
```

### Existing Derivation is insufficient as historical-use authority

`Derivation` is inference provenance. It has `premise_refs`, `evidence_refs`, `rule_or_method_refs`, and `conclusion_ref`, but it does not bind EUA-B `requirement_digest`, `snapshot_digest`, or exact resolved experience semantic payload.

More importantly, the generic state-graph `_iter_ref_edges` path does not treat Derivation's premise/evidence/conclusion fields as authoritative local reference edges. The projection validator may use Derivation specially for projection qualification, but generic Derivation persistence is not an exact historical Experience Use authority.

Therefore:

```text
Derivation cites projection/current facts
!= proof of exact EUA-B snapshot reliance
```

### Existing RecordRelation is insufficient

`RelationType` has no dedicated historical reliance relation. Generic `RecordRelation` is append-only once written, which is useful, but neither its type nor metadata is validated as:

```text
exact judgment J
+ exact allowed ExperienceUseAdmission
+ exact requirement digest
+ exact snapshot digest
+ exact resolved semantic payload/context
```

Free-form relation metadata is therefore not sufficient authority.

### Responsibility Decision citation is insufficient

`DecisionRecord.rationale_refs` can cite semantic records, but a Responsibility Decision that cites a projection or judgment does not prove which exact EUA-B snapshot its preceding domain judgment actually consumed.

```text
Decision cites projection
!= historical experience-use proof
```

### There is no current store-owned atomic linearization

Current ordinary record and relation writes are separate semantic operations. There is no store-owned commit surface that atomically linearizes:

```text
exact task/domain judgment J
+
exact Experience Use historical binding to S
```

An independently computed/persisted snapshot followed later by an optional link would record evaluator activity, not necessarily responsibility history.

## Audit verdict

```text
ExperienceQualification
= CLOSED / NOT REOPENED

ExperienceUseAdmission current-use evaluator
= SUPPORTED (EUA-B)

existing Assertion as task/domain judgment carrier
= SUFFICIENT BY CURRENT EVIDENCE

new DomainJudgment record type
= NOT JUSTIFIED

existing Derivation as historical-use authority
= INSUFFICIENT

existing generic RecordRelation as historical-use authority
= INSUFFICIENT

Historical Experience Use binding responsibility
= JUSTIFIED

durable linearization point
= MUST BE store-owned and atomic with the exact judgment responsibility

standalone durable evaluator snapshot followed by optional later judgment link
= REJECTED

production durable placement / implementation class
= NOT AUTHORIZED BY THIS AUDIT
```

## Required future responsibility shape

The future durable fact, regardless of class/event name, must answer:

```text
judgment J
actually relied on
exact experience semantic state S
under exact context C
```

The minimum payload responsibility is:

```text
exact judgment identity
  record id
  exact judgment version

requirement_digest
snapshot_digest
exact resolved semantic payload/context
exact selected projection identities
```

The historical payload must be self-sufficient for replay/audit. It must not depend on looking up the future current state of a `KnowledgeProjection`.

## Candidate identity rule

Treat the exact judgment identity as `(record_id, version)`, not merely the mutable current record id.

Conceptually:

```text
HistoricalExperienceUseKey
= H(
    schema,
    semantic-role=historical-experience-use,
    exact-judgment-identity=(judgment_ref, judgment_version),
  )
```

The payload binds:

```text
requirement_digest
snapshot_digest
exact resolved semantic payload/context
```

Replay semantics:

```text
same exact judgment identity
+ same experience semantics
→ replay

same exact judgment identity
+ changed experience semantics
→ rebound / fail closed

updated experience semantics
→ new or revised judgment responsibility
```

A later projection/revalidation change does not mutate the historical use fact.

## Linearization rule

The strongest safe shape is:

```text
store-owned atomic commit
  exact task/domain Assertion J
  + exact historical Experience Use binding S
```

A judgment already committed without an exact historical-use binding must not be retroactively upgraded by consulting current projection state. If the system needs a new experience basis, it must form a new/revised judgment responsibility and bind that exact basis at its own commit linearization point.

This prevents:

```text
evaluator computed S
→ persisted standalone snapshot
→ maybe later someone links J
```

from being confused with:

```text
J actually relied on S
```

## Frozen counterexamples

HUB-001:

```text
ExperienceUseAdmission(status=allowed)
+ no task/domain judgment
!= historical experience use
```

HUB-002:

```text
same snapshot S
+ judgment J1
!= use by judgment J2
```

HUB-003:

```text
same exact judgment identity
+ different snapshot semantics
→ rebound / fail closed
```

HUB-004:

```text
KnowledgeProjection.epistemic_judgment_refs
!= task/domain judgment that consumed the projection
```

HUB-005:

```text
Responsibility Decision cites projection
!= proof that its preceding judgment relied on exact resolved snapshot
```

HUB-006:

```text
later projection/revalidation drift
!= mutation of historical use fact
```

HUB-007:

```text
standalone durable evaluator snapshot
+ later optional link to judgment
!= atomic historical reliance
```

HUB-008:

```text
current projection state
!= authority to backfill a missing historical-use binding
```

## Hard ceiling

This audit authorizes no production implementation.

Specifically it does not add or authorize:

- a `DomainJudgment` class;
- a `HistoricalExperienceUseBinding` class/event name;
- a durable Experience Use store bucket;
- a store commit method;
- serialized/P5 historical-use import;
- retroactive historical backfill;
- `InvocationPermit` fields;
- Responsibility Runtime integration;
- dispatch freshness integration;
- Outcome-to-ExperienceImpact authority;
- retry/recovery/fresh-invocation authority.

The next production gate, EUA-D, remains CLOSED until explicitly authorized after this audit is merged and stopped.
