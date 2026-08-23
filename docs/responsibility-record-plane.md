---
document_type: specification
document_status: stable
framework_version: 1.0.0
knowledge_scope: specification
evidence_basis: specification
external_evidence: required-for-domain-claims
aliases:
  - Evidence Semantics
  - Evolution Semantics
  - Evidence and Change Semantics
  - Evidence Semantics Specification
tags:
  - semantics
  - evidence
  - evolution
  - control-plane
spec_version: framework-v1-interface-1.0.0
spec_status: stable-interface
control_plane_schema_pin: official-1.0.0
control_plane_schema_successor_draft: 1.1.0-draft
runtime_implementation_milestone: R2.0
runtime_protocol: "2.0"
owner: metra
updated: 2026-08-20
last_verified: 2026-08-23
verification_method: Manual alignment of the Framework V1.0 fixed record interface with the Control Plane schema official-1.0.0 pin; no claim that 1.1.0-draft has passed runtime acceptance
revision_basis: framework-v1-control-plane-pin-2026-08-20
semantic_contract:
  role: canonical-definition
  defines:
    - record_type
    - epistemic_status
    - lifecycle
    - record_relation
    - record_field_semantics
    - revalidation_semantics
  imports:
    - concept: distinction
      from: Finite Change Theory
      mode: represent
    - concept: factor
      from: Finite Change Theory
      mode: represent
    - concept: organization_structure
      from: Finite Change Theory
      mode: represent
    - concept: orientation
      from: Finite Change Theory
      mode: represent
    - concept: judgment
      from: Finite Change Theory
      mode: represent
    - concept: action
      from: Finite Change Theory
      mode: represent
    - concept: structure_candidate
      from: Cross-Domain Structure Candidates
      mode: reference
    - concept: change_procedure
      from: Finite Change Practice
      mode: represent
  excludes:
    - truth_definition
    - causal_methodology
    - normative_legitimacy
    - domain_evidence_standards
    - operational_configuration
    - theory_definition
    - practice_definition
---

# Responsibility Record Plane

> **Knowledge and evidence boundary:** This document is the cross-cutting record-semantics specification for the personal platform. It specifies how evidence, assertions, goals, constraints, experiments, decisions, actions, outcomes, revisions, and their states and relations are represented by machines, traced, checked for invalid states, and used to trigger revalidation. Record completeness does not prove truth; completion of a procedure does not prove legitimacy of a decision; occurrence of an outcome does not prove causal attribution; official status does not prove the reasonableness of a purpose.

> **Normative status in Framework V1.0:** Runtime record semantics are pinned to the accepted Control Plane schema `official-1.0.0`. This document is the stable Framework V1.0 interface description for theory and practice. It does not promote the unaccepted `1.1.0-draft` to official status. If this text conflicts with the concrete tokens or implementation semantics of the running `official-1.0.0`, the accepted `official-1.0.0` prevails until independent re-acceptance is completed.

## Definition dependencies

This document owns the Framework V1.0 definitions for the record interface: `record_type`, epistemic status, lifecycle, record relations, common fields, and revalidation semantics.

It only **represents** distinction, factors, organization, orientation, judgment, and action from [Theory of Determinative Responsibility](theory-of-determinative-responsibility.md); it does not redefine them. It records procedural facts from [Action Responsibility Practice](action-responsibility-practice.md) but does not define the practice procedure. It only references structure candidates from the [Responsibility Structure Candidate Catalog](responsibility-structure-candidate-catalog.md), and does not rewrite an epistemic "structure candidate" as the Record Plane lifecycle state `candidate`. Theory / Practice do not import this specification's tokens in the reverse direction.

This document is not responsible for theories of truth, statistical or causal methodology, value ranking, the normative legitimacy of authorization, domain evidence standards, privacy or legal criteria, current project ports, commands, scheduled tasks, database layouts, or runtime topology. Those belong to project READMEs, code, and RUNBOOKs.

## I. Cross-cutting position and purpose

