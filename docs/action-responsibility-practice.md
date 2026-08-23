---
document_type: practice
document_status: stable
framework_version: 1.0.0
knowledge_scope: methodology
evidence_basis: original-method
external_evidence: required-for-domain-claims
updated: 2026-08-20
revision_basis: framework-v1-practice-reliability-handoff-2026-08-20
semantic_contract:
  role: canonical-definition
  defines:
    - change_procedure
    - procedure_profile
    - hard_procedure_trigger
    - six_stage_change_cycle
    - residual_responsibility
    - minimum_change_record
    - persistent_system_governance_check
  imports:
    - concept: distinction
      from: Finite Change Theory
      mode: operationalize
    - concept: factor
      from: Finite Change Theory
      mode: operationalize
    - concept: organization_structure
      from: Finite Change Theory
      mode: operationalize
    - concept: orientation
      from: Finite Change Theory
      mode: operationalize
    - concept: judgment
      from: Finite Change Theory
      mode: operationalize
    - concept: action
      from: Finite Change Theory
      mode: operationalize
    - concept: correction
      from: Finite Change Theory
      mode: operationalize
    - concept: open_closure
      from: Finite Change Theory
      mode: operationalize
    - concept: candidate_generation
      from: Finite Intelligence
      mode: operationalize
    - concept: structural_tension
      from: Finite Intelligence
      mode: operationalize
    - concept: directional_revision_candidate
      from: Finite Intelligence
      mode: operationalize
    - concept: epistemic_action
      from: Finite Intelligence
      mode: operationalize
    - concept: epistemic_material_acquisition
      from: Finite Intelligence
      mode: operationalize
    - concept: open_validation
      from: Finite Intelligence
      mode: operationalize
    - concept: revision_depth_judgment
      from: Finite Intelligence
      mode: operationalize
    - concept: finite_reflexivity
      from: Finite Intelligence
      mode: operationalize
    - concept: counterfactual_construction
      from: Finite Intelligence
      mode: operationalize
    - concept: cognitive_search_allocation_judgment
      from: Finite Intelligence
      mode: operationalize
    - concept: cognitive_frontier
      from: Finite Intelligence
      mode: operationalize
    - concept: selective_consolidation
      from: Finite Intelligence
      mode: operationalize
    - concept: structure_candidate
      from: Cross-Domain Structure Candidates
      mode: reference
    - concept: correction_loop
      from: Finite Civilizational Reliability
      mode: operationalize
    - concept: fault_containment
      from: Finite Civilizational Reliability
      mode: operationalize
    - concept: rate_compatibility
      from: Finite Civilizational Reliability
      mode: operationalize
    - concept: effective_reversibility
      from: Finite Civilizational Reliability
      mode: operationalize
    - concept: reauthorization_structure
      from: Finite Civilizational Reliability
      mode: operationalize
    - concept: civilizational_maneuverability
      from: Finite Civilizational Reliability
      mode: operationalize
  excludes:
    - theory_redefinition
    - domain_specific_thresholds
    - record_schema
    - operational_facts
---

# Action Responsibility Practice

> **Knowledge and evidence boundary:** This document operationalizes the analytical language of [Theory of Determinative Responsibility](02-theory-of-determinative-responsibility.md) into procedures for action, so that an endorsed or undertaken change can be executed, verified, stopped, recovered, narrowed, reopened, or exited. It does not redefine theoretical concepts, nor does it substitute for legal, medical, safety, engineering, organizational, or other professional standards. Concrete mechanisms, thresholds, intervention effects, and boundaries of rights belong to domain models, fact owners, and professional norms.

## Definition dependencies

This document owns the definitions of the action procedure for finite change, procedure profiles, hard procedure triggers, the six-stage change cycle, residual responsibility, the minimum change record, and the supplementary governance check for persistent systems.

The open / closure distinction from [Theory of Determinative Responsibility](02-theory-of-determinative-responsibility.md), and candidate generation, structural tension, directional revision candidates, counterfactual construction, cognitive search allocation judgment, the cognitive frontier, epistemic action, material acquisition, open validation, revision-depth judgment, and selective consolidation from [Theory of Cognitive Responsibility](03-theory-of-cognitive-responsibility.md), are only **operationalized** here. The [Responsibility Structure Candidate Catalog](06-responsibility-structure-candidate-catalog.md) is used only as a source of candidate questions; [System Responsibility Reliability](07-system-responsibility-reliability.md) provides diagnostic dimensions for long-horizon systems. When machine recording is needed, responsibility is handed off to the [Responsibility Record Plane](09-responsibility-record-plane.md); this document does not depend on its specific record tokens.

