# Responsibility-separation product contracts

This document records a deliberately narrow product interpretation of the frozen
`responsibility_topology` research artifact.  It does **not** claim that
`portable-runtime` is Lean-verified or that the runtime is a refinement of the
formal model.

The Strict-L6 success path remains:

```text
actual serialized runtime transition
    -> Lean parser
    -> Lean-owned B0 projection
    -> Lean checker
```

`RawWithdrawalTransitionV1` is therefore a frozen runtime-native serialization
surface.  Python must not manufacture B0 coordinates or silently normalize a
known semantic mismatch in order to make the two models look identical.

## Contracts

| ID | Product contract | Evidence class |
|---|---|---|
| RSC-001 | A qualification-state change keeps the subject/provenance addressable and produces an append-only transition audit event. | Strict-L6 consequence + product auditability extension |
| RSC-002 | An Assertion used as positive current-use qualification must be current and supported; stale or revalidation-required assertions cannot issue a new invocation permit. | frozen formal consequence + product admission rule |
| RSC-003 | Dependency impact is not discharge. | formal separation / countermodel |
| RSC-004 | Selecting a repair is not realizing the repair. | formal repair-sufficiency separation |
| RSC-005 | Provider/execution success is not terminal objective completion. | runtime governance invariant |
| RSC-006 | A known semantic mismatch must remain explicit; runtime direct typed impact is not rewritten into formal transitive historical impact. | frozen cross-repository anti-collapse rule |

## Claim boundary

The contracts above are **proof-derived product contracts**, not six Lean
theorems with identical status.  In particular, this repository does not claim:

- full runtime refinement or end-to-end runtime verification;
- complete automatic extraction of a real-world repair graph;
- that declared obligations exhaust reality;
- a universal responsibility ontology;
- that direct runtime dependency impact and formal historical challenge impact
  are semantically identical.

The runtime remains responsible for its own serialization, persistence,
authorization, scope/version binding, and product admission rules.
