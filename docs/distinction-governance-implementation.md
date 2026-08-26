# Distinction governance implementation mapping

Canonical semantic contract:

```text
contracts/semantics/governance/distinction-governance-v1.md
```

This document describes how the Python reference implementation realizes that contract. It is implementation documentation and owns no independent semantics. If this document or Python behavior conflicts with `contracts/`, the canonical contract wins.

## Canonical contract identity

- contract id: `distinction-governance`
- contract version: `distinction-governance-1.0`
- canonical owner: `portable-runtime/contracts`
- Python representation: `src/portable_runtime/governance/distinction.py`

No repository name, external commit SHA, or upstream branch is part of current runtime compatibility identity.

## Implementation correspondence

The Python module represents the contract's qualification, activation, scope and partition axes through `DistinctionState`. Operational sequencing metadata such as `version` and `operational_anchor` is implementation state used to prevent stale applications; it is not a fifth distinction-semantic axis.

`GovernanceDecision`, `GovernedApplication`, `ReviewObligation`, structured authority targets and freshness anchors implement explicit responsibility positions. Application remains separate from real-world action, and review opening remains separate from review discharge.

The runtime representation MUST preserve the canonical invariants and negative paths defined by the contract and conformance suite. Python is the reference execution oracle, not a second definition owner.

## Compatibility aliases

The historical runtime name `resolve_allowed` is retained for compatibility. Its semantic alias is `existing_assignment_use_allowed`, meaning:

```text
may rely on an assignment already registered in the adopted partition
```

It does not mean:

```text
classify reality
mutate partition membership
assert ontic truth
```

`src/portable_runtime/governance/assignment.py` exposes the alias without changing the serialized `resolve_assignment` capability/token.

## Semantic ingress

The runtime validates admissibility against local canonical state, event history, freshness anchors, authority and evidence/observability inputs. It does not prove that an external source is true merely because an adapter accepted it.

Positive qualification or governed application remains fail-closed when identity, provenance, freshness, authority, or required source material is missing or ambiguous.

## Breaking contract changes

A change is breaking when it changes any of the following without a versioned contract update:

- the meaning of distinction state axes;
- legal state or transition admissibility;
- `ReviewObligation / GovernanceDecision / GovernedApplication` identity, linkage or frame conditions;
- event-instance replay behavior;
- authority, input matching, freshness, or immutable identity requirements;
- application pre/post provenance or atomic-commit requirements;
- review closure/discharge requirements;
- qualification/activation/scope/partition usability semantics;
- existing-assignment use into classification or mutation semantics;
- the canonical ownership boundary in `contracts/`.

Editorial clarification that preserves all accepted and rejected conformance behavior is non-breaking.

## Contract upgrade rule

Upgrade by changing the versioned artifact under `contracts/`, updating catalog/schema/vector identities as applicable, porting counterexamples, and passing conformance before runtime behavior or public protocol changes land. Runtime code MUST NOT dynamically read external documents or commit metadata to decide legal behavior.