The Responsibility Record Plane is not a downstream stage of [Action Responsibility Practice](action-responsibility-practice.md). It cuts across research, experiments, project changes, runtime incidents, rule promotion, and real-world action, providing common record semantics to different processes.

The minimum objectives of this specification are:

1. state what is being recorded;
2. state how strongly a proposition is currently supported;
3. state what processing stage an object is in;
4. make provenance, version, scope, authorization, outcomes, and revisions traceable;
5. prevent old conclusions from migrating unconditionally after the environment or object changes;
6. refuse to compress different semantic dimensions into a single status;
7. make it possible to reconstruct judgment from primary records without silently reifying "judgment" into a new object with independent truth value or authorization force.

## II. Three orthogonal dimensions

Object type answers **what is recorded**; epistemic status answers **to what degree a proposition is currently supported**; lifecycle answers **what processing stage the object is in**. The three must be stored independently.

### 1. Object types

| Type | Minimum definition |
|---|---|
| `EvidenceArtifact` | Traceable material such as logs, test output, screenshots, files, API responses, measurements, or human reports |
| `Observation` | A record, at a specified time, location, method, and scope, of differences acquired through senses, instruments, or classification channels |
| `Assertion` | A proposition that can be supported, refuted, contested, or remain unknown; `Claim` and `Hypothesis` serve different uses |
| `Derivation` | The process of obtaining a conclusion from premises, evidence, and rules of reasoning; `Inference` is represented this way |
| `Goal` | An orientation / goal representation endorsed, undertaken, or assigned by a particular subject or institution, with direction, concrete target, and completion criterion kept distinguishable |
| `Constraint` | A boundary statement by a subject, institution, technical specification, or domain model about allowed actions, states, transitions, or outcomes; a real-world limitation does not thereby become a directly registrable object |
| `Experiment` | A planned change and observation arranged to distinguish hypotheses, evaluate candidates, or validate a revision |
| `Action` | An operation actually executed under real conditions and authority |
| `Decision` | A choice made under purposes, authority, evidence, and uncertainty |
| `Policy` | A persistent constraint on subsequent actions of the same class |
| `Outcome` | A record of a real result appearing in a specified scope after an action, revision, or environmental change |
| `Revision` | A versioned modification to a rule, configuration, code, data, model, purpose, boundary, or other object |
| `ChangeObject` | An object, and its version, that is modified, verified, promoted, rolled back, or retired |

Both `Claim` and `Hypothesis` are kinds of `Assertion`; `Inference` is represented by `Derivation`. A factual `Claim` may be read as `supported` only where proportionate evidence supports it within an explicit scope.

Statements about allowed states, excluded paths, bottlenecks, limiting factors, or mechanisms remain `Assertion` / `Derivation` records or domain-model content. They must be bound to an object, scope, model, evidence, alternative explanations, and invalidation conditions. A real-world limitation is not an ontological object that becomes "known" merely because its record is complete.

### 2. "Judgment" is not a `record_type`

The canonical definition of judgment belongs to [Theory of Determinative Responsibility](theory-of-determinative-responsibility.md). In the Responsibility Record Plane, judgment is the current integrated reading of existing `Assertion`, `Derivation`, `Goal`, `Constraint`, evidence, unknowns, and other records.

If that integration changes subsequent real-world action, create a separate `Decision` and record authorization relations explicitly. Do not add a `Judgment` record type in order to bypass this boundary.

### 3. Epistemic status

| Status | Meaning |
|---|---|
| `unverified` | Proposed or recorded, but proportionate validation has not yet been completed |
| `supported` | Supported by proportionate evidence within the current declared scope |
| `contested` | Unresolved conflicting evidence or interpretations exist |
| `refuted` | Negated by proportionate evidence within the declared scope |
| `unknown` | Current evidence is insufficient to support or refute; this may be within-model insufficiency or incompleteness of the possibility space |
| `revalidation-required` | Changes in dependencies, versions, distributions, objects, or environment mean old evidence cannot be migrated directly |

