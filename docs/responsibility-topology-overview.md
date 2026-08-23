---
document_type: moc
document_status: stable
framework_version: 1.0.0
knowledge_scope: navigation
owner: metra
updated: 2026-08-20
last_verified: 2026-08-20
verification_method: Manual alignment of Framework V1.0 responsibility topology, public semantic interfaces, handoff boundaries, one-way Control Plane representation relation, and change gate
revision_basis: framework-v1-freeze-2026-08-20
aliases:
  - Personal Platform
  - Development Environment Overview
tags:
  - moc
  - personal-rnd-platform
  - semantic-governance
semantic_contract:
  role: routing-and-document-governance
  defines: []
  routes:
    - Finite Change Theory
    - Finite Intelligence
    - Finite-System Strategic Interaction
    - Finite Value Genesis
    - Cross-Domain Structure Candidates
    - Finite Civilizational Reliability
    - Finite Change Practice
    - Control Plane
    - Genesis and Architectural Principles of the Finite Framework
  prohibits:
    - theory_redefinition
    - domain_mechanism_redefinition
    - record_semantics_redefinition
    - operational_fact_duplication
    - canonical_surface_expansion_without_gate
---

# Responsibility Topology Overview

> **This page is responsible only for navigation, semantic governance, and the Framework V1.0 change gate. It does not own theoretical definitions.** Theory, mechanisms, procedures, and record semantics must return to their corresponding owner. If this page conflicts with an owner, the owner prevails and this page must be corrected.

## I. What Framework V1.0 Freezes

Framework V1.0 freezes four kinds of structure, not every sentence in the prose:

$$
\boxed{
V1=
\text{responsibility-topology freeze}
+\text{public-semantic-interface freeze}
+\text{handoff-rule freeze}
+\text{change-gate freeze}
}
$$

After V1, new examples, explanations, candidates, research questions, and local terms go by default into domain models, the candidate catalog, research notes, or runtime records. They do not automatically become core theoretical debt.

## II. Core Documents and the Responsibility Topology

### Canonical definition owners

| Document | Identity | V1 public responsibility |
|---|---|---|
| [Theory of Determinative Responsibility](02-theory-of-determinative-responsibility.md) | Meta-model | Defines epistemic boundaries, the minimum analytical language, open / closure, analysis layers, and the fact–norm boundary |
| [Theory of Cognitive Responsibility](03-theory-of-cognitive-responsibility.md) | Capability theory | Defines the public mechanism interface for finite intelligence: candidate formation, open validation, revision depth, reflexivity, epistemic action, and the boundary of subjectivity |
| [Theory of Interaction Responsibility](04-theory-of-interaction-responsibility.md) | Specialized strategic theory | Defines strategic actors, situation representation, representation closure, reopen attribution, and handoff to formal tools |
| [Theory of Value Responsibility](05-theory-of-value-responsibility.md) | Specialized theory of value genesis | Defines the value-genesis interface, experience-status gate, individual value commitment, and reopening under value conflict |
| [Responsibility Structure Candidate Catalog](06-responsibility-structure-candidate-catalog.md) | Dynamic candidate catalog | Defines structure candidates and migration types; catalog entries themselves are not part of the frozen canonical surface |
| [System Responsibility Reliability](07-system-responsibility-reliability.md) | Long-term system-reliability theory | Defines diagnostic dimensions including correction, common capture, fault containment, rate compatibility, effective reversibility, reauthorization, and maneuverability |
| [Action Responsibility Practice](08-action-responsibility-practice.md) | Action methodology | Defines procedure strength, execution, verification, recovery, exit, residual responsibility, and persistent-system governance checks |
| [Responsibility Record Plane](09-responsibility-record-plane.md) | Cross-cutting record-semantics specification | Defines the recording interface for object types, epistemic status, lifecycle, relations, and revalidation; it does not define theory or practice in reverse |

### Non-canonical documents

