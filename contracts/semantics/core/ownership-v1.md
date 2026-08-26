# Canonical ownership — v1

Status: stable
Owner: `portable-runtime/contracts`

## Rule

The current repository is semantically self-contained. `contracts/` is the only canonical owner for product semantics consumed by runtime code, public APIs, SDKs, conformance tests and operator tooling.

External papers, repositories, proofs and historical commits may be cited in historical or research discussion outside the normative contract surface, but they MUST NOT be required to determine legal runtime state, legal transition, public wire meaning, authority, replay identity, current qualification, or compatibility.

## Canonical precedence

When two artifacts disagree, precedence is:

1. `contracts/` semantic contracts;
2. `contracts/` structural schemas;
3. `contracts/` canonicalization rules;
4. `contracts/` conformance vectors;
5. Python reference implementation;
6. HTTP/public adapters;
7. TypeScript client and workflow helpers;
8. Responsibility Inspector.

Therefore:

```text
PythonReferenceBehavior conflicts with CanonicalContract
-> Python bug

TypeScriptBehavior conflicts with CanonicalContract
-> TypeScript conformance bug

InspectorInterpretation conflicts with CanonicalContract
-> Inspector bug
```

`contracts/` defines semantics. Python is the reference execution oracle for those semantics and is itself subject to the contracts; Python source code is not a second semantic definition owner.

## Normative dependency direction

```text
contracts/
  -> Python reference implementation
  -> HTTP/public adapters
  -> TypeScript client / workflow SDK
  -> Inspector
```

No arrow points back from an implementation or consumer into the canonical contract.

## Non-substitution

- implementation behavior is evidence of conformance, not a new definition;
- generated DTOs are structural projections, not semantic authority;
- a public view of an authority-bearing object is not itself authority;
- a proof/checker may verify a submitted artifact but cannot silently redefine the runtime contract;
- persisted history remains historical fact even when current qualification later changes.

## Change rule

A semantic change that expands legal state, legal transition, authority, mutation scope or current-use entitlement MUST update the relevant contract version and conformance vectors before implementation behavior changes.

Editorial clarification that preserves all accepted/rejected vectors may remain within the same compatibility version.