## I. Scope and procedure strength

This practice is mainly for actions that change persistent states, official records, shared resources, other people's situations, long-term dependencies, or the future option space. Low-risk and easily recoverable matters may use a simplified procedure; high-impact, hard-to-recover matters, or matters involving third-party rights, must use stronger procedure.

### 1. Procedure profiles

Procedure profiles are predefined procedural packages. They do not compress risk into a single total score.

| Profile | Typical use | Minimum procedure |
|---|---|---|
| `minimal` | Narrow impact, easy recovery, no major third-party impact | Specify object and purpose, execution boundary, outcome confirmation, and stop-on-failure conditions |
| `standard` | Creates persistent state, dependencies, official records, or moderate failure cost | Add alternative options, proportionate evidence, authority, verification, rollback, and review |
| `enhanced` | High impact, tight coupling, persistent operation, difficult recovery, or significant effects on others | Add independent verification, role separation, dissent, exposure limits, takeover, recovery, and exit governance |

A profile may be escalated as new information appears. Low-risk factors cannot offset a non-compensable boundary.

### 2. Hard triggers

If any of the following applies, the procedure must be raised directly to the proportionate minimum level:

- major third-party rights, bodily safety, privacy, or non-compensable interests may be affected;
- the source of authority is unclear, the authorization scope is disputed, or the executor may be self-authorizing;
- a key change is irreversible or the real recovery path is unclear;
- power is highly asymmetric, exit capacity is weak, or affected parties have difficulty expressing dissent;
- errors may replicate, spread, lock in, or propagate across systems rapidly;
- the action depends on critical infrastructure, finite public resources, or highly concentrated data, standards, or interfaces;
- the verifier, evaluation standard, default path, or stopping mechanism is unilaterally controlled by the executing system;
- domain standards explicitly require a stronger procedure.

### 3. Risk dimensions

Even when no hard trigger is hit, examine scope of impact, third-party rights, duration, irreversibility, uncertainty, dependency, structural sensitivity, replication and feedback gain, concentration of power, detectability, and difficulty of recovery. These dimensions are used to select procedure strength; they do not form a statistical formula that can compensate away hard constraints.

## II. Six-stage finite-change cycle

> **Reality and purpose → Conditions and authority → Options and strength → Execution and recording → Verification and correction → Persistence and exit**

The six stages are an action process, not an ontological structure and not a mechanically linear sequence. Any stage may return to an earlier stage for renewed distinction, organization, or judgment; real outcomes may force the entire problem to reopen.

### 1. Reality and purpose

At minimum, make explicit:

- the current object, scope, history, time scale, and the difference intended to be changed;
- the current object boundary, input channels, classifications, and included factors;
- what remains unknown, excluded, or only a candidate;
- who endorses the current direction, jointly negotiates it, accepts it by delegation, or assigns it externally;
- the state to be created or maintained, completion criteria, principal beneficiaries, and those who may bear losses;
- what new facts would require the goal itself to be reviewed.

Evidence materials, observations, factual assertions, inferences, candidate mechanisms, value judgments, and unknowns should remain distinguishable. For concrete record semantics, see the [Responsibility Record Plane](09-responsibility-record-plane.md). Where there is no explicit endorsement of purpose, one may describe a functional reference, stable tendency, or externally assigned task, but may not rewrite an observer's interpretation as the system's own purpose.

### 2. Conditions and authority

Check the time, knowledge, tools, bodily and attentional capacity, collaboration, resources, dependencies, maintenance, and recovery conditions required for the change. Also check whether there are prerequisite states, qualifications, interfaces, relationships, records, or time windows that must be obtained in advance or continuously maintained. Is a current absence something that can be supplied later, something whose delay merely adds cost, or something that will close a real path or materially raise later entry costs?

Authority must be specified independently:

- who proposes;
- who has decision authority;
- who executes;
- who verifies;
- who can require stopping, rollback, or escalation;
- what are the boundaries of the object, action, duration, external side effects, and redelegation.