| Document | Identity | Responsibility |
|---|---|---|
| [Genesis and Architectural Principles of Responsibility Topology](10-genesis-and-architectural-principles.md) | Architecture rationale | Preserves reasons for the architecture, prohibited shortcuts, responsibility integrity, self-review signals, and successor exits; it does not override canonical definitions |
| This page | MOC | Routing, owner aggregation, version governance, and the change gate |

These documents are not a deductive chain that automatically derives answers. Concrete mechanisms and facts are owned by domain models and situational evidence; normative legitimacy, legal standing, and professional standards are owned by the relevant normative and institutional procedures.

## III. Public Canonical Interface

A canonical concept can have only one authoritative definition owner. `semantic_contract.defines` registers only the **public cross-document interface**; it does not register every rigorously defined working term appearing in a document.

A concept should enter `defines` only if at least one of the following holds:

1. other core modules call it directly;
2. it determines a cross-document responsibility boundary or handoff;
3. changing its meaning would cause framework-level compatibility breakage;
4. it is an indispensable stable entry point for the module.

Therefore:

$$
\boxed{
\text{public canonical interface}
\neq
\text{document-local working vocabulary}
}
$$

Local terms may be rigorously defined, revised, split, or removed in the prose without receiving a platform-level canonical ID.

## IV. Call Relations

Other documents may call public concepts only through declared relations:

| Mode | Meaning |
|---|---|
| `reference` | Direct reference without changing the meaning |
| `boundary-reference` | References only a boundary or handoff condition |
| `specialize` / `specialize-*` | Specializes an upstream concept for a particular system or problem |
| `operationalize` | Converts the concept into a procedural responsibility without changing its theoretical meaning |
| `represent` | Converts it into a recording or reading structure without changing the concept itself |
| `handoff` | Explicitly transfers responsibility to another module or procedure |

Thus:

$$
\text{call}\neq\text{redefinition}
$$

Machine checks treat the `semantic_contract` in each canonical document's front matter as the source of truth. The owner table on this page is only an aggregated view.

Definition authority and authority to judge reality must remain separate:

| Position | Question answered |
|---|---|
| canonical definition owner | What does the term mean in this framework? |
| specialization owner | How is it concretized for a particular system or problem? |
| evidence owner | By what evidence standard does a real-world claim hold? |
| operational fact owner | What is the current object, version, authority, or state? |

Defining a concept does not itself confer the entitlement to judge that a real-world object satisfies it.

## V. Dependency Direction and the Control Plane

Framework V1.0 explicitly adopts a one-way representation relation:

$$
\boxed{
\text{Control Plane}
\xrightarrow{\text{represent}}
\text{Theory / Practice concepts}
}
$$

Theory and practice may hand recording responsibility to the [Responsibility Record Plane](09-responsibility-record-plane.md), but they must not make `epistemic_status`, `lifecycle`, or any other concrete record token a reverse dependency of their own theoretical definitions. Future Control Plane versions should not automatically force theory to be reissued.

Framework V1.0 pins runtime record semantics to the accepted `official 1.0.0`. No later Control Plane draft enters the stable V1 dependency until it has passed an independent acceptance process.

## VI. Representation and Notation Governance

Across documents, the following minimum discipline applies:

- working symbols primarily distinguish analytical positions; using functions, arrows, subscripts, or set-like notation does not automatically make them rigorous mathematical objects;
- `\rightsquigarrow` may denote candidate formation or a conditional correspondence, while `\leadsto` may denote a possible path or revision influence; determinism, causality, temporality, and computability must be stated locally in prose;
- if a working representation is promoted into a mathematical model, the objects, domain, codomain, variables, conditions, error, data, and validation method must be specified separately;
- downstream documents keep only notation boundaries specific to their domain rather than repeating the entire general disclaimer.

This is a document-governance convention. It adds no canonical theoretical concept.

## VII. Knowledge and Action Architecture

