# EUA-D — Durable Historical Experience Use production closure

Status: **SUPPORTED locally after the exact-head production gate described below.**

This closure is scoped only to EUA-D. It does not open EUA-E0 or any downstream responsibility, authorization, permit, dispatch, execution, outcome, or impact authority.

## Formal base and responsibility

EUA-D was opened from the exact EUA-C production gate:

```text
main@7b1966559316fd0c8c65eb85a22a7cb6edb2f380
```

EUA-C froze that an existing canonical `Assertion` is sufficient as the task/domain judgment carrier and that a dedicated historical Experience Use binding responsibility is justified. EUA-D implements only that durable responsibility:

```text
current KnowledgeProjection truth
→ ExperienceUseAdmission
→ exact task/domain Assertion J
→ durable Historical Experience Use
→ STOP
```

The durable authority form is one typed event-backed fact:

```text
HistoricalExperienceUseRecorded
subject_ref = exact J.id
```

with typed reconstruction through `HistoricalExperienceUse`. A raw `Event` is not the public domain model.

No `DomainJudgment` class is introduced or required.

## Store-owned semantic compare-and-bind

A caller may submit only an exact judgment, an exact `ExperienceUseRequirement`, and compare expectations. It may not submit a resolved snapshot, historical binding, independently selected assertion/evidence/counterexample refs, or a caller-built authority event.

The first durable commit linearizes under the store's existing transaction/writer boundary:

```text
validate exact J
→ validate ordinary canonical Assertion write semantics
→ re-evaluate exact R using EUA-B
→ require status == allowed
→ require current requirement digest == expected digest
→ require current snapshot digest == expected digest
→ require current admission contract == current EUA-B contract
→ derive HistoricalExperienceUseRecorded from the store-owned result
→ atomically persist J + historical-use event
→ validate the resulting authority graph
→ commit
→ STOP
```

Memory uses its rollback-capable transaction and SQLite uses the writer-serialized transaction. A failure after either member of the pair has been tentatively written rolls back the pair.

This is a semantic compare-and-bind, not persistence of a caller-computed admission result:

```text
caller previously observed allowed S
!=
store may persist S as historical authority
```

The store must prove that the exact semantic state is still current at the linearization point.

## Exact identity and replay

Historical Experience Use identity is the exact judgment identity:

```text
(judgment_ref, judgment_version)
```

The event id is deterministically derived from that semantic role and exact judgment identity. The durable payload binds:

```text
judgment_ref
judgment_version
requirement_digest
snapshot_digest
snapshot_semantic_json
selected_projection_refs
admission_contract_version
```

Replay rules are intentionally asymmetric between first commit and historical replay:

```text
new J + no historical binding
→ current EUA-B requalification is mandatory

existing exact historical binding
→ reconstruct immutable historical payload
→ do not requalify against current KnowledgeProjection state
```

Therefore later projection, evidence, relation, or revalidation drift does not mutate or invalidate the historical provenance fact. Same exact J with the same historical semantics replays one identity. Same exact J with changed requirement, snapshot, projection selection, judgment semantics, or explicitly conflicting contract expectation fails closed as rebound.

An already-persisted unbound J cannot later acquire Historical Experience Use through current-state lookup:

```text
existing J + no historical binding
→ retroactive backfill rejected
```

## Single-owner Experience Use digest contract

EUA-B owns the canonical representation and digest responsibility through public contracts:

```text
EXPERIENCE_USE_REQUIREMENT_SCHEMA
RESOLVED_EXPERIENCE_USE_SNAPSHOT_SCHEMA
CURRENT_EXPERIENCE_USE_ADMISSION_CONTRACT

experience_use_requirement_digest(...)
experience_use_snapshot_digest(...)
```

EUA-D consumes these contracts and does not define an independent requirement/snapshot canonicalizer. Requirement digest semantics therefore remain exactly the EUA-B canonical semantics, including canonical key ordering, separators, Unicode escaping, thawing, and noise removal.

The production conformance suite exercises the full non-ASCII chain:

```text
R(use_context={"语言": "中文", "地点": "東京"})
→ EUA-B requirement_digest
→ EUA-D commit
→ HistoricalExperienceUseRecorded reconstruction
→ replay
```

and requires the same exact digest throughout.

The Historical Experience Use event identity hash remains a separate identity responsibility; it is not a second implementation of the EUA-B requirement or snapshot digest.

## Current admission contract vs historical support

Current-use evaluation and historical reconstruction have distinct version responsibilities:

```text
CURRENT_EXPERIENCE_USE_ADMISSION_CONTRACT
= contract required for every new EUA-D commit

SUPPORTED_HISTORICAL_EXPERIENCE_USE_CONTRACTS
= contracts whose already-durable historical facts can be reconstructed
```

For v1 both contain `experience-use-admission-v1`, but historical reconstruction does not require an event-declared contract to equal the current evaluator contract. This preserves old historical responsibility when a future evaluator becomes current:

```text
current = v2
supported historical = {v1, v2}
```

An unsupported historical contract remains fail-closed.

## Responsibility-role separation

The consuming task/domain judgment remains an ordinary canonical `Assertion` carrying the semantic role:

```text
metadata.semantic_role = "task-domain-judgment"
```

For a new binding it may not be one of the selected projection's `current_assertion_refs` or `epistemic_judgment_refs`. This prevents the assertion/judgment that qualifies experience from collapsing into the judgment that consumes experience.

Experience eligibility does not decide the judgment's truth:

```text
ExperienceUseAdmission == allowed
!= J.epistemic_status == supported
```

A contested or otherwise valid task/domain Assertion retains its own epistemic status when historical reliance is recorded.

## Exact projection set and judgment revision

`ExperienceUseRequirement` canonicalizes its exact selected projection set. The historical payload must preserve the same canonical exact set; input ordering cannot create a new historical semantic identity or rebound.

Judgment revisions remain distinct responsibility nodes. A canonical Revision uses distinct old/new record identities:

```text
J1 → HistoricalExperienceUse(J1)
J2 → HistoricalExperienceUse(J2)
Revision(revises=J1, produces=J2)
```

Both historical facts remain independently reconstructible. A revision does not rewrite the old historical reliance fact.

## Atomicity, replay, and authority fences

The EUA-D production conformance suite closes the following classes of counterexample on both Memory and SQLite where applicable:

```text
new J + exact allowed S
→ atomic success

same exact J + same S
→ replay

same exact J + different S
→ rebound

existing J + no historical binding
→ no retroactive backfill

historical binding + missing J
→ invalid authority graph

later projection/revalidation drift
→ historical binding unchanged

caller evaluation + state drift before commit
→ compare mismatch/fail closed
→ J and binding absent

fault after J write / before event completion
→ rollback both

fault after event write / before transaction completion
→ rollback both

two concurrent same-J commits
→ one semantic result linearizes

direct HistoricalExperienceUseRecorded append
→ closed

Memory/SQLite generic state import
→ closed

bundle/P5 authority import
→ closed through the state-import authority fence
```

HUB-001 through HUB-008 are therefore graduated by production conformance, not merely by audit labels. The required strict CI job includes `tests/conformance/test_historical_experience_use.py` directly.

## Capability ceiling

EUA-D proves only historical reliance responsibility:

```text
J is an exact valid task/domain Assertion
+
J actually used exact historical Experience Use semantics S
```

It does not prove:

```text
S allowed → J true
Historical Experience Use → Responsibility Decision
Historical Experience Use → Authorization
Historical Experience Use → InvocationPermit
Historical Experience Use → dispatch
Historical Experience Use → provider execution
Historical Experience Use → Outcome
Historical Experience Use → ExperienceImpact
```

EUA-D creates no Decision, Authorization, InvocationPermit, dispatch, provider invocation/retry, Outcome, ExperienceImpact, recovery, or fresh invocation authority.

## Closed boundaries after EUA-D

After this production slice:

```text
EUA-D durable Historical Experience Use
= SUPPORTED locally

DomainJudgment
= NOT REQUIRED

historical backfill/import
= CLOSED / UNSUPPORTED

direct authority event append
= CLOSED

EUA-E0 judgment → responsibility consumption
= CLOSED

EUA-E1 Decision / authorization binding
= CLOSED

EUA-E2 Permit + final experience freshness binding
= CLOSED

EUA-F Outcome → ExperienceImpact
= CLOSED
```

No downstream authority is implicitly opened by this closure.

## Release gate

This document is the final semantic change in the EUA-D branch. The commit containing it becomes the candidate freeze head only after the branch diff remains scoped as above. That exact head must then pass:

```text
Ruff
Mypy
full pytest
strict-conformance
```

with the Historical Experience Use production suite present in strict-conformance, HUB-001…008 exercising production semantics, and zero XPASS. Only that exact head may be used as the PR head. Merge requires the protected merge-context checks, synthetic merge tree equality, expected-head merge, and verification of the resulting `main` tree and parents.

After merge: **STOP. EUA-E0 remains closed pending separate explicit authorization.**