Capability, technical feasibility, model recommendations, and historical success do not themselves constitute authorization.

### 3. Options and strength

Begin with the question: **what is the least that must change to achieve the purpose?** Prefer to limit the object, duration, authority, exposure, and resources. For important options, at least examine whether evidence for the key causal structure is proportionate; whether resources, capability, and authority are actually present; whether a non-compensable boundary is touched; whether the change can be verified, stopped, narrowed, recovered, or compensated; which future paths it opens, preserves, or closes; and what the lifecycle cost will be. For important intertemporal choices, distinguish immediate gains, cumulative gains, option-preservation value, switching cost, and lock-in risk. The current feasibility of a plan does not imply that future reconfiguration will remain cheap; preserving more options does not automatically make an option better than deeper current investment.

If the object, factors, causal structure, or key unknowns have not reached a degree of closure proportionate to the task, do not conceal upstream uncertainty with more detailed execution. Allocate proportionate epistemic activity instead.

#### Cognitive investment allocation

Using candidate generation, $\mathcal F$, $\Phi$, $\Lambda$, and the higher-order judgment responsibilities defined by [Theory of Cognitive Responsibility](03-theory-of-cognitive-responsibility.md), practice need only leave five explicit judgments:

1. **Current candidates and frontier:** which candidates have actually been formed, and which continue to be developed, held, or pruned; do not assume that ungenerated candidates already form a complete space.
2. **Determination and composition:** whether key candidates are individually clear enough; whether they are compatible when they must be combined; whether local representations, even when compatible, are sufficient for the current joint conclusion; and whether the retention standard required for cross-context comparison holds.
3. **Next path:** internal counterfactual construction, information lookup, tool use, introduction of other actors, or real-world exploration.
4. **Reason for selection:** which path is most likely to change the current judgment or expose structural error, and whether its cost and risk are proportionate.
5. **Epistemic stopping conditions and reflexive boundary:** when further search, or further checking of the current higher-order judgment itself, is unlikely to materially change the current epistemic judgment; why cognitive search can be stopped temporarily now; which unknowns and dissent remain; and what new materials, outcomes, or candidates would show that the stopping judgment was premature and trigger reopening.

**Epistemic closure is not an action gate.** Even if the current candidates, structures, and evidence are sufficient to stop further cognitive search, this does not by itself license real implementation. Action must still independently pass checks concerning purpose endorsement, conditions and authority, option strength, non-compensable boundaries, third-party impact, verification, stopping, recovery, and residual responsibility.

These are all current fallible judgments, not truth values produced automatically by a procedure. Internal counterfactuals do not substitute for real evidence. Where the current structure itself is highly doubtful, or where a low-cost, highly discriminating real test exists, new reality constraints should be obtained first. Finite reflexive review stops only in the current working sense and does not produce final correctness.

In an `enhanced` case, if the same system judges that further search is unnecessary and directly acquires, by virtue of that judgment, the qualification to advance a high-impact, hard-to-recover, or irreversible action, it should wherever possible introduce different material sources, different roles, or independent review, so as to avoid a closed loop in which sufficiency is self-defined and continuation is self-authorized.

#### Discriminative exploration

When epistemic action is needed, answer at least: which candidates actually need to be distinguished now; whether there is a real arrangement under current conditions that is both feasible and discriminating; what observation, experiment, pilot, boundary case, or minimal reproduction would make the candidates yield different expectations; what intervention is minimally sufficient under current authority, risk, and real-world cost; what result would reduce confidence in the current preferred structure or narrow its boundary; and whether apparently independent evidence actually shares a data source, evaluator, apparatus, or representation.

The objective of exploration is **discriminative information** relevant to current judgment and structural revision, not information maximization in general. In irreversible, non-compensable, or high third-party-impact settings, potential information value does not license greater exposure.

#### Fast experiment, slow promotion

Low-cost sandboxes, shadow runs, limited pilots, and staged exposure are allowed, but persistent rules, broad adoption, and high authority require evidence and authorization proportionate to the new scope. Support from one experiment does not automatically constitute structural promotion.

A non-compensable hard constraint cannot be tested by "allowing partial violation." Only implementation method, false-blocking rate, and execution cost may be tested.