```text
                         Finite Change Theory
              ┌────────────┼────────────┬────────────┐
              ↓            ↓            ↓            ↓
       Finite Intelligence  Finite-System         Finite Value       Cross-Domain
                            Strategic Interaction Genesis             Structure Candidates
              └────────────┬────────────┴────────────┘
                           ↓
                    Domain Models / Situational Facts
                           ↕
                    Finite Civilizational Reliability
                           ↓
         Finite Change Practice + Legal / Normative / Shared-Affairs Procedures
                           ↓
                          Action
                           ↓
                       New Reality
                           ↺

Control Plane =================================================
Cross-cutting recording and revalidation; it represents only and does not
become a reverse definitional dependency of theory or practice.
```

The diagram represents primary responsibilities and handoff positions. It does not represent the temporal order of reality, a ranking of theoretical value, or a fixed execution flow.

## VIII. Entry by Question

| Question | Primary entry | Follow-up entry |
|---|---|---|
| `E₀` / `E₁`, difference / retention, distinction, factors, organization, orientation, judgment, action, open / closure | [Theory of Determinative Responsibility](02-theory-of-determinative-responsibility.md) | Domain models |
| Learning, candidate generation, structural reorganization, open validation, revision depth, agency, and the boundary of subjectivity | [Theory of Cognitive Responsibility](03-theory-of-cognitive-responsibility.md) | Corresponding domain models |
| Multi-actor strategic representation, models of others, representation closure, reopening, and handoff to formal models | [Theory of Interaction Responsibility](04-theory-of-interaction-responsibility.md) | [Theory of Cognitive Responsibility](03-theory-of-cognitive-responsibility.md) / domain models / [Action Responsibility Practice](08-action-responsibility-practice.md) |
| System relevance, experiential polarity, reflective endorsement, and individual value commitment | [Theory of Value Responsibility](05-theory-of-value-responsibility.md) | Psychological, relational, and other domain models |
| Entering an unfamiliar domain and searching for transferable problem structures | [Responsibility Structure Candidate Catalog](06-responsibility-structure-candidate-catalog.md) | Corresponding domain models |
| Long-term correction, fault propagation, lock-in, recovery, reauthorization, and maneuverability | [System Responsibility Reliability](07-system-responsibility-reliability.md) | Domain models / [Action Responsibility Practice](08-action-responsibility-practice.md) |
| Real-world action, procedure strength, verification, recovery, and exit | [Action Responsibility Practice](08-action-responsibility-practice.md) | Professional standards / domain models |
| Recording objects, epistemic status, lifecycle, relations, and revalidation | [Responsibility Record Plane](09-responsibility-record-plane.md) | Project README / RUNBOOK |
| Why the framework has its current boundaries and when it should review itself | [Genesis and Architectural Principles of Responsibility Topology](10-genesis-and-architectural-principles.md) | Corresponding canonical owner |

### Domain models and professional questions

| Question | Primary entry | Follow-up entry |
|---|---|---|
| Formalization, statistics, decision, and optimization | [Mathematics Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E6%95%B0%E5%AD%A6%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) | [Theory of Determinative Responsibility](02-theory-of-determinative-responsibility.md) / [Theory of Cognitive Responsibility](03-theory-of-cognitive-responsibility.md) |
| Physical objects, measurement, and experiment | [Physics Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%89%A9%E7%90%86%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) | [Mathematics Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E6%95%B0%E5%AD%A6%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) |
| Life maintenance, bodily state, health, and recovery | [Life and Health Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%94%9F%E5%91%BD%E5%81%A5%E5%BA%B7%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) | [Psychology Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E5%BF%83%E7%90%86%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) / [Relations Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E5%85%B3%E7%B3%BB%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) |
| Feeling, motivation, habit, goal endorsement, and psychological recovery | [Psychology Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E5%BF%83%E7%90%86%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) | [Theory of Cognitive Responsibility](03-theory-of-cognitive-responsibility.md) / [Theory of Value Responsibility](05-theory-of-value-responsibility.md) / [Relations Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E5%85%B3%E7%B3%BB%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) |
| Relations among subjects, commitments, dependency, repair, and exit | [Relations Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E5%85%B3%E7%B3%BB%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) | [Theory of Value Responsibility](05-theory-of-value-responsibility.md) / [Organization and Institutions Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%BB%84%E7%BB%87%E5%88%B6%E5%BA%A6%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) |
| Organizational roles, authority, rules, judgment structures, and institutional change | [Organization and Institutions Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%BB%84%E7%BB%87%E5%88%B6%E5%BA%A6%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) | [Theory of Interaction Responsibility](04-theory-of-interaction-responsibility.md) / [Economics Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%BB%8F%E6%B5%8E%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) |
| Software, systems, data, and runtime results | [Computing Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E8%AE%A1%E7%AE%97%E6%9C%BA%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) | [Action Responsibility Practice](08-action-responsibility-practice.md) / RUNBOOK |
| Learning, teaching, and educational institutions | [Education Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E6%95%99%E8%82%B2%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) | [Theory of Cognitive Responsibility](03-theory-of-cognitive-responsibility.md) / [Organization and Institutions Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%BB%84%E7%BB%87%E5%88%B6%E5%BA%A6%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) |
| Production, distribution, exchange, debt, and economic institutions | [Economics Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%BB%8F%E6%B5%8E%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) | [Mathematics Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E6%95%B0%E5%AD%A6%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) / [Organization and Institutions Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%BB%84%E7%BB%87%E5%88%B6%E5%BA%A6%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) |

