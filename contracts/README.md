# Portable Runtime canonical contracts

`contracts/` is the sole canonical semantic and interoperability owner for `portable-runtime`.

No external repository, document set, commit SHA, theorem repository, or research note is required to interpret the runtime's supported product semantics. Historical research may motivate a contract, but it has no normative authority over this repository unless its semantics are explicitly adopted into this directory.

## Ownership

The ownership chain is:

```text
portable-runtime/contracts
    owns canonical product semantics,
    state/transition invariants,
    authority ceilings,
    canonicalization rules,
    public structural contracts,
    and conformance vectors

Python portable_runtime
    is the normative reference implementation / oracle
    for these contracts

packages/typescript
    is a non-authoritative conforming consumer

packages/inspector
    is a non-authoritative read/inspection consumer
```

Runtime implementation code MUST NOT create a second semantic owner. Public clients MUST NOT infer authority that the contracts do not grant.

## Four contract layers

1. **Structural** — schemas, enums, required fields and versioned wire shapes.
2. **Semantic** — identity, replay, freshness, authority ceilings, non-substitution and failure behavior.
3. **Canonicalization** — exact byte/JSON normalization and digest rules. Existing v1 canonicalizations are frozen per contract; they are not silently unified.
4. **Conformance** — executable golden vectors including expected durable deltas and forbidden effects.

## Responsibility-preserving invariants

The following separations are canonical:

- judgment != authorization;
- policy allow != AuthorizationGrant;
- provider/execution success != verified/confirmed objective completion;
- `epistemic_status=supported` != governance `qualification=qualified`;
- governed state application != real-world Action;
- historical provenance != current qualification;
- dependency impact != discharge;
- selecting a repair != realizing a repair;
- current-use admission != execution authority;
- existing adopted assignment use != classification of reality.

## Public authority ceiling

Public contracts may expose read-only views of authority-bearing runtime objects, but clients cannot mint or reconstruct authority from those views. In particular, `InvocationPermit` and `GovernanceUseRequirement` remain runtime-internal. Public surfaces expose `InvocationPermitView` and `GovernanceUseAdmissionView` only.

## Compatibility

`distinction-governance-1.0`, Control Plane `official-1.0.0`, runtime protocol `2.0`, provider protocol `1`, and the existing persisted/event tokens remain compatible unless a versioned contract in this directory explicitly declares a breaking change.

See `catalog.toml` for the machine-readable contract index.