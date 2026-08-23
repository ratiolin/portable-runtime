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
- `responsibility_topology` owns Lean specializations, theorem statements, proof artifacts, paper-specific formal claim surfaces, and the current cross-repository REF-1 observation-bridge specification.

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

> Both repositories preserve distinctions among historical dependency, mutable operative/current qualification, observed impact, and subsequent review/discharge responsibilities, while using different propagation and execution semantics for their respective object models.

The following is not currently supported:

> The Lean challenge semantics verify the portable-runtime revalidation engine.

## 4. REF-1 observation bridge status

The first bridge-design pass is now recorded in `responsibility_topology/OBSERVATION_BRIDGE_ALPHA0.md`.

It changes the previous candidate bridge shape.

### 4.1 The state-only signature is rejected

The earlier planning shape:

```text
alpha : RuntimeState -> FormalObservation
```

is now considered underspecified for the current systems.

Runtime authorization currentness can depend on observation time through grant validity, expiry, and revocation, while durable `AuthorizationUse` deliberately preserves authorization at the historical action time.

On the formal side, some impact/repair observations depend on challenge/repair trace witnesses or supplied repair problems rather than on the final state alone.

Therefore the current bridge inputs are conceptual observation bundles:

```text
RuntimeObservationBundle0 :=
  runtime snapshot
  + observedAt
  + relevant records/relations
  + optional impact/reopen views

FormalObservationBundle0 :=
  formal state
  + finite observation boundary
  + optional challenge/revalidation/problem witnesses
```

### 4.2 Neutral common observation algebra

The current target is a neutral `O0` rather than a Lean-state-shaped object:

```text
RuntimeObservationBundle0
        | alpha_R0
        v
       O0
        ^
        | alpha_F0
FormalObservationBundle0
```

`O0` keeps distinct observation families for:

```text
historicalTrace
historicalDependency
operativeStatus
activationUse
impactObservation
reviewInvalidation
dischargeRequirement
dischargeEvidence
regimeReference
mismatchAnnotations
```

This vocabulary is intentionally weaker than either repository's full internal model.

### 4.3 XDI constraints inherited by REF-1

The cross-domain falsification work changes bridge assumptions:

- historical trace and operative status are separate; a historical record must not imply continued operative force;
- impact observation remains separate from discharge requirement/evidence;
- regime/policy/version references may be preserved, but higher-order adequacy is not projected as a Boolean fact.

### 4.4 Current mapping status

The bridge currently classifies mappings as:

```text
EXACT-SHAPE
ABSTRACTION
PARTIAL
SEMANTIC-MISMATCH
NOT-REPRESENTED
```

No broad runtime/formal coordinate is currently approved as unconditional `EXACT-SHAPE`.

Important known mismatches include:

```text
runtime direct typed dependency impact
!=
formal transitive historical challenge closure

runtime clock-indexed grant currentness
!=
formal state-indexed Usable/BaseCurrent/Grounded

runtime RevalidationDisposition policy action
!=
formal RepairProblem / RepairAction / RepairSet

runtime Work/Action/AuthorizationUse execution evidence
!=
formal Grounded activation topology

runtime deep ReopenAssessment scopes
!=
formal Q_open entitlement theory
```

### 4.5 What REF-1 does establish

REF-1 identifies a non-trivial **partial observational boundary**. It does not establish implementation refinement.

The next bridge step, if undertaken, is finite fixture adapters that emit `O0` observations from each side and expose information loss/mismatch mechanically.

Do not jump directly to:

```text
RuntimeStep(r,r')
->
FormalStep*(...)
```

until those fixture projections are stable without extensive ad hoc case distinctions.

## 5. Adequacy remains a separate responsibility

Even a correct future observational or refinement theorem would not prove that the shared responsibility vocabulary is adequate.

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

Runtime deep reopen is currently an operational representation of a selected revision scope. It is not proof that the revision-scope judgment is correct.

## 6. Cross-domain candidate status

Cross-domain falsification no longer supports the unqualified statement:

```text
persistent relation != current responsibility
```

as a candidate invariant. Historical trace/record persistence and operative-relation persistence must be separated.

Two narrower candidate invariants currently survive at `formal similarity` only:

```text
CI-2
Affectedness does not by itself constitute sufficient discharge.

CI-3
Conformance within a represented regime does not by itself settle
higher-order adequacy/validity/fitness of that regime for its relied-upon purpose.
```

Neither has established mechanism similarity or universality.

## 7. Strong-claim gate

Any future documentation using phrases such as:

```text
verified runtime
formal refinement
implements exactly
semantically equivalent
complete dependency extraction
universal responsibility invariant
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
partial observational boundary
selected conformance / observational evidence
```

This document governs relationship language only. It changes neither Framework definitions nor runtime behavior.