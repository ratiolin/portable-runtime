---
document_type: relationship-contract
document_status: stable
framework_version: 1.0.0
knowledge_scope: cross-repository-boundary
updated: 2026-08-24
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

The repositories belong to the same research program but retain distinct responsibility ownership:

- `portable-runtime` owns Framework V1.0 documentation, record semantics, runtime mechanisms, implementation behavior, executable adapters, fixtures, and runtime-side observation certificates;
- `responsibility_topology` owns Lean specializations, theorem statements, proof artifacts, paper-specific formal claim surfaces, cross-domain minimal calculi, and the verified observational checker.

The relationship remains **not** a verified implementation/refinement relation.

## 1. Framework call vocabulary

This contract reuses the Framework V1.0 relations:

| Mode | Meaning in this cross-repository relationship |
| --- | --- |
| `reference` | cite a concept without changing its meaning |
| `boundary-reference` | import only a responsibility boundary or handoff condition |
| `specialize` | make a framework concept precise for a narrower formal object model |
| `operationalize` | turn a theoretical responsibility into a runtime/procedural responsibility without redefining the theory |
| `represent` | encode a concept into runtime records/read structures without making the representation the definition |
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

A Lean theorem proves a property of its explicit formal specialization. It does not automatically prove the broader Framework concept in every domain.

### Framework/practice -> runtime mechanisms

```text
portable-runtime theory/practice
    --operationalize / represent-->
portable-runtime records, authorization, revision,
revalidation, reopen, recovery, execution, O0 adapters
```

Executable behavior is implementation evidence. It does not redefine upstream theoretical meaning.

### Lean kernel <-> runtime implementation

No general refinement relation has been established:

```text
responsibility_topology
    -/-> verified refinement of portable-runtime

portable-runtime
    -/-> verified implementation of responsibility_topology
```

The current strongest bridge is a **restricted certified observational bridge** described below.

## 3. Known semantic non-identity

Dependency propagation remains the clearest reason not to identify the two systems.

The Paper 3 formal model uses a specialized historical warrant graph and models challenge impact as the challenged target plus transitive historical descendants.

The runtime R1.3 surface uses typed direct dependency matching and explicitly does not treat generic dependency impact as recursive full-graph invalidation. Runtime impact, risk interpretation, and policy disposition are separate judgments.

Therefore the following remains safe:

> Both repositories preserve distinctions among recorded/historical dependency, mutable operative qualification, impact observation, and subsequent review/discharge responsibilities, while using different propagation and execution semantics.

The following remains unsupported:

> The Lean challenge semantics verify the portable-runtime revalidation engine.

## 4. REF-1 design boundary

REF-1 rejected the underspecified state-only shape:

```text
alpha : RuntimeState -> FormalObservation
```

because runtime observations may require explicit observation time while formal observations may require finite trace/problem witnesses not recoverable from the final state alone.

The bridge therefore uses finite observation bundles and a neutral `O0`:

```text
RuntimeObservationBundle0
        | alpha_r0
        v
       O0
        ^
        | alpha_f0
FormalObservationBundle0
```

Observation families include:

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
```

and mapping quality is first-class:

```text
EXACT-SHAPE
ABSTRACTION
PARTIAL
SEMANTIC-MISMATCH
NOT-REPRESENTED
```

Higher-order adequacy is intentionally not projected as an O0 Boolean.

## 5. REF-2 executable O0 status

REF-2 is implemented in this repository at:

```text
portable-runtime PR #9 merge
8d04e01e7e16608da5ad9a17b7dc0f4d8f5c229f
```

Primary implementation:

```text
src/portable_runtime/observation/o0.py
```

Six REF-1 fixture families F1–F6 execute through the adapters.

`discover_b0` discovers compatible coordinates from actual adapter output under explicit subject-ID mappings; it does not receive a preselected family allowlist.

The first non-empty witnessed fragment is:

```text
B0 = {
  historicalTrace:trace.referent-present,
  operativeStatus:qualification.current
}
```

The impact coordinate is not admitted to B0 because runtime direct typed impact and formal transitive challenge impact remain `SEMANTIC-MISMATCH`.

This is a substantive boundary, not an adapter defect to normalize away.

## 6. REF-3 certified withdrawal fragment

### 6.1 Runtime-side certificate extraction

Runtime-side extraction is implemented at:

```text
portable-runtime PR #10 merge
fd85f3041db99cf4bc12b81b2219e732827ad622
```

The selected fragment is:

```text
history-retaining qualification withdrawal
```

The versioned runtime certificate records only witnessed B0 information:

```text
historical trace before / after
qualification before / after
accepted discharge evidence after
B0 coordinate identities
source semantic tags
```

The extraction function refuses to infer qualification from impact or disposition data.

A frozen fixture produced from the REF-2 F1 runtime trace records:

```text
historical trace: present -> present
qualification:     qualified -> withdrawn
accepted discharge evidence after: false
```

### 6.2 Verified checker

The corresponding formal checker is merged in `responsibility_topology` at:

```text
PR #73 merge
26bca813ac1c1530a476dc82c24dafcc42ff982c
```

The Lean checker proves that an accepted certificate satisfies the abstract B0 qualification-withdrawal contract.

It also proves the restricted checker-level consequence:

```text
checked qualification withdrawal
+
no accepted discharge/requalification evidence
->
certified current-use continuation rejected
```

The formal kernel separately proves that its existing challenge semantics can realize the same abstract pattern at the challenged target:

```text
exact historical target referent retained
+
pre-state usable
+
post-state not usable
```

These are two sides of one observational fragment. They are not a direct Python-step-to-Lean-step theorem.

## 7. Verified checker trust boundary

The current trust boundary is:

```text
raw runtime state / events
        |
        | ordinary Python execution
        v