### 4. Execution and recording

The executor acts only within the authorized scope and records actual actions, anomalies, external states, and abort conditions. Plans, model explanations, agent self-reports, and statements that a "task is complete" are only process materials.

If an action also performs material acquisition, record the real connection corresponding to $\mathcal Q$: the observed or measured object, channel, apparatus or data source, sampling conditions, time range, key transformations, and known defects. Judgments about real outcomes must be grounded in material acquisition and evidential-force judgments proportionate to the object boundary; an executing system's own report cannot substitute for them.

If overreach, serious risk, failure of a key condition, or loss of recovery capacity is discovered, pause, narrow, or escalate. Record implementation is handed off to the [Responsibility Record Plane](09-responsibility-record-plane.md). This document requires only that key facts remain traceable; it does not create a separate practice-state schema or depend on specific Control Plane tokens.

### 5. Verification and correction

Verification first distinguishes **material acquisition, the manner of distinction, and judgment of evidential force**. Process completion, disappearance of an alert, an increased model score, or the appearance of a log entry does not automatically prove that the real object changed in accordance with the completion criterion.

In a closed task, where the object boundary, factors, primary structure, and completion criteria are already proportionately fixed, use explicit verifiers such as tests, formal proofs, state constraints, dual records, or independent measurements.

In an open task, distinguish material acquisition, factor-forming distinction, and judgment of evidential force as in [Theory of Cognitive Responsibility](03-theory-of-cognitive-responsibility.md). When material acquisition itself must be analyzed explicitly, write:

$$
R_t
\xrightarrow{\mathcal Q_t}
E_t^{\mathrm{mat}}
\xrightarrow{D_t}
F_t
$$

Open validation then combines the current organizational process, structure, and candidates to judge the evidential force of the acquired material:

$$
V_{\mathrm{open}}:
(E_t^{\mathrm{mat}},\mathcal Q_t,D_t,F_t,\mathcal O_t,S_t,\ldots)
\rightarrow
J_t^E
$$

In practice, answer separately:

- **How was the material acquired?** What are the object, channel, apparatus, sampling, time range, transformation chain, and known defects?
- **How did distinction form factors?** How do the current object boundary, scale, comparison standard, classification granularity, and merge rules turn acquired content into factors $F$?
- **What is the evidential force of the material?** Which candidates does it currently support, weaken, discriminate between, or leave unresolved?
- **How do acquisition and distinction affect evidential judgment?** Are shared data sources, calibration, selection mechanisms, missingness, correspondence errors, classifications, or evaluators creating systematic blind spots?
- **What would overturn the current interpretation?** Is there a preserved route for counterevidence that could lower confidence in the current judgment?

Also identify the **location of deviation**: is the current conflict more plausibly in material acquisition $\mathcal Q$, distinction $D$, factor formation $F$, the organizational process or structure $\mathcal O/S$, or the evidential-force judgment $V$? Do not collapse these distinct failures into "model error."

The following must be maintained:

$$
E_t^{\mathrm{mat}}
\neq
J_t^E
$$

That is, evidence material is not the same as evidential force. The material-acquisition chain, distinction, factor formation, organizational process, organizational structure, and verifier itself can all become objects of revision.

#### Revision depth

After a deviation, anomaly, or new regularity appears, perform the operational checks corresponding to $\Gamma$:

1. Does the current material and evidential judgment most strongly support revising execution, judgment, organizational process $\mathcal O$, organizational structure $S$, factors $F$, distinction $D$, goal, material acquisition $\mathcal Q$, open validation $V$, or some other condition?
2. What competing attributions exist?
3. If only a local correction is made, what future result would show that the revision was too shallow?
4. If a deeper reorganization is made, what evidence would show that the revision was too deep?
5. Can a lower-cost, recoverable reproduction, verification, or exploration discriminate among these attributions?
6. Did the original problem incorrectly assume that several local determinations could all enter one global joint structure?
7. Does the executing system also control material acquisition, the evaluator, the record, or renewal, thereby forming a self-validating loop?

Correction must not default to parameter updates only, nor to total reconstruction. Real outcomes may require changing judgment, organizational process, organizational structure, factors, distinction, goal, execution, authorization, material acquisition, evidential-force judgment, or stopping method; they may also reopen a closed task. Where necessary, revise which local determinations may be combined and how they are combined.