`Assertion` carries proposition-level `epistemic_status`. `Observation` may use the same field to record the quality / epistemic status of the observation record itself, but this does not mean a proposition about the observed object has been supported or refuted. `Derivation` stores the source of reasoning, premises, rules, and conclusion references; it does not carry the conclusion's `epistemic_status`. The status of the conclusion remains on the referenced `Assertion`. Whether evidence is proportionate is decided by the measurement, sampling, statistical, experimental, causal, or other professional standards of the relevant domain; this specification records those judgments and their bases.

`supported`, `verified`, `official`, `authorized`, and "currently defensible" are different semantics:

- `supported`: a proposition is currently supported by evidence within scope;
- `verified`: specified procedures and acceptance criteria have been satisfied;
- `official`: the object is at an official lifecycle stage;
- `authorized`: a valid grant of authority exists;
- currently defensible judgment: still requires integration of purposes, constraints, unknowns, and consequences.

They must not substitute for one another.

### 4. Lifecycle

Different object types use different lifecycles. There is no unified state machine covering all objects.

```text
Assertion
draft → current → superseded → archived

Revision
proposed → authorized → applied → verified
                                  ├→ accepted
                                  ├→ rejected
                                  └→ rolled-back

Policy, Skill, or persistent rule
draft → candidate --promote--> official → deprecated → archived
```

In this specification, `candidate` is a lifecycle state of a `Policy`, Skill, or persistent rule. It is not a `record_type`, and it is not the same as the epistemic "structure candidate" in the [Responsibility Structure Candidate Catalog](responsibility-structure-candidate-catalog.md).

Public release, broad acceptance, entry into `official`, or long-running operation establishes only facts about dissemination, adoption, or lifecycle. Truth, legitimacy of purpose, effectiveness of action, independent uptake by a community, and conditions of affected parties still require independent evidence.

Time-limited authorization, exceptions, and emergency rules must preserve validity scope and expiry. Continued application after expiry is a new decision and must not be silently renewed.

Epistemic results may remain `unknown` indefinitely, but candidates that enter an execution or official-rule lifecycle must receive a disposition within a bounded period. At expiry they must at least enter one of `promote`, `narrow`, `reject`, `archive`, or `escalate`; "insufficient evidence" cannot become an indefinitely deferred lifecycle status.

Where applicable, a candidate object should define in advance: `trial_deadline`, `budget_limit`, `exposure_limit`, `success_conditions`, `failure_conditions`, `safety_stop_conditions`, `minimum_evidence`, `promotion_requirements`, and `default_disposition`.

## III. Type-specific states and verification semantics

| `record_type` | Primary status question | Main lifecycle | Minimum verification semantics |
|---|---|---|---|
| `Assertion` | supported / refuted / unknown / contested | draft → current → superseded → archived | Evidence supports or refutes within the declared scope |
| `Action` | Did it occur, exceed authority, or complete? | recorded → verified | Real evidence consistent with the execution boundary; an action that occurred cannot be rewritten as "did not occur" |
| `Decision` | Was it made, was the procedure valid, are its reasons defensible? | draft → current → superseded | Authorization / procedure are separate from legitimacy |
| `Outcome` | Was it recorded, independently confirmed, and is attribution established? | recorded → confirmed → superseded | Outcome is not attribution |
| `Goal` | Source, endorsement status, completion | proposed → current → superseded | Endorsement is not authorization or legitimacy |
| `Constraint` | Scope, type, whether non-compensable | Normative / technical rules may use the persistent-rule lifecycle; empirical constraint models are treated as Assertions | A model is not the real limitation itself |
| `Revision` | Before/after versions, authorization, verification, rollback | proposed → authorized → applied → verified | Complete version lineage |

Rolling back an `Action` cannot delete the original action or rewrite it as never having occurred. Instead, connect a new compensating `Action`, `Revision`, or restored `ChangeObject` version.

## IV. Core relations and minimum evidence chain

