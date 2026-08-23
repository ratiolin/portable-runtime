---
document_type: relationship-contract
document_status: stable
framework_version: 1.0.0
knowledge_scope: cross-repository-boundary
updated: 2026-08-23
semantic_contract:
  role: relationship-governance
  defines: []
  prohibits:
    - formal_refinement_claim_without_theorem
    - state_equality_claim
    - theory_redefinition
    - runtime_behavior_redefinition
---

# Relationship to the `responsibility_topology` Formal Kernel

This document governs the relationship between this repository and `xiongweilin/responsibility_topology`.

The two repositories belong to the same broader research program, but they have different responsibility owners:

- `portable-runtime` owns Framework V1.0 documentation, record semantics, operational/runtime mechanisms, implementation behavior, and executable evidence;
- `responsibility_topology` owns Lean specializations, theorem statements, proof artifacts, and paper-specific formal claim surfaces.

The relationship is intentionally **not** a verified implementation/refinement relation.

## 1. Framework call vocabulary

This contract reuses the Framework V1.0 call relations defined by `responsibility-topology-overview.md`:

| Mode | Meaning in the cross-repository relationship |
| --- | --- |
| `reference` | cite an upstream concept without changing its meaning |
| `boundary-reference` | import only a responsibility boundary or handoff condition |
| `specialize` | make a framework concept precise for a narrower formal object model |
| `operationalize` | turn a theoretical responsibility into a runtime/procedural responsibility without redefining the theory |
| `represent` | encode a concept into runtime records/read structures without making the representation the concept definition |
| `handoff` | explicitly transfer responsibility to another module, procedure, or evidence owner |

The governing rule remains:

```text
call != redefinition
```

Definition ownership, specialization ownership, evidence ownership, and operational-fact ownership remain distinct.

## 2. Current direction of calls

### Framework/theory -> Lean specialization

```text
portable-runtime framework/theory documents
    --reference / boundary-reference / specialize-->
responsibility_topology formal kernel
```

A Lean theorem proves a property of its explicit formal specialization. It does not automatically prove the broader Framework V1.0 concept for every domain.

### Framework/practice -> runtime mechanisms

```text
portable-runtime theory/practice
    --operationalize / represent-->
portable-runtime records, authorization, revision,
revalidation, reopen, recovery, and execution
```

Executable behavior is evidence about the implementation. It does not redefine the upstream theoretical meaning.

### Lean kernel <-> runtime implementation

No refinement relation is currently established:

```text
responsibility_topology
    -/-> verified refinement of portable-runtime

portable-runtime
    -/-> verified implementation of responsibility_topology
```

The current relationship is conceptual specialization plus selected conformance/correspondence evidence where explicitly stated.

## 3. Known semantic non-identity

Dependency propagation after change is a concrete example of why the two systems must not be equated.

The Paper 3 formal model in `responsibility_topology` uses a specialized historical warrant graph and models challenge impact as the target plus transitive historical warrant descendants.

This runtime's R1.3 revalidation surface uses typed dependency relations to produce structural impact assessments and explicitly does not treat generic dependency impact as recursive full-graph invalidation. Runtime impact, risk assessment, and revalidation disposition are separate judgments.

Therefore the following is safe:

> Both repositories preserve the distinction between recorded/historical dependency and mutable current qualification, while using different dependency-propagation semantics for their respective object models.

The following is not currently supported:

> The Lean challenge semantics verify the portable-runtime revalidation engine.

## 4. Future bridge target

If a formal execution bridge is developed later, the preferred target is observational abstraction/refinement, not literal state equality.

Candidate shape:

```text
alpha : RuntimeState -> FormalObservation
```

followed by a theorem family such as:

```text
RuntimeStep(r, r')
->
FormalStep* (alpha r) (alpha r')
```

or a weaker observational correspondence over a selected interface.

Any such bridge must specify:

1. which runtime records/states are observed;
2. which Lean objects those observations denote;
3. which runtime transitions are in scope;
4. whether one runtime step maps to zero, one, or multiple formal steps;
5. which observations are preserved, reflected, or only simulated;
6. what runtime detail is abstracted away;
7. where dependency-policy differences require separate semantics instead of forced equivalence.

Do not target:

```text
LeanState = PythonState
```

unless future model design first makes that identity meaningful.

## 5. Adequacy remains a separate responsibility

Even a correct future refinement theorem would not prove that the shared responsibility vocabulary is adequate.

Keep distinct:

```text
implementation correspondence
!=
responsibility-model adequacy
```

and:

```text
correct repair inside a supplied model
!=
entitlement to conclude that the model itself is sufficient
```

The latter is the `Q_open`-level problem: when may a system conclude that its responsibility vocabulary, dependency cuts, or governing regime must itself be reopened?

## 6. Cross-domain invariance remains unproved

The current Lean kernel is an epistemic/state-backed specialization. Similar structures in other domains are research candidates, not established invariants merely because the same terminology can be applied.

A future cross-domain result must distinguish:

```text
shared analogy
!=
shared formal structure
!=
proved invariant under specialization
```

## 7. Strong-claim gate

Any future documentation using phrases such as:

```text
verified runtime
formal refinement
implements exactly
semantically equivalent
complete dependency extraction
```

must cite a concrete theorem/artifact establishing that relation.

Until then, approved relationship language is:

```text
reference
boundary-reference
specialize
operationalize
represent
handoff
conceptual alignment
selected conformance / observational evidence
```

This document governs relationship language only. It changes neither Framework definitions nor runtime behavior.