### Action, runtime, and project entry points

| Question | Primary entry | Follow-up entry |
|---|---|---|
| Current main line, backlog, and time-block arrangement | [Current Action Board](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E5%BD%93%E5%89%8D%E8%A1%8C%E5%8A%A8%E7%9C%8B%E6%9D%BF.md) | [Action Responsibility Practice](08-action-responsibility-practice.md) |
| Diet, resistance training, and bodily recovery | [Diet and Resistance Training Plan](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E9%A5%AE%E9%A3%9F%E4%B8%8E%E6%8A%97%E9%98%BB%E8%AE%AD%E7%BB%83%E8%AE%A1%E5%88%92.md) | [Life and Health Domain Model](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%94%9F%E5%91%BD%E5%81%A5%E5%BA%B7%E9%A2%86%E5%9F%9F%E6%A8%A1%E5%9E%8B.md) |
| Planning, executing, verifying, recovering, and exiting a change | [Action Responsibility Practice](08-action-responsibility-practice.md) | [Current Action Board](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E5%BD%93%E5%89%8D%E8%A1%8C%E5%8A%A8%E7%9C%8B%E6%9D%BF.md) |
| Runtime state, services, deployment, and daily checks | [Environment Operations Manual](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%8E%AF%E5%A2%83%E8%BF%90%E7%BB%B4%E6%89%8B%E5%86%8C.md) | [metratio.com Infrastructure Documentation](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/metratio.com%20%E5%9F%BA%E7%A1%80%E8%AE%BE%E6%96%BD%E6%96%87%E6%A1%A3.md) / [Model Routing](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E6%A8%A1%E5%9E%8B%E8%B7%AF%E7%94%B1.md) |
| Takeover, shutdown, recovery, and backup | [Disaster Recovery](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%81%BE%E9%9A%BE%E6%81%A2%E5%A4%8D.md) | [Backup Index](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E5%A4%87%E4%BB%BD%E7%B4%A2%E5%BC%95.md) / [Environment Operations Manual](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%8E%AF%E5%A2%83%E8%BF%90%E7%BB%B4%E6%89%8B%E5%86%8C.md) |
| Dependencies, image vulnerabilities, and security exceptions | [Vulnerability Ledger](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E6%BC%8F%E6%B4%9E%E5%8F%B0%E8%B4%A6.md) | [metratio.com Infrastructure Documentation](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/metratio.com%20%E5%9F%BA%E7%A1%80%E8%AE%BE%E6%96%BD%E6%96%87%E6%A1%A3.md) |
| Dify console and Docker troubleshooting | [Dify Console API Login](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/Dify%20%E6%8E%A7%E5%88%B6%E5%8F%B0%20API%20%E7%99%BB%E5%BD%95.md) / [Docker Troubleshooting](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/Docker%20%E6%8E%92%E9%9A%9C.md) | [Environment Operations Manual](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%8E%AF%E5%A2%83%E8%BF%90%E7%BB%B4%E6%89%8B%E5%86%8C.md) |
| Recording evidence, decisions, actions, outcomes, revisions, and lifecycle | [Responsibility Record Plane](09-responsibility-record-plane.md) | [Daily Notes Template](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E6%AF%8F%E6%97%A5%E7%AC%94%E8%AE%B0.md) |
| Current projects, development plans, and project progress | [E-commerce Workflow Project](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%94%B5%E5%95%86%E5%B7%A5%E4%BD%9C%E6%B5%81%E9%A1%B9%E7%9B%AE/README.md) | [Development Plan](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%94%B5%E5%95%86%E5%B7%A5%E4%BD%9C%E6%B5%81%E9%A1%B9%E7%9B%AE/%E5%BC%80%E5%8F%91%E8%AE%A1%E5%88%92.md) / [Current Progress](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E7%94%B5%E5%95%86%E5%B7%A5%E4%BD%9C%E6%B5%81%E9%A1%B9%E7%9B%AE/%E5%BD%93%E5%89%8D%E8%BF%9B%E5%BA%A6.md) |
| Model routing | [Model Routing](https://github.com/ratiolin/ratio/blob/main/%E8%B4%A3%E4%BB%BB%E6%8B%93%E6%89%91/%E6%A8%A1%E5%9E%8B%E8%B7%AF%E7%94%B1) | |

## IX. Competition and Migration

Maintain:

$$
\boxed{
\text{competition}\neq\text{migration}
}
$$

A challenger expressed in a different language may keep its own ontology, codec, state structure, and internal representation. It gains standing to challenge without first being mapped into current canonical IDs; otherwise V1 would use its own language circularly to prove itself irreplaceable.

Only when a challenger is ready to enter current routing, replace a component, or federate with the current framework does it enter migration. At that point, at minimum, one must address:

1. the affected definitions, owners, imports, callers, interfaces, and records;
2. semantics that can be preserved, or must be transformed, narrowed, merged, decomposed, or retired;
3. unmigrated content and historical traceability;
4. routing switch-over and revalidation.

Therefore:

$$
\boxed{
\text{semantic mapping}
=\text{migration requirement}
\neq\text{competition admission requirement}
}
$$

Open research on cross-framework correspondence, architecture genesis, evaluator sensitivity, and related topics is not a V1 completion condition and remains in the non-canonical research workspace.

## X. Conflict, Maintenance, and the V1 Change Gate

When multiple versions of the same term, procedure, or fact appear, first determine whether the item is a definition, specialization, boundary reference, handoff, procedure, representation, or current fact; then return to the corresponding owner. MOCs, genesis narratives, conversation summaries, old snapshots, and duplicate formulations must not override canonical owners.

After release, a core document may be changed only if at least one of the following holds:

1. a cross-module public canonical meaning changes;
2. an owner, specialization, or handoff boundary changes;
3. failing to address the issue would make a real-world failure impossible to locate, reopen, or hand off;
4. a real cross-document compatibility error or contradiction is being repaired.

If none of the four applies:

$$
\boxed{\text{do not modify V1}}
$$

Research notes may be recorded, candidates added, domain models supplemented, and failure cases accumulated, but the core remains closed by default.

When modifying, at minimum check:

- whether each canonical ID still has exactly one owner;
- whether `imports.from` and `mode` remain correct;
- whether document-local vocabulary has been accidentally promoted to a platform API;
- whether the Control Plane has become a reverse definitional dependency of theory;
- whether situational facts, domain thresholds, or runtime configuration have entered stable theory;
- whether counterexamples, failure conditions, reopening, handoff, and stop exits still exist.

Framework V1.0 changes its default phase from “continue refining” to:

$$
\boxed{
\text{use}
\rightarrow
\text{accumulate failure cases}
\rightarrow
\text{revise when necessary}
}
$$