| Relation | Minimum meaning |
|---|---|
| `records` | Material carries an observation |
| `supports` | A record supports an assertion within its declared scope |
| `contradicts` | A record conflicts with the content, scope, or conditions of an assertion |
| `derived-from` | Identifies premises, evidence, and reasoning from which a conclusion was obtained |
| `tests` | An experiment tests a hypothesis or revision |
| `authorizes` | A decision grants explicit authority for an action or revision |
| `produces` | An outcome appears after an action or revision; this does not automatically mean causation |
| `revises` | A revision connects before and after versions of an object |
| `supersedes` | A new record replaces an old record for current use while retaining the old record |
| `requires-revalidation` | A change means an existing conclusion cannot continue to apply directly |

The Portable Runtime canonical relation set does not contain `causes`. Domain attribution may enter as external / domain records, or as the content of an `Assertion` / `Derivation`. The runtime creates only observable relations such as `produces`; it does not automatically promote temporal succession, co-variation, one successful event, or repeated correlation into causation.

A typical evidence chain is:

```text
EvidenceArtifact
→ records Observation
→ supports / contradicts Assertion
→ Experiment tests Hypothesis or Revision
→ Decision authorizes Revision / Action
→ Action / Revision produces Outcome
→ Outcome supports / contradicts later Assertions
→ Decision promotes / narrows / rejects / rolls back / archives
→ later change requires-revalidation
```

Feedback, correction, and revision must remain distinct: feedback means an outcome re-enters a later process; correction means that a structure or action changes because of it; `Revision` records only that a versioned modification occurred.

## V. Minimum common fields

```yaml
id:
record_type:
created_at:
created_by:
system_boundary:
scope:
source_refs:
epistemic_status:
lifecycle_status:
environment_versions:
verification_refs:
supersedes:
```

For an `Assertion`, `epistemic_status` represents proposition status; for an `Observation`, it represents observation-record quality. `Derivation` does not carry the conclusion's state. `Action`, `Decision`, `Outcome`, and other types use their type-specific state fields and must not be forced into `supported / refuted`.

`system_boundary` states whether the record belongs to an instance, project, harness, platform, or organization. `scope` specifies object, task, time, and applicability. `environment_versions` binds model, code, data, tool, rule, classification, or evaluator versions that may affect migration of the conclusion.

Optional semantic fields:

```yaml
assumptions:
known_limitations:
unknown_scopes: []
possibility_space_ref:
invalidation_conditions:
valid_from:
expires_at:
review_triggers:
execution_status:
decision_status:
confirmation_status:
direction_origin:
goal_owner:
beneficiary_refs: []
acceptance_status:
completion_criteria:
participant_refs:
  proposers_researchers: []
  users_maintainers: []
  authorizers_responsible: []
  direct_beneficiaries: []
  risk_cost_bearers: []
  excluded_constrained_irreversibly_affected: []
```

When `epistemic_status: unknown`, `unknown_scopes` may distinguish `within-model` from `model-incomplete` as needed. `possibility_space_ref` binds the versioned definition of the current objects, classifications, variables, states, and path space. Neither field may be interpreted as a complete description of real possibility.

For `direction_origin`, at least distinguish `self-recognized`, `jointly-negotiated`, `delegated`, `externally-assigned`, and `functional-reference`. A task that was assigned does not automatically become a subject's own purpose merely because it was recorded as a `Goal`.

`participant_refs` is for cases of substantial publicization, adoption, authorization, or external impact. Proposers, maintainers, authorizers, beneficiaries, and risk bearers may overlap, but their positions must be recorded separately; the existence of one group cannot automatically serve as evidence for another.

## VI. Inviolable rules

