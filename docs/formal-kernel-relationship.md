---
document_type: research-correspondence
document_status: stable
normative_for_runtime: false
updated: 2026-08-26
---

# Non-normative relationship to the formal kernel

This document records formal-verification evidence and historical/research correspondence. It is **not** a portable-runtime semantic contract.

Current ownership is:

```text
portable-runtime/contracts/
    owns portable-runtime canonical semantics

responsibility_topology
    owns its Lean theorem, checker and proof semantics

ratio
    may remain a historical/research lineage source only
```

No external repository is a normative dependency for determining portable-runtime legal state, legal transition, authority, replay identity, qualification, or public wire meaning. If this document conflicts with `contracts/`, `contracts/` wins.

## Current correspondence direction

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

Historical research lineage may explain why a contract or proof obligation was investigated, but those arrows are not current normative dependency arrows.

## Known semantic non-identity

Dependency propagation remains a concrete example. The formal work may use a specialized historical warrant graph with transitive challenge semantics, while the runtime uses typed direct dependency matching and separates impact observation, risk interpretation, policy disposition, revalidation and discharge.

Therefore the safe claim is that both systems can preserve related responsibility distinctions while using different state spaces and propagation semantics. The unsafe claim is that formal challenge semantics verify the runtime revalidation engine.

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

Preferred language for the current bridge includes `research correspondence`, `formal verification evidence`, `partial observational boundary`, `restricted certified observational bridge`, and `verified certificate checker`.

This document changes neither canonical runtime semantics nor runtime behavior.