If verification is impossible, unauthorized side effects appear, the verifier is contaminated, recovery conditions fail, or the current structure can be sustained only by accumulating exceptions, the action should be bounded, adjusted, paused, rejected, or reopened.

### 6. Persistence and exit

Passing verification means only that the current scope satisfies the current standard. It does not automatically legitimize expansion, long-term retention, or institutionalization.

The outcome must enter an explicit disposition: continue, expand, narrow, observe, recover, pause, retire, or reopen. Expansion requires new evidence and authorization proportionate to the added scope. Renewal is a new judgment and cannot be extended automatically on the basis of historical success.

Where experience must persist across time, preserve proportionate structures, applicability boundaries, key counterexamples, failed paths, verifier defects, rejected candidates, reopen signals, revision-depth judgments, and successful or unsuccessful search paths. The mechanism of selective consolidation is defined by [Theory of Cognitive Responsibility](03-theory-of-cognitive-responsibility.md).

## III. Cumulative consequences and persistent systems

After one cycle of change ends, examine whether it changes the next cycle's inputs, factors, organization, orientation, capabilities, relationships, power, and option space, and whether it creates new assets, dependencies, commitments, or complexity that must be maintained.

When similar changes recur, identify possible reinforcing or balancing loops, cycles, feedback delays, external costs, lock-in, and interruptible links. Related patterns appear in the [Responsibility Structure Candidate Catalog](06-responsibility-structure-candidate-catalog.md).

### Supplementary governance check for persistent systems

For persistent, high-impact systems, or systems likely to create material cumulative effects, answer at least the following as applicable:

1. Are purpose, authorization, and non-compensable boundaries explicit?
2. Are causal contribution, control capacity, benefit, risk bearing, and repair responsibility traceable?
3. Are there closed loops of self-authorization, self-verification, self-renewal, or inability to be externally terminated?
4. Are resources, data, infrastructure, standards, and exit control highly concentrated?
5. Are substitution, migration, takeover, and graceful-degradation paths real and usable?
6. What are the absolute totals, capacity thresholds, and recovery conditions of finite shared resources?
7. Can dissent enter formal records and trigger proportionate procedural change?
8. Are model and metric assumptions, blind spots, failed samples, anomalies, and invalidation conditions visible?
9. Are rollback, contraction, stopping propagation, transfer of responsibility, exit, and repair actually available?
10. Who maintains newly added governance complexity, how is it verified, and when is it revised or retired?

Also compare the time required to detect a deviation, form a judgment, and take action with the time window in which the deviation develops into unrecoverable damage. Sustained full load, repeated emergency response, or hidden depletion does not prove that a system has recovery or regenerative capacity.

#### Operational verification of reliability claims

When a plan claims that it "has backups," "can roll back," "can exit," "has dissent," "has independent verification," "can reacquire," or "is periodically reauthorized," the label itself is not evidence. At minimum, verify:

| Claim | Minimum operational check |
|---|---|
| Has backup | Does the backup share power, identity, keys, network, updates, knowledge base, or maintainers with the primary system? Can it start independently during failure? Has recovery actually been exercised? |
| Can roll back | Can software and data be reverted? Can real external consequences and third-party losses be restored? Does rollback authority actually exist? |
| Can exit | Is there a real alternative state? Can data, property, relationships, qualifications, and roles migrate? Does exit still require approval from the original controller? |
| Dissent exists | Can dissent enter formal handling and receive verification resources? Can it trigger review? Is the channel controlled unilaterally by the system being challenged? |
| Independent verification | Are data, metrics, personnel, funding, technical roots, and authorization genuinely independent? Can the result change execution? |
| Can reacquire | Can key knowledge, qualifications, tools, interfaces, permissions, and resources be rebuilt after a path closes? |
| Periodic reauthorization | What is the default state at expiry? Who bears the burden of proving renewal? Is renewal evidence independent? Are takeover and exit available if renewal fails? |

For recovery paths, also examine recovery keys, identity reconstruction, recovery knowledge, alternative supply chains, backup-system dependence on the failed system, and the minimum independent functions available during graceful degradation.

## IV. Value conflict and residual responsibility