1. Materials, observations, assertions, and interpretations must remain separate. An observation includes the mediation of input and classification; causes and mechanisms require a separate `Assertion` / `Derivation`.
2. `Outcome` represents only the result. Without an attribution procedure, do not write that an action "caused" the outcome.
3. Every record must specify object type, system boundary, applicability scope, and relevant status. Important unknowns must not be disguised as certainty with default values.
4. `Revision` must connect before and after versions and preserve a proportionate route for verification.
5. Promotion of a candidate requires both verification evidence and valid authorization; an evaluator or evaluated object may not lower the standard without a record.
6. Non-compensable boundaries involving authority, data integrity, safety, third-party rights, or domain hard constraints cannot be offset by total scores or average gains.
7. When models, classifications, state spaces, problem definitions, code, data, tools, evaluators, task distributions, permissions, or environments change materially, related conclusions must enter `revalidation-required` or have their scope narrowed.
8. New records replace old records through versioning and `supersedes`; they must not silently overwrite them.
9. Completion of approval, review, or compliance procedures proves only that the corresponding procedure occurred. Risk control, achievement of purpose, and real effectiveness require separate outcome evidence.
10. Metrics, standards, evaluators, supervision rules, and exit mechanisms are themselves revisable, verifiable, and retireable objects.
11. Valid assertions about impossible states, bottlenecks, excluded paths, or mechanisms must be bound to object, scale, model, execution / measurement conditions, alternative explanations, and invalidation conditions.
12. Claims that a structure has been publicized, adopted, or authorized must distinguish epistemic acceptance, real maintenance, valid authorization, and conditions of affected parties.
13. Lifecycle `candidate` and epistemic "structure candidate" must remain in distinct namespaces.
14. An official version must not retain wording such as "candidate," "trial," or "pre-promotion" when that wording conflicts with its own status.

## VII. Revalidation semantics

At minimum, check whether the following changes trigger `requires-revalidation`:

- changes in evidence sources, sensors, or measurement methods;
- changes in object boundary, classification, state space, or scope;
- changes in model, data, code, tool, or evaluator versions;
- changes in environmental distribution, critical dependencies, or authority conditions;
- old assumptions broken by new observations, anomalies, or counterexamples;
- material changes in record-aggregation logic or read-projection rules.

Revalidation is not a matter of simply marking an old record `supported` again. It asks whether old evidence can still migrate to the new object, scope, and environment. If it cannot, preserve the old record's history and build a new evidence chain for the new scope.

## VIII. Mapping to Finite Change Practice

Practice stages may have the following common mappings to record semantics, but this is a read/write convenience, not a dependency hierarchy:

| Practice stage | Common record objects and relations |
|---|---|
| Reality and purpose | `EvidenceArtifact`, `Observation`, `Assertion`, `Goal` |
| Conditions and authority | `Constraint`, `Decision`, `authorizes` |
| Options and strength | `Experiment`, `Revision`, `Policy` |
| Execution and recording | `Action`, execution evidence |
| Verification and correction | `Outcome`, `supports` / `contradicts`, `Revision` |
| Persistence and exit | `Decision`, lifecycle transitions, revalidation, retirement |

Practice concepts such as "situation" or "procedure profile" do not thereby automatically become `record_type`s. If implementation needs to read them, represent them through existing records and derived views unless a later independent proposal shows that the existing types are insufficient.

## IX. Implementation boundary and acceptance

The implementation layer must comply with these semantics, but storage table names, file layouts, APIs, agent commands, scheduled tasks, health ports, model routing, network policies, concrete verifiers, and runtime states belong to the [control-plane project README](https://github.com/ratiolin/control-plane/blob/main/README.md), code, tests, CI, and RUNBOOKs; they are not duplicated here.

At minimum, an implementation should be able to:

1. store and validate the orthogonality of object type, epistemic status, and lifecycle;
2. connect the core evidence and version relations;
3. reject observations without provenance, revisions without before/after versions, and promotions without verification or authorization;
4. propagate revalidation requirements after material environmental or object changes;
5. preserve failure, rejection, rollback, and compensation history;
6. enforce deadlines, exposure, budget, verifier, and default-disposition constraints for candidates;
7. ensure that every derived reading is traceable to primary records and has no automatic authorization force;
8. avoid adding case-specific ontological fields merely to bypass the public semantics.

If a later Control Plane version is to enter Framework V1.x or V2, it must independently pass compatibility and runtime acceptance. Merely adding read models, convenience fields, or implementation projections does not automatically require theory and practice to be reissued. A framework compatibility review is triggered only when the public record semantics themselves change incompatibly.
