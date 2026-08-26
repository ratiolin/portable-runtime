# Responsibility-separation product contracts

This document records deliberately narrow product contracts derived from the canonical semantics owned by `xiongweilin/ratio/责任拓扑`. `portable-runtime` does **not** own Framework definitions, does not keep local canonical Framework-document copies, and does not claim that the runtime is Lean-verified or a full refinement of the formal model.

The Strict-L6 success path remains:

```text
actual serialized runtime transition
    -> Lean parser
    -> Lean-owned B0 projection
    -> Lean checker
```

`RawWithdrawalTransitionV1` is therefore a frozen runtime-native serialization surface. Python must not manufacture B0 coordinates or silently normalize a known semantic mismatch in order to make the two models look identical.

## Contracts

| ID | Product contract | Evidence class |
|---|---|---|
| RSC-001 | A qualification-state change keeps the subject/provenance addressable and produces an append-only transition audit event. | Strict-L6 consequence + product auditability extension |
| RSC-002 | An Assertion used as positive current-use qualification must be current and supported; stale or revalidation-required assertions cannot issue a new invocation permit. | frozen formal consequence + product admission rule |
| RSC-003 | Dependency impact is not discharge. | formal separation / countermodel |
| RSC-004 | Selecting a repair is not realizing the repair. | formal repair-sufficiency separation |
| RSC-005 | Provider/execution success is not terminal objective completion. | runtime governance invariant |
| RSC-006 | A known semantic mismatch must remain explicit; runtime direct typed impact is not rewritten into formal transitive historical impact. | frozen cross-repository anti-collapse rule |
| RSC-007 | Framework judgment, `GovernanceDecision`, and Responsibility Record Plane `Decision` are different responsibility objects; none silently mints action authorization. | canonical semantic-convergence boundary |
| RSC-008 | `GovernedApplication` is a committed governance-state application, not evidence that a real-world Responsibility Record Plane `Action` occurred. | canonical semantic-convergence boundary |
| RSC-009 | Responsibility Record Plane `epistemic_status=supported` is not Distinction Governance `qualification=qualified`; qualification requires its own governed responsibility edge. | canonical semantic-convergence boundary |
| RSC-010 | `PolicyDecision=allow` is not `AuthorizationGrant`; policy admission does not mint authority. | runtime authorization boundary |
| RSC-011 | `resolve_allowed` / `existing_assignment_use_allowed` may use an assignment already registered in the adopted partition; it does not classify reality, mutate partition membership, or assert ontic truth. | distinction-governance-1.0 compatibility boundary |
| RSC-012 | Governance admissibility validation does not prove external source truth; missing/ambiguous/stale identity, provenance, freshness, authority, or required source material fails closed for new positive use. | semantic-ingress trust boundary |

## Canonical source boundary

Machine-readable source pins live in `semantic-sources.toml`.

Canonical Framework documents live only in `xiongweilin/ratio/责任拓扑`. In particular, these former duplicate local files are intentionally deleted and MUST NOT be recreated as canonical definitions:

```text
docs/responsibility-record-plane.md
docs/action-responsibility-practice.md
```

Operationalization or representation is not redefinition.

## Claim boundary

The contracts above are proof-derived or canonically specialized product contracts, not a claim that each line is a Lean theorem with identical status. In particular, this repository does not claim:

- full runtime refinement or end-to-end runtime verification;
- complete automatic extraction of a real-world repair graph;
- that declared obligations exhaust reality;
- a universal responsibility ontology;
- that direct runtime dependency impact and formal historical challenge impact are semantically identical;
- that governance admissibility proves the truth of external event/evidence/authority sources.

The runtime remains responsible for its own serialization, persistence, transactions, authorization adapters, event journal, scope/version binding, RealityBoundary, provider execution, and product admission rules.