An action procedure cannot automatically decide which way of life or which value should take priority. Factual correctness, procedural effectiveness, and satisfaction of outcome criteria do not eliminate value conflict.

Judgment should distinguish non-compensable boundaries from tradeable goals, and should state current and future affected parties, benefits, losses, opportunity costs, and qualifications to decide. Role reversal may reveal positional blind spots, but it does not substitute for rights boundaries, real evidence, actual participation, or valid consent.

**Residual responsibility** means that even where the reasons for action are sufficient and the procedure proportionate, irreducible losses may remain. Actors and governance structures should make the principal reasons public and preserve conditions for feedback, care, repair, compensation, appeal, and review. Completion of action does not mean the disappearance of responsibility.

Where action is necessary despite the absence of a complete recovery plan, narrow the object, duration, authority, and exposure. Where every available direction causes loss, choose the less intrusive option and explicitly assume the residual responsibility that remains.

## V. Minimum change record

This document specifies only what practice must be able to answer. Concrete fields and machine representation are handed off to the [Responsibility Record Plane](09-responsibility-record-plane.md). A `minimal` record may be reduced according to risk; `standard` and `enhanced` add progressively more detail.

An important change should at least answer:

1. **Object and boundary:** what are the object, location, identity, scope, scale, included factors, and key unknowns?
2. **Input, distinction, and evidence state:** how were real inputs acquired, how did distinctions form the current factors, and how are observations, factual assertions, judgments of evidential force, inferences, candidate structures, and value judgments distinguished?
3. **Orientation:** what is the goal, who endorses, undertakes, or assigns it, and what are the completion criteria?
4. **Structure and composition:** which key causal, value, authority, relationship, resource, and constraint structures are supported; what retention standard grounds cross-context correspondence; which local determinations are permitted to combine; and does the joint conclusion remain underdetermined?
5. **Roles and authority:** who proposes, decides, executes, acquires materials, judges evidential force, corrects, and stops?
6. **Procedure strength:** what is the current profile, which hard triggers apply, and what are the main risks?
7. **Option boundary:** what is the minimally sufficient plan, and what are its exposure, duration, resource, and authority boundaries?
8. **Verification and refutation:** how does $\mathcal Q$ acquire material, how do $D/F$ form current factors, how does $V$ judge evidential force, and what result would lower confidence in the current judgment?
9. **Correction and recovery:** what new material or evidential judgment would trigger revision at which level, and how would failure be rolled back, recovered, compensated, handed over, or exited?
10. **Persistence disposition:** when should continuation, expansion, narrowing, pausing, or retirement be reviewed?

Where changes repeat, accumulate, or involve structural reorganization, answer as applicable:

11. How does this cycle change the conditions of the next, and what feedback, lock-in, or external cost is being formed?
12. What is the current cognitive frontier, which candidates are held or pruned, and what are the reopen conditions?
13. Why is the next epistemic investment internal counterfactual construction, verification, tool use, or real exploration; when does continued search, or continued checking of higher-order judgment itself, become disproportionate; and what would trigger reopening?
14. What is the current revision-depth judgment and what competing attributions remain?
15. Which new structures, boundaries, counterexamples, failed paths, verifier defects, and negative knowledge should be consolidated, and which should not be hardened into long-term structure?

## VI. Domain handoff and the Control Plane

Concrete mechanisms and rights boundaries in bodily, psychological, relational, educational, labor, marriage and fertility, organizational and institutional, economic, software, safety, and other domains belong to the corresponding domain models. Where subjects are involved, preserve their conditions of expression, endorsement, refusal, and exit; the working boundary of subjectivity is defined in [Theory of Cognitive Responsibility](03-theory-of-cognitive-responsibility.md).

Specific rules for agent authority, project execution gates, tests, APIs, processes, monitoring, and recovery belong to the currently authoritative execution specifications of each project, such as the README, ADRs, `AGENTS.md`, skills, and RUNBOOKs.

[Action Responsibility Practice](08-action-responsibility-practice.md) answers **how to act**; the [Responsibility Record Plane](09-responsibility-record-plane.md) answers **how to represent, trace, and reject invalid record states**. The two are orthogonal. Practice may hand recording responsibility to the Record Plane, but it does not make the Record Plane schema a procedural definition dependency; complete records also do not prove that an action was correct, sufficiently authorized, or beneficial in outcome.
