---
document_type: research-correspondence
document_status: stable
normative_for_runtime: false
updated: 2026-08-27
---

# Non-normative relationship to the Framework and formal kernel

This document records research lineage, formal-verification evidence and cross-repository correspondence. It is **not** a portable-runtime semantic contract.

Current ownership is:

```text
ratio/责任拓扑
    owns the upstream Framework V1 semantic/design definitions,
    responsibility cuts and handoff rules

responsibility_topology
    owns its formal research governance,
    Lean theorem/checker/proof semantics and frozen research artifacts

portable-runtime/contracts/
    owns portable-runtime canonical product semantics,
    interoperability contracts and conformance meaning
```

These ownership roles are intentionally different:

```text
upstream Framework semantic/design source
!= downstream normative product protocol
!= formal-specialization/proof owner
```

`ratio/责任拓扑` may motivate or define an upstream Framework distinction, but it is not a runtime dependency. A Framework change does not change portable-runtime behavior unless the relevant semantics are deliberately adopted and versioned in `portable-runtime/contracts/`.

`responsibility_topology` may prove or check a formal specialization, but that proof surface does not become portable-runtime semantic authority.

No external repository is a normative dependency for determining portable-runtime legal state, legal transition, authority, replay identity, qualification or public wire meaning. If this document or any external source conflicts with `contracts/`, `contracts/` wins for portable-runtime product behavior.

## Current correspondence directions

### Framework -> product protocol / runtime

```text
ratio/责任拓扑 Framework definitions and responsibility cuts
        |
        | reference / boundary-reference / deliberate product adoption
        v
portable-runtime/contracts
        |
        | normative product protocol
        v
portable-runtime implementation
```

The adoption edge is explicit and versioned. Therefore:

```text
reference / operationalize / represent
!= redefine the upstream Framework

upstream Framework change
-/-> automatic portable-runtime semantic change
```

### Framework -> formal specialization

```text
ratio/责任拓扑 Framework definitions
        |
        | reference / boundary-reference / specialize
        v
responsibility_topology formal objects and relations
```

A Lean theorem proves a property of its explicit formal specialization. It does not automatically prove the broader Framework concept for every domain.

### Runtime -> formal evidence

The active runtime-to-formal relation is evidence-oriented:

```text
portable-runtime/contracts
        |
        v
runtime observation / certificate
        |
        v
unverified extraction / serialization boundary
        |
        v
Lean checker
        |
        v
restricted formal conclusion about the submitted artifact
```

There is no general refinement theorem:

```text
responsibility_topology -/-> verified refinement of portable-runtime
portable-runtime -/-> verified implementation of responsibility_topology
```

Research lineage may explain why a product contract or proof obligation was investigated, but those arrows are not current normative runtime dependency arrows.

## Known semantic non-identity

Dependency propagation remains a concrete example. The formal work may use a specialized historical warrant graph with transitive challenge semantics, while the runtime uses typed direct dependency matching and separates impact observation, risk interpretation, policy disposition, revalidation and discharge.

Therefore the safe claim is that the Framework, formal specialization and product runtime can preserve related responsibility distinctions while using different state spaces and propagation semantics. The unsafe claim is that formal challenge semantics verify the runtime revalidation engine.

## Restricted observational bridge

The bridge uses finite observation bundles and a neutral observation layer rather than claiming state equality:

```text
RuntimeObservationBundle0
        | alpha_r0
        v
       O0
        ^
        | alpha_f0
FormalObservationBundle0
```

Mapping quality remains explicit:

```text
EXACT-SHAPE
ABSTRACTION
PARTIAL
SEMANTIC-MISMATCH
NOT-REPRESENTED
```

A known mismatch MUST remain a mismatch; Python must not manufacture formal coordinates or normalize away a semantic difference merely to make conformance appear stronger.

## Certified withdrawal fragment

The runtime contains certificate extraction for a restricted history-retaining qualification-withdrawal fragment. The corresponding Lean checker proves a property of the certificate it receives.

The trust boundary is:

```text
raw runtime state / events
        |
        | ordinary Python execution
        v
observation + certificate extraction / serialization
        |
        | UNVERIFIED EXTRACTION BOUNDARY
        v
QualificationWithdrawalCertificate
        |
        | VERIFIED CHECKER STARTS HERE
        v
Lean checker
        |
        v
restricted abstract transition conclusion
```

Approved claim:

> A concrete certificate presented to the Lean checker satisfies the checker's restricted formal contract when the checker accepts it.

Not approved:

```text
Python runtime verified
portable-runtime refines responsibility_topology
certificate extraction verified by Lean
RuntimeStep -> FormalStep*
```

Historical implementation/proof references such as portable-runtime PRs #9/#10 and responsibility_topology PRs #73–#75 remain provenance for this research bridge only. They are not compatibility pins and are not loaded by runtime code.

## Cross-domain and adequacy boundary

Formal similarity, case-model encodings and cross-domain counterexamples are evidence, not portable-runtime semantic ownership and not verification of external domains.

Keep distinct:

```text
implementation correspondence != responsibility-model adequacy
correct repair inside a supplied model != entitlement to conclude the model is sufficient
```

Runtime deep reopen operationalizes a selected revision scope. It is not proof that the revision-scope judgment is correct or that a regime is adequate.

## Strong-claim gate

Future documentation using terms such as `verified runtime`, `formal refinement`, `implements exactly`, `semantically equivalent`, `complete dependency extraction`, or `universal responsibility invariant` must cite a theorem/artifact establishing that exact relation.

Preferred language for the current cross-repository relation includes `upstream Framework semantic/design source`, `downstream normative product protocol`, `formal specialization`, `research correspondence`, `formal verification evidence`, `partial observational boundary`, `restricted certified observational bridge`, and `verified certificate checker`.

This document changes neither canonical runtime semantics nor runtime behavior.
