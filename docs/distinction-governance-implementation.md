# Distinction governance implementation contract

`portable-runtime` operationalizes the distinction-governance semantics owned by `xiongweilin/ratio/责任拓扑`. It does not redefine that framework.

## Pinned semantic baseline

- Contract: `distinction-governance-1.0`
- Source repository: `xiongweilin/ratio`
- Source commit: `ef9e490987ed47ebef3ac455851109304f24a97c`
- Canonical semantic owners: `责任拓扑/区分治理状态空间.md` and `责任拓扑/区分治理运行语义.md`

Runtime code and tests MUST target this pin rather than implicitly following the upstream `main` branch.

## Ownership boundary

The upstream framework owns distinction-governance state identity, admissibility, transition semantics, responsibility edges, freshness requirements, decision/application identity, provenance requirements, and review-discharge semantics.

`portable-runtime` owns their provider-neutral operationalization: internal types, transition kernel, persistence mapping, transactions, projections, runtime integration, protocol exposure, and conformance fixtures. Runtime implementation choices MUST NOT silently weaken or reinterpret the pinned semantic contract.

## Breaking upstream changes

Treat an upstream change as breaking for this implementation when it changes any of the following without preserving the pinned behavior:

- the contract version or meaning of the distinction state axes;
- state or transition admissibility;
- `Q / Dec / App` identity, linkage, or frame conditions;
- event-instance replay semantics;
- decision authority, input matching, freshness, or immutable identity;
- application pre/post provenance or atomic-commit requirements;
- review closure/discharge requirements;
- qualification/activation/scope/partition usability semantics;
- the owner boundary between framework semantics and runtime operationalization.

Editorial clarification, additional examples, or new counterexamples that are already rejected by the pinned contract are non-breaking.

## Upgrade rule

A newer upstream commit is not adopted merely because it is on `main`. Upgrade by changing the pinned contract/version/commit in an explicit runtime change, porting the corresponding counterexamples, and passing the runtime conformance suite before persistence or public-protocol changes are made.
