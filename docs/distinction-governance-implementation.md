# Distinction governance implementation contract

`portable-runtime` operationalizes the distinction-governance semantics owned by `xiongweilin/ratio/责任拓扑`. It does not redefine that framework and it does not keep local canonical copies of Framework documents.

## Pinned semantic sources

Machine-readable source metadata lives in `semantic-sources.toml`.

- Framework: `1.0.0`
- Source repository: `xiongweilin/ratio`
- Contract: `distinction-governance-1.0`
- Executable baseline commit: `ef9e490987ed47ebef3ac455851109304f24a97c`
- Adopted canonical semantic revision: `10b6f8d4de6f4e4a247a30ebd915136532cfd4f6`
- State-space spec revision: `distinction-state-space-1.3.0`
- Runtime-semantics spec revision: `distinction-runtime-semantics-1.5.1`
- Semantic-convergence spec: `distinction-semantic-convergence-1.0.0`

The executable baseline remains pinned to `ef9e490...` because the adopted `10b6f8d4...` revision explicitly preserves the `distinction-governance-1.0` state invariants and transition-admissibility behavior. The later commit is the authoritative compatibility/ownership clarification, not a hidden executable-contract upgrade.

Runtime code and tests MUST target the explicit pins rather than implicitly following upstream `main`.

## Ownership boundary

The upstream framework owns distinction-governance meaning, state identity, admissibility, transition semantics, responsibility edges, freshness requirements, decision/application identity, provenance requirements, review-discharge semantics, version-axis interpretation, epistemic-basis ownership, and adopted-partition assignment semantics.

`portable-runtime` owns provider-neutral operationalization: internal types, transition kernel, persistence mapping, transactions, projections, runtime integration, protocol exposure, and conformance fixtures. Runtime implementation choices MUST NOT silently weaken or reinterpret the pinned semantic contract.

The following local files are intentionally absent and MUST NOT be recreated as canonical mirrors:

```text
docs/responsibility-record-plane.md
docs/action-responsibility-practice.md
```

Their canonical definitions live only in `xiongweilin/ratio/责任拓扑`.

## Existing assignment use

The historical runtime name `resolve_allowed` is retained for compatibility. Its semantic name is `existing_assignment_use_allowed` and it means:

```text
may rely on an assignment already registered in the adopted partition
```

It does not mean:

```text
classify reality
mutate partition membership
assert ontic truth
```

`src/portable_runtime/governance/assignment.py` exposes the semantic compatibility alias without changing the serialized `resolve_assignment` capability/token.

## Semantic ingress

The runtime kernel validates admissibility against canonical event history, freshness anchors, authority, and evidence/observability inputs. It does not prove that an external source is true merely because the source is accepted by an adapter.

Positive qualification or governed application remains fail-closed when identity, provenance, freshness, authority, or required source material is missing or ambiguous.

## Breaking upstream changes

Treat an upstream change as breaking for this implementation when it changes any of the following without preserving the pinned behavior:

- the contract version or meaning of the distinction state axes;
- state or transition admissibility;
- `Q / Decision / Application` identity, linkage, or frame conditions;
- event-instance replay semantics;
- decision authority, input matching, freshness, or immutable identity;
- application pre/post provenance or atomic-commit requirements;
- review closure/discharge requirements;
- qualification/activation/scope/partition usability semantics;
- adopted-partition assignment becomes a first-class classification/mutation lifecycle;
- the owner boundary between framework semantics and runtime operationalization.

Editorial clarification, owner correction, version-axis clarification, compatibility aliases, or new counterexamples already rejected by the pinned contract are non-breaking.

## Upgrade rule

A newer upstream commit is not adopted merely because it is on `main`. Upgrade by changing explicit source metadata, porting corresponding counterexamples, and passing runtime conformance before persistence or public-protocol changes are made. If legal state/transition behavior changes, increment the compatibility contract rather than silently moving the executable baseline.