alpha_r0 + certificate extraction / serialization
        |
        | UNVERIFIED EXTRACTION BOUNDARY
        v
QualificationWithdrawalCertificate
        |
        | VERIFIED CHECKER STARTS HERE
        v
Lean checkQualificationWithdrawal
        |
        v
abstract B0 transition contract
```

Therefore the approved claim is:

> A concrete certificate presented to the Lean checker satisfies the restricted B0 contract when the checker accepts it.

The following claims are not approved:

```text
Python runtime verified
portable-runtime refines responsibility_topology
certificate extraction verified by Lean
RuntimeStep -> FormalStep*
```

A stronger refinement claim would have to reduce or separately certify the extraction boundary.

## 8. Cross-domain status inherited by the bridge

Cross-domain falsification rejected the broad unqualified candidate:

```text
persistent relation != current responsibility
```

Historical trace persistence and persistence of operative force are separate questions.

Two narrower candidates survive at `FORMAL SIMILARITY` only:

```text
CI-2
Affectedness does not by itself constitute sufficient discharge.

CI-3
Conformance within a represented regime does not by itself settle
higher-order adequacy / validity / fitness for the relied-upon purpose.
```

`responsibility_topology` now contains minimal parametric calculi and finite D1–D3 plus D4 case-model encodings for these responsibility cuts. Those case models are not verification of the external domains and do not establish mechanism similarity or universality.

## 9. Level-6 technical consolidation status

The technical-consolidation track is frozen in `responsibility_topology` at:

```text
PR #74 integration merge
59751542378a61dc33d372dd693ebda8627bab5a

PR #75 bookkeeping freeze
b95fb82742739395e1e917aa3019199ca470ffad
```

Machine gates for the integration:

```text
Lean #256:                    PASS
Python-Lean Conformance #197: PASS
```

Frozen verdict:

```text
TECHNICAL LEVEL 6: PASS
scope: restricted observational-certificate bridge
```

This verdict means the technical evidence stack exists:

```text
CrossDomainCore
+
DomainInstances
+
CertifiedRuntimeBridge
```

It does not mean:

```text
universal responsibility invariant proved
external domains verified
Python runtime verified
full observational refinement proved
Q_open solved
```

Technical feature expansion is stopped by default after this checkpoint.

## 10. Adequacy / Q_open remains separate

Even a future stronger runtime correspondence would not prove that the responsibility vocabulary is adequate.

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

Runtime deep reopen is an operational representation of a selected revision scope. It is not proof that the revision-scope judgment is correct or that a regime is entitled to reopen itself.

The Q_open work remains parked until the Level-6 technical checkpoint is treated as frozen.

## 11. Strong-claim gate

Any future documentation using phrases such as:

```text
verified runtime
formal refinement
implements exactly
semantically equivalent
complete dependency extraction
universal responsibility invariant
```

must cite a concrete theorem/artifact establishing that exact relation.

Currently approved relationship language includes:

```text
reference
boundary-reference
specialize
operationalize
represent
handoff
conceptual alignment
partial observational boundary
restricted certified observational bridge
verified certificate checker
selected conformance / observational evidence
```

This document governs relationship language only. It changes neither Framework definitions nor runtime behavior.
