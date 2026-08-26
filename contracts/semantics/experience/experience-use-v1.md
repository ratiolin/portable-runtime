# Experience Use contracts — v1

Status: stable
Canonical owner: `portable-runtime/contracts`

This slice defines current-use admission and historical reliance without granting execution authority.

## Contract identities

- `experience-use-requirement-v1`
- `experience-use-admission-v1`
- `resolved-experience-use-snapshot-v1`
- `historical-experience-use-v1`
- `historical-experience-use-commit-v1`

## ExperienceUseRequirement

A public input identifies selected knowledge projection references plus use scope, subject-version references, environment bindings and arbitrary JSON use context. Projection-reference ordering is canonicalized before digesting.

The v1 requirement digest is SHA-256 over canonical JSON with:

```text
keys sorted
separators=(",", ":")
ensure_ascii=true
```

This canonicalization is contract-specific and MUST NOT be silently replaced by another runtime digest convention.

## ExperienceUseAdmission

Admission status is one of:

```text
not-applicable
allowed
blocked
stale
unavailable
```

An allowed admission means only that the exact selected experience set is currently admissible for the requested use context under the reference implementation. It does not mean:

- the consuming judgment is epistemically supported;
- a policy allowed execution;
- an AuthorizationGrant exists;
- an InvocationPermit exists;
- a provider may be invoked.

Admission returns requirement and snapshot digests so callers can carry exact semantic identity without locally minting authority.

## HistoricalExperienceUse

Historical use records what exact knowledge snapshot a judgment actually relied on at commit time. Historical reliance is immutable provenance: later knowledge drift does not rewrite the historical binding.

A first commit is compare-and-bind. Exact replay preserves deterministic identity. Reusing the same judgment identity/version with changed reliance semantics is rejected as identity rebound.

Retroactive backfill is closed: a consuming judgment cannot manufacture a self-qualifying experience history after the fact.

## Current vs historical

```text
historical provenance != current qualification
```

A previously valid historical binding may remain true as history even when current use would now be blocked/stale/unavailable. A new use must be evaluated against current state.

## Client authority ceiling

Clients send requirements and expected digests; the Python reference implementation re-evaluates and compares them at commit. Non-Python clients may verify digests only after passing canonicalization vectors, and even correct digest computation grants no semantic or execution authority.