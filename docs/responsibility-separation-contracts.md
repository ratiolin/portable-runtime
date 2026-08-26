# Responsibility-separation product contracts

Canonical source:

```text
contracts/semantics/core/responsibility-separation-v1.md
```

This document is a readable product index/projection of the canonical responsibility-separation contracts. It owns no independent semantics. If it conflicts with `contracts/`, `contracts/` wins.

The restricted formal checker path remains evidence only:

```text
actual serialized runtime transition
    -> unverified extraction / parser boundary
    -> formal observation / certificate
    -> Lean checker
```

A formal checker can validate the artifact it receives; it does not make the Python runtime verified and does not own portable-runtime semantics.

## Contracts

| ID | Product contract | Evidence class |
|---|---|---|
| RSC-001 | A qualification-state change keeps the subject/provenance addressable and produces an append-only transition audit fact. | product invariant; formal evidence may support it |
| RSC-002 | An Assertion used as positive current-use qualification must be current and supported; stale or revalidation-required assertions cannot issue a new invocation permit. | product admission rule |
| RSC-003 | Dependency impact is not discharge. | responsibility separation; formal countermodels may support it |
| RSC-004 | Selecting a repair is not realizing the repair. | responsibility separation |
| RSC-005 | Provider/execution success is not terminal objective completion. | runtime governance invariant |
| RSC-006 | A known semantic mismatch remains explicit; runtime direct typed impact is not rewritten into a different historical/transitive impact semantics. | anti-collapse compatibility rule |
| RSC-007 | Domain/framework judgment, `GovernanceDecision`, and Responsibility Record Plane `Decision` are distinct responsibility objects; none silently mints action authorization. | canonical cross-layer boundary |
| RSC-008 | `GovernedApplication` is a committed governance-state application, not evidence that a real-world Responsibility Record Plane `Action` occurred. | canonical cross-layer boundary |
| RSC-009 | Responsibility Record Plane `epistemic_status=supported` is not Distinction Governance `qualification=qualified`; qualification requires its own governed responsibility edge. | canonical cross-layer boundary |
| RSC-010 | `PolicyDecision=allow` is not `AuthorizationGrant`; policy admission does not mint authority. | runtime authorization boundary |
| RSC-011 | `resolve_allowed` / `existing_assignment_use_allowed` may use an assignment already registered in the adopted partition; it does not classify reality, mutate partition membership, or assert ontic truth. | distinction-governance compatibility boundary |
| RSC-012 | Governance admissibility validation does not prove external source truth; missing/ambiguous/stale identity, provenance, freshness, authority, or required source material fails closed for new positive use. | semantic-ingress trust boundary |

## Local canonical boundary

The current semantic owner is `portable-runtime/contracts`. These former duplicate documentation paths remain intentionally absent and MUST NOT be recreated as canonical definitions:

```text
docs/responsibility-record-plane.md
docs/action-responsibility-practice.md
```

Their current product semantics are owned by the versioned local contracts under `contracts/semantics/records/` and `contracts/semantics/action/`.

## Claim boundary

The contracts above do not claim:

- full runtime refinement or end-to-end runtime verification;
- complete automatic extraction of a real-world repair graph;
- that declared obligations exhaust reality;
- a universal responsibility ontology;
- that direct runtime dependency impact and a formal historical challenge relation are semantically identical;
- that governance admissibility proves truth of external event/evidence/authority sources.

The runtime remains responsible for serialization, persistence, transactions, authorization adapters, event journal, scope/version binding, RealityBoundary, provider execution and product admission rules.
