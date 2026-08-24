---
document_type: research-context
document_status: active
framework_version: 1.0.0
knowledge_scope: comparative-theory
canonical_status: noncanonical
evidence_basis: framework-documents-and-external-literature
updated: 2026-08-24
semantic_contract:
  role: theory-competition-record
  defines: []
  imports:
    - concept: analysis_layers
      from: Theory of Determinative Responsibility
      mode: reference
    - concept: open_closure
      from: Theory of Determinative Responsibility
      mode: reference
    - concept: finite_intelligence
      from: Theory of Cognitive Responsibility
      mode: reference
    - concept: finite_system_strategic_interaction
      from: Theory of Interaction Responsibility
      mode: reference
    - concept: finite_value_genesis
      from: Theory of Value Responsibility
      mode: reference
    - concept: finite_civilizational_reliability
      from: System Responsibility Reliability
      mode: reference
    - concept: structure_candidate
      from: Responsibility Structure Candidate Catalog
      mode: reference
  excludes:
    - framework_definition
    - canonical_semantics
    - priority_claim
    - universal_novelty_claim
    - literature_exhaustion_claim
    - empirical_domain_claim
    - formal_proof_claim
---

# Theory Competition Map

> **Purpose:** This document records the strongest known neighboring research traditions for the theory layer of Responsibility Topology, where they already absorb a proposed contribution, where substantial overlap exists, and where a narrower residual may remain worth testing.
>
> **Status discipline:** This is a living, non-canonical research-context document. It does not redefine Framework V1.0, establish novelty, prove that a literature search is exhaustive, or authorize a new theory or formalization line. A theory claim survives competition only when the strongest available neighboring account cannot preserve the same material facts and decision consequences with equal or lower assumption cost.

## 1. Why a competition record is necessary

Responsibility Topology intentionally combines questions that are usually owned by different disciplines: epistemology, bounded rationality, machine learning, game theory, multi-agent systems, resilience engineering, safety engineering, formal methods, database provenance, authorization, AI assurance, value learning, and consciousness science. This makes the framework vulnerable to a specific false-positive pattern:

```text
new vocabulary
-/->
new problem
-/->
new explanatory structure
-/->
new decision consequence.
```

The framework should therefore treat neighboring work as active competition rather than as background citation.

The relevant unit of comparison is not terminology. It is the combination:

```text
problem
+ material facts preserved
+ assumptions required
+ explanatory consequence
+ decision / action consequence
+ empirical or formal discriminability.
```

A neighboring theory may absorb a Responsibility Topology claim even when it uses completely different names. Conversely, shared vocabulary does not establish absorption if the neighboring account cannot preserve the same responsibility-relevant distinctions.

The strongest competition should be applied first to the narrowest surviving residual. Broad statements such as “finite systems revise beliefs,” “multiple agents have different representations,” “systems need resilience,” or “history should be recorded” are not the main research target once mature neighboring accounts already cover them. The pressure should instead be placed on interfaces such as:

```text
historical support
-> current qualification
-> composition
-> authorization
-> continued reliance
-> revalidation
-> recovery.
```

## 2. Competition statuses

This document uses the following research statuses.

| Status | Meaning |
|---|---|
| **ABSORBED** | A mature neighboring account already captures the substantive problem and consequence without a material loss that has been demonstrated here. New terminology alone is not a residual. |
| **STRONG OVERLAP** | Neighboring work covers most of the problem; a narrower responsibility-specific interface may remain, but it has not yet earned a standalone theory claim. |
| **RESIDUAL CANDIDATE** | There is a precise remaining question that appears not to be automatically supplied by the strongest neighboring account and could produce a different evidence, qualification, or action boundary. It still requires hostile comparison. |
| **OPEN** | Competition is not sufficiently reconstructed to classify the claim. |

These are research-governance labels, not truth values.

## 3. Current summary

| Framework area | Strongest neighboring traditions | Competitive pressure | Current assessment | AI-development trajectory |
|---|---|---:|---|---|
| Determinative Responsibility | fallibilist epistemology; philosophy of science; TMS / belief revision; data provenance; authorization logics; systems/cybernetic reasoning | Very high | Broad meta-language is **STRONG OVERLAP**. Any residual must be narrower than belief change, provenance, or revocation and show a distinct transition between representation, qualification, authority, action, and revalidation | Meta-language alone becomes cheaper; decision-relevant transition rules become more valuable |
| Cognitive Responsibility | bounded rationality; resource-rational analysis; rational metareasoning; open-set/open-world learning; model-based diagnosis; diagnosability; model invalidation; active learning; scientific discovery | Very high | **STRONG OVERLAP**. The strongest residual candidate is not candidate generation or anomaly detection but entitlement to escalate from ordinary uncertainty/model mismatch to suspected representation inadequacy with downstream action consequences | Candidate generation becomes cheaper; epistemic qualification and reality contact become more valuable |
| Interaction Responsibility | games with unawareness; epistemic game theory; I-POMDPs; belief merging; judgment aggregation; assume-guarantee contracts; interface theories; multi-agent verification | Very high | **STRONG OVERLAP**. The residual candidate must survive direct competition from both aggregation theory and compositional verification: when may heterogeneous, time-varying local qualifications enter one action-bearing joint representation? | Strongly increasing value as heterogeneous agents become operational actors |
| Value Responsibility | preference learning; CIRL/assistance games; second-order preference and autonomy theories; moral psychology; affective science; AI consciousness/welfare research | Very high | Most broad value-formation claims face **STRONG OVERLAP**; the experience-status gate and the separation of regulation, experience, endorsement, and normative authority remain useful boundary disciplines | Moderate near-term value; potentially very high if AI welfare/subjectivity becomes operationally relevant |
| System Responsibility Reliability | resilience engineering; STAMP/STPA; fault tolerance; common-cause failure; runtime assurance/Simplex; corrigibility/interruptibility; continuous assurance; AI post-deployment monitoring | Very high | Broad resilience, monitoring, shutdown, and runtime-control claims are **STRONG OVERLAP**. The strongest residual candidate is the joint treatment of epistemic common capture, current qualification, reauthorization, continued reliance, and effective reversibility | Very strongly increasing value as action speed, autonomy, shared-model dependence, and deployment coupling grow |
| Structure Candidate Catalog | systems thinking; analogy/structure mapping; causal transportability; safety patterns; causal inference; reliability patterns; network science | Very high for individual patterns | Individual candidates are usually not novelty claims. The plausible residual is a research-governance discipline that limits escalation from common problem to formal similarity to mechanism similarity before migration evidence is earned | Increasing methodological value as AI accelerates cross-domain analogy generation |

## 4. Direct competitors to responsibility-bearing transitions

This section attacks the narrow interface hypothesis directly. Each competitor is evaluated against four questions:

```text
What does the competitor already solve?
Which Responsibility Topology shortcut or residual does it absorb?
Which material fact, if any, may remain outside it?
What theorem, case, or decision difference could distinguish the two?
```

### 4.1 Truth maintenance, belief revision, and dynamic epistemic change

Jon Doyle's Truth Maintenance System already records reasons for beliefs, revises the current belief set when assumptions are contradicted, supports dependency-directed backtracking, and uses recorded reasons to explain actions. AGM belief revision and its successors provide mature formal accounts of contraction, expansion, revision, iterated change, belief bases, and related update operations.

Representative sources:

- Jon Doyle, “A Truth Maintenance System,” *Artificial Intelligence* 12(3), 1979, 231–272. DOI: https://doi.org/10.1016/0004-3702(79)90008-0
- “Logic of Belief Revision,” *Stanford Encyclopedia of Philosophy*. https://plato.stanford.edu/entries/logic-belief-revision/

Direct pressure:

```text
historical reason exists
!=
currently held / currently accepted belief
```

and:

```text
new information or contradiction
-> revise / withdraw dependent conclusions
```

are not Responsibility Topology novelty claims by themselves.

Possible remaining material fact: Responsibility Topology separates a belief-like epistemic state from **qualification for a particular use**, authority to act, continued reliance, and revalidation responsibility. A proposition may remain recorded or even believed while no longer being qualified for a particular downstream use.

Discriminating test: construct a case in which TMS/AGM and Responsibility Topology agree on the belief content and historical reasons but disagree on whether a downstream use remains admissible because qualification, authority, or context has changed. If the rival can represent the same difference without an ad hoc external layer and reaches the same decision boundary, the residual shrinks.

Current status: **STRONG OVERLAP; residual only at cross-layer qualification/use transitions.**

### 4.2 Data provenance and lineage semantics

Database provenance and lineage already provide mature ways to represent which inputs, witnesses, or derivation paths support a result. Provenance semirings supply an algebraic framework that unifies several forms of why-provenance and lineage.

Representative source:

- Todd J. Green, Grigoris Karvounarakis, and Val Tannen, “Provenance Semirings,” PODS 2007, 31–40. DOI: https://doi.org/10.1145/1265530.1265535

Direct pressure:

```text
historical dependency;
derivation lineage;
alternative support paths;
why this result exists.
```

These are heavily occupied problems. Merely retaining historical dependency is not a sufficient residual.

Possible remaining material fact:

```text
provenance persistence
!=
current admissibility / qualification.
```

The same derivation lineage may persist while an input loses current qualification, an environment changes, a credential expires, a use becomes disallowed, or a revalidation obligation is triggered.

Discriminating test: hold provenance fixed while varying a current qualification or use condition. If a provenance system extended with ordinary metadata/policy captures the same withdrawal and revalidation decision without losing material facts, no separate theoretical object has been earned.

Current status: **STRONG OVERLAP on lineage; RESIDUAL CANDIDATE only for provenance-to-current-use transitions.**

### 4.3 Authorization logic, trust management, and revocation

Authorization research already treats permission as stateful, history-sensitive, and revisable. State-modifying authorization logics explicitly model requests that change authorization state and reason about sequences of access requests.

Representative sources:

- Mo Becker and Sebastian Nanz, “A Logic for State-Modifying Authorization Policies,” Microsoft Research, 2007 / IEEE INFOCOM 2010. https://www.microsoft.com/en-us/research/publication/a-logic-for-state-modifying-authorization-policies/
- Mo Becker, “Specification and Analysis of Dynamic Authorisation Policies,” IEEE CSF 2009. https://www.microsoft.com/en-us/research/publication/specification-and-analysis-of-dynamic-authorisation-policies/

Therefore:

```text
once authorized
-/->
still authorized
```

is not a residual by itself.

Possible remaining material fact: the framework may still need to connect authorization currentness to epistemic qualification, provenance, environment/context version, responsibility for revalidation, and continued reliance. Authorization logic normally owns the authorization state; it does not automatically establish why the supporting epistemic object is still qualified for the present use.

Discriminating test: compare two systems with the same authorization policy and nominal permission state but different epistemic qualification/provenance changes. If ordinary authorization logic can represent the needed validity guard and obtains the same decision, the Responsibility Topology residual is absorbed.

Current status: **STRONG OVERLAP; residual candidate only at epistemic-qualification/authorization composition.**

### 4.4 Assume-guarantee contracts and interface theories

Compositional verification and contract-based design directly study how local component assumptions and guarantees compose into system properties. Sound and complete assume-guarantee frameworks exist for component theories, and recent work applies quantitative contracts directly to multi-agent systems with local tasks and shared safety constraints.

Representative sources:

- Chris Chilton, Bengt Jonsson, and Marta Kwiatkowska, “Compositional assume–guarantee reasoning for input/output component theories,” *Science of Computer Programming* 91 (2014), 115–137. DOI: https://doi.org/10.1016/j.scico.2013.12.010
- Rafael Dewes and Rayna Dimitrova, “Contract-based Design and Verification of Multi-Agent Systems with Quantitative Temporal Requirements,” AAAI 2025. DOI: https://doi.org/10.1609/aaai.v39i22.34480

Direct pressure:

```text
local correctness
-/->
global correctness;

local guarantees
require
composition assumptions.
```

These are core contract/interface-theory concerns. Therefore “local qualification does not automatically compose” is not yet a residual.

Possible remaining material fact: Responsibility Topology's local qualifications may be evidence-dependent, context-indexed, use-indexed, time-varying, and authority-bearing rather than only behavioral/interface assumptions. A formally valid contract may continue to compose syntactically even after the evidence or authorization supporting one local assumption is no longer current.

Discriminating test: produce a case where ordinary contract verification succeeds under its declared assumptions but Responsibility Topology rejects composition because an assumption is no longer epistemically qualified or authorized for the current use. Then test whether the contract framework can encode the same validity condition without merely importing the Responsibility Topology distinction as another Boolean guard.

Current status: **VERY STRONG OVERLAP; this is a primary hostile competitor for Interaction Responsibility.**

### 4.5 Belief merging and judgment aggregation

Belief merging and judgment aggregation study how multiple individual belief or judgment bases can be combined into a collective result under consistency, integrity, rationality, and aggregation constraints. The literature includes impossibility results and distinguishes direct judgment aggregation from approaches that merge underlying evidence first.

Representative sources:

- “Belief Merging and Judgment Aggregation,” *Stanford Encyclopedia of Philosophy*. https://plato.stanford.edu/entries/belief-merging/
- Jon Williamson, “Aggregating Judgements by Merging Evidence,” *Journal of Logic and Computation* 19(3), 2009, 461–473. DOI: https://doi.org/10.1093/logcom/exn011

Direct pressure:

```text
local judgments
-/->
coherent collective judgment;

multiple evidence bases
require
an explicit merge rule.
```

These are mature problems. “Shared determination” cannot be promoted merely because multiple actors contribute local determinations.

Possible remaining material fact: a shared action-bearing determination may depend not only on merged belief content but also on authority, source qualification, heterogeneous representation, continued reliance, responsibility for revalidation, and discharge when one party's basis changes.

Discriminating test: hold the merged belief/judgment outcome fixed while varying authority or current qualification of one source. If the correct joint action/reliance decision changes and the merging framework has no native place for that change except an externally supplied constraint, a narrower residual may remain.

Current status: **STRONG OVERLAP; residual candidate only beyond belief/judgment aggregation into reliance, authority, and revalidation.**

### 4.6 Systems-theoretic safety, runtime assurance, and continuous assurance

STAMP/STPA treats safety as a systems-theoretic control and constraint problem rather than only a component-reliability problem. Runtime Assurance and Simplex architectures pair an advanced/untrusted component with runtime monitoring and a trusted reversionary path. Emerging continuous-assurance work seeks to connect design-time, runtime, and evolution-time evidence and to regenerate assurance arguments as system artifacts change.

Representative sources:

- Nancy Leveson and John Thomas, *STPA Handbook*. https://psas.scripts.mit.edu/home/get_file.php?name=STPA_handbook.pdf
- J. Tanner Slagel et al., “A Verification Framework for Runtime Assurance of Autonomous UAS,” NASA NTRS 20240007986, 2024. https://ntrs.nasa.gov/citations/20240007986
- Dhaminda B. Abeywickrama et al., “Towards Continuous Assurance with Formal Verification and Assurance Cases,” 2025 preprint. https://arxiv.org/abs/2511.14805

Direct pressure:

```text
monitor current behavior;
check safety constraints;
withdraw control from an unsafe advanced component;
retain a trusted fallback;
update assurance evidence as the system changes.
```

Generic monitoring, correction, runtime withdrawal, fallback, and evidence refresh are therefore not sufficient residuals.

Possible remaining material fact: Responsibility Topology may still contribute if it can expose **common epistemic capture** across nominally independent assurance positions and connect this to current qualification, authority duration, continued reliance, and effective reversibility. A monitor, fallback, reviewer, and assurance case can all appear separate while inheriting the same model/data/identity/organizational failure source.

Discriminating test: compare two architectures with identical nominal assurance stages but different failure-lineage independence. If Responsibility Topology requires a different deployment, admission, or recovery topology and existing safety/assurance methods do not capture the difference without additional provenance/independence assumptions, a residual remains.

Current status: **VERY STRONG OVERLAP; continuous assurance is an emerging direct competitor rather than a settled exhaustive theory.**

## 5. Determinative Responsibility

### 5.1 What the theory is trying to preserve

[Theory of Determinative Responsibility](theory-of-determinative-responsibility.md) provides a minimum-language layer around finite determination. Its important disciplines include:

```text
current determinability != ultimate structure of reality;
separately determinable -/-> jointly determinable;
jointly determinable -/-> local representations sufficient for joint structure;
fact -/-> norm;
technical executability -/-> authority or legitimacy;
current closure -/-> final closure.
```

It also separates the analytical responsibilities in:

```text
Reality -> Distinction -> Factors -> Organization -> Judgment -> Action -> New Reality.
```

### 5.2 Main competition

The broad intellectual territory is already densely occupied. Fallibilism, philosophy of science, model-based reasoning, cybernetics, decision theory, systems theory, truth maintenance, belief revision, provenance, and scientific methodology all contain versions of the following ideas:

- observations are mediated rather than direct copies of reality;
- current models and beliefs are revisable;
- representations can omit relevant structure;
- historical reasons can persist while current acceptance changes;
- local evidence does not automatically justify unrestricted generalization;
- action changes the environment from which later evidence is obtained;
- empirical adequacy and normative legitimacy are distinct questions.

Accordingly, the framework should not claim novelty from these propositions in isolation.

### 5.3 Current residual candidate

The strongest potential residual is not a new epistemology of fallibility, history, or revocation. It is a **responsibility-transition account** across domains that usually use different state spaces:

```text
Reality / evidence
-> representation
-> epistemic qualification
-> joint determination
-> authority
-> action
-> continued reliance
-> revalidation
-> recovery.
```

The research question is whether the transition conditions between these positions can be made sufficiently explicit to detect category errors that domain-local methods leave implicit.

Examples of prohibited shortcuts include:

```text
recorded -> true;
provenance exists -> currently qualified;
supported -> currently usable;
currently usable -> authorized;
locally supported -> jointly composable;
once authorized -> still authorized;
action succeeded -> model was adequate;
rollback interface exists -> rollback remains effectively reachable.
```

This remains a **RESIDUAL CANDIDATE**, not an established novelty claim. Section 4 materially raises the burden: the residual must survive belief revision, provenance, authorization, composition, aggregation, and assurance accounts, not merely broad philosophy-of-science comparison.

### 5.4 AI trajectory

As generative AI makes coherent conceptual systems and formal decompositions cheaper to produce, the scarcity value of a broad meta-language decreases. The value of Determinative Responsibility therefore depends increasingly on whether it constrains downstream transitions rather than whether it can redescribe them.

The strategic direction should be:

```text
less value in: more universal vocabulary;
more value in: explicit transition prohibitions, use qualification, and reopen conditions.
```

## 6. Cognitive Responsibility

### 6.1 Central problem

[Theory of Cognitive Responsibility](theory-of-cognitive-responsibility.md) distinguishes at least:

```text
within-model unknown
!=
incomplete candidate space;

not generated
!=
nonexistent;

currently unconstructible
!=
impossible;

candidate generation
!=
candidate qualification;

more material acquisition
!=
better distinction;

structural tension
!=
a proof that the current representation is wrong.
```

It also treats cognitive activity as resource-bounded and selectively allocated.

### 6.2 Strong competition: bounded and resource-rational cognition

Bounded rationality and rational metareasoning already study how finite agents allocate limited computation rather than performing unlimited inference. Resource-rational analysis explicitly models cognition as the use of limited computational resources and asks why particular cognitive mechanisms are selected under resource constraints.

Representative source:

- Falk Lieder and Thomas L. Griffiths, “Resource-rational analysis: Understanding human cognition as the optimal use of limited computational resources,” *Behavioral and Brain Sciences* 43 (2020), e1. DOI: https://doi.org/10.1017/S0140525X1900061X

Therefore, the following broad claims should be treated as **ABSORBED or STRONG OVERLAP** unless a more specific consequence is supplied:

```text
finite systems cannot compute everything;
search must be allocated;
computation itself has cost;
meta-level reasoning can decide which computation to perform next.
```

### 6.3 Strong competition: open-world and open-set recognition

Open-set recognition explicitly rejects the closed-world assumption that all test classes are known during training and formalizes the problem of unknown classes entering at deployment.

Representative source:

- Walter J. Scheirer, Anderson de Rezende Rocha, Archana Sapkota, and Terrance E. Boult, “Toward Open Set Recognition,” *IEEE TPAMI* 35(7), 2013. DOI: https://doi.org/10.1109/TPAMI.2012.256

This strongly overlaps with the framework's refusal to infer a complete candidate space from currently represented categories. However, open-set recognition usually starts from a machine-learning recognition problem, while Cognitive Responsibility asks a broader governance question about when a system is entitled to revise the object types, factor set, boundary, scale, or problem representation itself.

### 6.4 Strong competition: model-based diagnosis, diagnosability, and model invalidation

Model-based diagnosis has long studied how observations inconsistent with expected behavior can identify components or assumptions that explain a discrepancy. Discrete-event systems have mature notions of diagnosability under partial observation, and model invalidation methods ask whether observations are incompatible with a candidate model.

Representative sources:

- Raymond Reiter, “A Theory of Diagnosis from First Principles,” *Artificial Intelligence* 32(1), 1987, 57–95. DOI: https://doi.org/10.1016/0004-3702(87)90062-2
- Stéphane Lafortune et al., “Discrete Event Systems: Modeling, Observation, and Control,” *Annual Review of Control, Robotics, and Autonomous Systems* (2019), including diagnosability under partial observation. https://www.annualreviews.org/content/journals/10.1146/annurev-control-053018-023659

Direct pressure:

```text
anomaly or inconsistency
-> diagnose modeled fault;
partial observation
-> ask whether faults are diagnosable;
data incompatible with candidate model
-> invalidate model.
```

Therefore an anomaly, failed prediction, or model/data contradiction does not by itself establish a Responsibility Topology-specific representation-inadequacy object.

The narrow residual must concern something stronger: entitlement to suspect that a **task-required distinction is absent from the current representation** before the correct refinement is known, while independently justifying that this missing distinction matters for continued reliance. If the “missing distinction” is already encoded in the diagnostic model, fault alphabet, loss function, or test family, the novelty claim is substantially weakened.

Current status: **VERY STRONG OVERLAP; QX-style residual remains unearned without independent provenance of the missing task-relevant distinction.**

### 6.5 Residual candidate: representation-inadequacy entitlement

The strongest remaining question is:

> Under what evidence can a finite action-bearing system become entitled to suspect that the current space of distinctions is inadequate for a relied-upon task, before it knows the correct refinement?

This is narrower than “detect an unknown class,” “diagnose a modeled fault,” or “observe a model/data mismatch.” It matters only if the suspicion changes a downstream qualification or action boundary, for example:

```text
continue -> pause;
qualified -> revalidation-required;
automatic action -> human/domain escalation;
parameter update -> representation reopen;
local repair -> structural reorganization.
```

This remains a **RESIDUAL CANDIDATE**. The burden is to show that ordinary model misspecification, open-world learning, model-based diagnosis, diagnosability, active diagnosis, model invalidation, or scientific-model criticism cannot preserve the same material fact and decision consequence.

### 6.6 AI trajectory

AI progress is likely to make candidate generation, counterfactual generation, search, theorem generation, and critique substantially cheaper. That reduces the scarcity value of “generate more candidates.” The scarce functions move toward:

```text
independent material acquisition;
qualification of evidence;
recognition of shared blind spots;
allocation of real-world experiments;
judgment of revision depth;
knowing when further internal reasoning is not enough.
```

Cognitive Responsibility becomes more valuable if it focuses on **responsibility of cognition** rather than on a general theory of cognition.

## 7. Interaction Responsibility

### 7.1 Central problem

[Theory of Interaction Responsibility](theory-of-interaction-responsibility.md) does not assume that interacting actors begin with one complete, common, actor-accessible game. It explicitly permits distinct strategic-situation representations:

$$
\mathscr G_i \neq \mathscr G_j.
$$

Here `G` remains orientation; it is not a game or strategic-situation symbol. The theory also allows uncertainty about which actors, factors, actions, time structures, or relations should be represented at all.

### 7.2 Direct competition: games with unawareness

Games with unawareness are a direct and important neighboring tradition. They were developed precisely because standard state-space models of asymmetric information do not adequately represent agents who are unaware of relevant events or possibilities.

Representative source:

- Aviad Heifetz, Martin Meier, and Burkhard C. Schipper, “Interactive Unawareness,” *Journal of Economic Theory* 130(1), 2006, 78–94. DOI: https://doi.org/10.1016/j.jet.2005.02.007

Therefore:

```text
different actors may represent different possibility spaces
```

is not a Responsibility Topology novelty claim by itself.

### 7.3 Direct competition: interactive agent modeling

Interactive POMDPs explicitly model an agent's beliefs about the physical world and about models and beliefs of other agents, including higher-order belief structure.

Representative source:

- Piotr J. Gmytrasiewicz and Prashant Doshi, “A Framework for Sequential Planning in Multi-Agent Settings,” *Journal of Artificial Intelligence Research* 24 (2005), 49–79.

This strongly competes with other-actor models and finite higher-order strategic reasoning.

### 7.4 Primary hostile competition: contracts, interfaces, belief merging, and judgment aggregation

For the current narrow residual, the strongest competition is no longer only game theory. Section 4.4 directly attacks local-to-global composition through assume-guarantee and interface theories; Section 4.5 attacks local-to-collective determination through belief merging and judgment aggregation.

Therefore the following broad statement is heavily occupied:

```text
local correctness / local judgment
-/->
valid global composition / collective judgment.
```

The remaining burden is to show that **qualification of composition** includes material facts not preserved by ordinary contract or aggregation accounts: heterogeneous representation, context-indexed evidence qualification, use-specific admissibility, authority, continued reliance, and revalidation after local support changes.

### 7.5 Residual candidate: qualification for formal joint representation

The strongest remaining question is:

> When may heterogeneous local determinations be compressed into one action-bearing joint strategic representation, and when must a system refuse that compression because compatibility, correspondence, current qualification, authority, or joint organizational information is not yet justified?

This is a transition problem:

```text
local determination
-> current qualification
-> compatibility
-> joint determination
-> formal-model handoff
-> authorization
-> action / continued reliance.
```

The framework may have a distinctive role if it can state when a game-theoretic, contract-based, or multi-agent formalization is **premature or no longer current**, rather than only solving the model after its assumptions have been selected.

Current status: **RESIDUAL CANDIDATE under very high competitive pressure.**

### 7.6 AI trajectory

This problem becomes more important as AI systems are decomposed into planners, retrievers, verifiers, domain agents, safety monitors, and execution agents. A future orchestration failure may arise even when each local agent is competent:

```text
local correctness
+
invalid or stale composition
=
unsafe global action.
```

The important research target is therefore not merely multi-agent performance, but **qualification and continued validity of composition**.

## 8. Value Responsibility

### 8.1 Central separation

[Theory of Value Responsibility](theory-of-value-responsibility.md) preserves a ladder roughly of the form:

```text
consequence difference
-> system relevance
-> regulatory polarity
-[experience-status gate]->
experiential polarity
-> first-order orientation
-> reflective endorsement
-> individual value commitment
```

while maintaining:

```text
system regulation -/-> experience;
experience -/-> ought;
preference -/-> reflective endorsement;
individual endorsement -/-> authority over others.
```

### 8.2 Competition: preference and value learning

AI alignment and assistance research already studies systems that infer uncertain human objectives or preferences and act cooperatively under that uncertainty.

Representative source:

- Dylan Hadfield-Menell, Anca Dragan, Pieter Abbeel, and Stuart Russell, “Cooperative Inverse Reinforcement Learning,” 2016. https://arxiv.org/abs/1606.03137

This means that “AI should not assume the human objective is completely known” and “value information may be learned interactively” are strongly occupied claims.

In philosophy and cognitive science, second-order preferences, reflective endorsement, autonomy, preference construction, affect, and value change are also mature research areas. Broad claims about reflection converting first-order desire into endorsed commitment therefore face very high competitive pressure.

### 8.3 Residual value: the experience-status gate

The most durable boundary contribution is the refusal to move directly from functional regulation to subjective experience:

```text
reward signal -/-> experience;
self-maintenance -/-> subjectivity;
functional agency -/-> consciousness;
linguistic self-report -/-> sufficient evidence of experience.
```

This is less a novel theory of consciousness than a governance firewall preventing an AI capability or control structure from being silently promoted into a welfare or moral-status conclusion.

Current consciousness research itself remains uncertain and increasingly treats AI consciousness as an empirical/theoretical assessment problem rather than something inferable from one behavioral marker.

Representative recent source:

- Patrick Butlin et al., “Identifying indicators of consciousness in AI systems,” *Trends in Cognitive Sciences* (2026).

### 8.4 AI trajectory

Near term, this module has weaker competitive advantage than Interaction or System Reliability because preference learning and autonomy/value theory are already crowded. Its option value rises sharply if advanced AI systems acquire persistent agency, memory, self-models, long-lived orientations, or other properties that make AI welfare/subjectivity a live governance problem.

The correct stance is therefore:

```text
preserve the boundary;
do not over-invest in a universal value theory;
reopen when domain evidence makes the gate operationally necessary.
```

## 9. System Responsibility Reliability

### 9.1 Central problem

[System Responsibility Reliability](system-responsibility-reliability.md) studies whether interconnected finite systems retain real capacity for:

```text
observation;
dissent;
validation;
correction;
memory;
fault containment;
recovery;
reauthorization;
reopening;
maneuver after fundamental mismatch.
```

Its most important distinctions include:

```text
formal division of labor -/-> fault independence;
operational redundancy -/-> recovery redundancy;
formal reversibility -/-> effective reversibility;
once authorized -/-> still authorized;
more candidate paths -/-> more real reachability.
```

### 9.2 Strong competition: resilience engineering

Resilience engineering, especially David Woods's theory of graceful extensibility, starts from finite adaptive capacity, continuing change, surprise, saturation risk, and the need for networks of adaptive units to preserve the ability to adapt beyond local limits.

Representative source:

- David D. Woods, “The Theory of Graceful Extensibility: Basic Rules that Govern Adaptive Systems,” *Environment Systems and Decisions* 38 (2018), 433–457. DOI: https://doi.org/10.1007/s10669-018-9708-3

Accordingly, claims such as:

```text
finite systems face adaptive limits;
surprise is unavoidable;
recovery capacity matters;
local optimization can create brittleness;
multiple adaptive units are required;
```

are **STRONGLY OVERLAPPED** and should not be presented as standalone novelty.

### 9.3 Strong competition: safety engineering and fault tolerance

Fault domains, common-cause failure, redundancy, failover, isolation, rollback, defense in depth, and recovery independence are long-established engineering concerns. The framework's use of operational, failure-propagation, and recovery networks is valuable as an analytical reminder, but it must not claim to have discovered redundancy or common-mode failure.

### 9.4 Strong competition: corrigibility and interruptibility

AI safety research explicitly studies whether agents preserve human ability to stop or redirect them.

Representative sources:

- Laurent Orseau and Stuart Armstrong, “Safely Interruptible Agents,” UAI 2016.
- Dylan Hadfield-Menell, Anca Dragan, Pieter Abbeel, and Stuart Russell, “The Off-Switch Game,” 2016/2017. https://arxiv.org/abs/1611.08219

Therefore, “preserve a shutdown path” is not a novel claim.

### 9.5 Strong competition: STAMP/STPA and runtime assurance

STAMP/STPA explicitly models safety as enforcement of constraints through a hierarchical control structure and treats unsafe interactions and inadequate control as possible causes even when individual components have not simply “failed.” Runtime Assurance/Simplex architectures explicitly monitor unverified or advanced components and transfer control to a trusted reversionary component when safety conditions are violated.

Therefore, the following are not residuals by themselves:

```text
safety is not reducible to component reliability;
monitoring must affect control;
a system needs an independent fallback path;
unsafe current behavior can require withdrawal of control.
```

The stronger question is whether nominally independent control, monitoring, fallback, evidence, and governance positions share the same epistemic or infrastructural failure lineage, and whether that common capture should change admission or recovery design.

### 9.6 Strong competition: AI assurance, post-deployment monitoring, and continuous assurance

AI risk-management and assurance practice increasingly treats deployment as an ongoing evidence process. NIST's AI RMF materials include monitoring, incident response, recovery, change management, override, and post-deployment evaluation. NIST AI 800-4 (March 2026) documents challenges of monitoring deployed AI systems. Recent continuous-assurance work also seeks to connect design-time, runtime, and evolution-time evidence and regenerate assurance arguments as system artifacts change.

Representative sources:

- NIST AI 800-4, *Challenges to the Monitoring of Deployed AI Systems*, March 2026. https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.800-4.pdf
- Abeywickrama et al., “Towards Continuous Assurance with Formal Verification and Assurance Cases,” 2025 preprint. https://arxiv.org/abs/2511.14805

This is direct competition for generic monitoring/recovery/revalidation language. Continuous assurance should currently be treated as a rapidly developing competitor, not as an already exhaustive mature theory.

### 9.7 Residual candidate: epistemic common capture plus authority and recovery

The strongest possible residual is a specific combination that becomes increasingly relevant to AI systems:

```text
many apparent validators
+
shared model/data/tool/authority lineage
->
common epistemic fault domain.
```

The framework's **common capture of correction loops** asks whether observation, dissent, validation, correction, and memory are nominally separate but inherit the same failure source.

This matters when generator, reviewer, safety monitor, planner, incident summarizer, and governance analyst all depend on the same model family, retrieval substrate, identity layer, evaluator, or organizational incentive.

The distinct research opportunity is to connect:

```text
epistemic independence
+ current qualification
+ authority duration
+ continued reliance
+ reauthorization
+ recovery-path independence
+ effective reversibility.
```

Traditional safety engineering contains many pieces of this structure; runtime/continuous assurance contains others. A Responsibility Topology contribution is earned only if the combined account produces a different audit requirement, admission decision, deployment topology, or recovery design after those competitors are given their strongest reasonable formulation.

Current status: **RESIDUAL CANDIDATE under very high competitive pressure.**

### 9.8 AI trajectory

The value of this area is likely to increase strongly for four reasons.

First, agentic systems shorten the distance between judgment and real-world action. Second, the same model families may occupy many nominally independent roles, increasing correlated epistemic failure. Third, automated deployment and code/action generation can reduce the damage or lock-in time window faster than they reduce observation and recovery time. Fourth, infrastructure concentration can make formal rollback survive while real rollback capacity disappears.

The 2026 International AI Safety Report notes that reliable evaluation of AI agents remains limited, that some failures appear only in real use, that agent autonomy and tool access make reliability assessment harder, and that multi-agent interactions may create novel behaviors or correlated failures. This is directly relevant to the theory's rate-compatibility and common-capture questions.

Source:

- *International AI Safety Report 2026*. https://internationalaisafetyreport.org/

## 10. Responsibility Structure Candidate Catalog

[Responsibility Structure Candidate Catalog](responsibility-structure-candidate-catalog.md) contains many patterns that individually have mature predecessors: feedback loops, path dependence, bottlenecks, network effects, local optimization, coupling, redundancy, causal separation, open/closed representation problems, and so on.

Accordingly:

```text
catalog membership
-/->
novel mechanism claim.
```

### 10.1 Direct competition: analogy and structure mapping

Structure-mapping theory already studies how relational structure rather than surface attributes may be mapped between domains and distinguishes analogy from other forms of similarity.

Representative source:

- Dedre Gentner, “Structure-Mapping: A Theoretical Framework for Analogy,” *Cognitive Science* 7(2), 1983, 155–170. DOI: https://doi.org/10.1207/s15516709cog0702_3

Therefore “cross-domain relational similarity should be analyzed structurally rather than by shared labels” is not a novel claim.

### 10.2 Direct competition: causal transportability

Causal transportability gives formal conditions for when causal information learned in one environment can legitimately be transferred to another and provides complete procedures under explicit causal assumptions.

Representative source:

- Elias Bareinboim and Judea Pearl, “Transportability of Causal Effects: Completeness Results,” AAAI 2012, 698–704. DOI: https://doi.org/10.1609/aaai.v26i1.8232

This places strong pressure on any substantive claim that Responsibility Topology itself determines when a mechanism or causal result transports across domains.

### 10.3 Narrowed residual: migration-strength governance before mechanism evidence

The catalog's plausible contribution is therefore not a new analogy theory or transportability calculus. It is a **research-governance discipline** that limits the strength of migration claims before domain-specific transport evidence is available:

```text
CommonProblem
!=
FormalSimilarity
!=
MechanismSimilarity.
```

The question is whether this staged discipline actually reduces false mechanism transfer in analysis, especially when AI systems can generate persuasive cross-domain analogies cheaply. If it does not change conclusions, evidence demands, or error rates, it should be treated as conceptual hygiene rather than as a substantive research contribution.

## 11. How AI progress changes the competitive value of the framework

### 11.1 What becomes cheaper

Continued AI progress is likely to reduce the cost of:

```text
candidate generation;
textual explanation;
formal decomposition;
code generation;
proof search;
counterexample generation;
policy drafting;
review generation;
agent replication.
```

The theoretical value of a framework cannot therefore depend primarily on producing more structures or more articulate explanations.

### 11.2 What becomes scarcer

The comparatively scarce resources become:

```text
independent contact with reality;
source and failure-lineage diversity;
qualification of evidence for a concrete use;
composition of heterogeneous local determinations;
legitimate authority to act;
ability to stop or withdraw qualification;
real rollback, takeover, exit, and recovery paths;
time to correct before propagation or lock-in;
ability to reopen a representation after the current system has shaped the environment around itself.
```

This predicts a shift in the framework's center of value:

```text
from cognition theory
-> responsibility of cognition;

from more agents
-> independence and composition of agents;

from more monitoring
-> independence and actionability of monitoring;

from nominal rollback
-> effective reversibility;

from initial authorization
-> current and renewable authorization.
```

### 11.3 Capability does not automatically erase responsibility problems

A stronger AI may reduce some epistemic errors, but it can simultaneously increase:

```text
action speed;
blast radius;
coordination scale;
model monoculture;
software and infrastructure coupling;
dependency on machine-generated evidence;
opacity of distributed decision paths.
```

Therefore the relevant variable is not simply “AI intelligence.” It is the ratio between capability for action and capability for independent detection, veto, correction, recovery, and reauthorization.

## 12. Current watch priority after competition

This ranking is an **observational/watch priority**, not an authorization to reopen theory construction, empirical search, runtime expansion, or formalization.

```text
Priority rank
!=
active research authorization.

Absent an independent trigger,
all ranked areas remain observational/watch priorities only.
```

If attention must be concentrated, the current watch order is:

1. **System Responsibility Reliability** — highest expected AI-era value; watch for source-backed cases involving common capture, rate incompatibility, loss of effective reversibility, reauthorization failure, or recovery dependence that existing safety/assurance methods fail to preserve.
2. **Interaction Responsibility / joint determination** — watch for cases where heterogeneous local qualifications produce a composition decision not captured by assume-guarantee contracts, interface theory, belief merging, or judgment aggregation.
3. **Cognitive Responsibility / representation-inadequacy entitlement** — watch narrowly for evidence that forces a distinction between ordinary diagnosis/model invalidation and justified suspicion of a missing task-required discriminator.
4. **Value Responsibility / experience-status gate** — preserve and monitor; reopen when AI consciousness/welfare evidence makes the distinction operationally consequential.
5. **Determinative Responsibility as substrate** — maintain a compact transition discipline; do not expand the meta-language unless a new distinction changes a theorem, evidence requirement, or action boundary.

This ordering is not a Framework V1.0 semantic dependency and does not override any repository-level theory/formalization gate.

## 13. Promotion and kill rules

A putative Responsibility Topology contribution should be downgraded or killed when any of the following is true:

```text
a recognized neighboring account preserves all relevant material facts;
the neighboring account reaches the same decision boundary with equal or lower assumptions;
the difference is only terminology or decomposition style;
the proposed framework object is definitional expansion of its desired conclusion;
the framework adds audit burden but no detectable decision or failure consequence;
a representation theorem shows the two accounts are equivalent on the relevant surface.
```

A residual is worth promotion only when at least one of the following survives hostile comparison:

```text
different evidence obligation;
different admissibility / qualification boundary;
different composition rule;
different intervention or escalation decision;
different revalidation or withdrawal rule;
different recovery topology;
nontrivial theorem or countermodel unavailable to the rival without stronger assumptions;
source-backed failure that the rival cannot preserve without losing a material fact.
```

For transition residuals, the hostile-comparison order should be:

```text
belief / epistemic change
-> provenance / lineage
-> authorization / revocation
-> composition / interfaces
-> aggregation / collective judgment
-> runtime / continuous assurance
-> only then: claim a distinct responsibility transition.
```

This mirrors the framework-wide principle that progress is not vocabulary, theorem, or case count. Competitive progress is measured by **freedom removed from the claim space**.

## 14. Maintenance protocol

This file should be updated when any of the following occurs:

- a neighboring literature is found that materially absorbs a current residual;
- a new source-backed AI failure makes a residual decision-relevant;
- an external theory yields an embedding, conservative translation, or equivalence relation to a framework structure;
- a current residual generates a distinct theorem, audit requirement, or runtime decision consequence;
- AI capability or deployment structure changes the practical value of a theory boundary.

For every future competitor, record at minimum:

```text
Competitor / literature:
Framework claim under pressure:
What does the competitor already solve?:
Same material facts?:
Same assumptions?:
Same decision consequence?:
What, if anything, remains unexplained?:
What theorem / case / experiment would distinguish them?:
Current status: ABSORBED | STRONG OVERLAP | RESIDUAL CANDIDATE | OPEN
Evidence that would change status:
Sources:
```

Do not infer literature exhaustion from this file. A missing competitor means **not yet recorded**, not **no competitor exists**.

## 15. Initial reference set

This list is deliberately compact. It identifies high-pressure neighboring traditions rather than attempting a full literature review.

1. Lieder, F. & Griffiths, T. L. Resource-rational analysis. *Behavioral and Brain Sciences* 43, e1 (2020). https://doi.org/10.1017/S0140525X1900061X
2. Scheirer, W. J., Rocha, A., Sapkota, A. & Boult, T. E. Toward Open Set Recognition. *IEEE TPAMI* 35(7) (2013). https://doi.org/10.1109/TPAMI.2012.256
3. Heifetz, A., Meier, M. & Schipper, B. C. Interactive Unawareness. *Journal of Economic Theory* 130(1) (2006). https://doi.org/10.1016/j.jet.2005.02.007
4. Gmytrasiewicz, P. J. & Doshi, P. A Framework for Sequential Planning in Multi-Agent Settings. *JAIR* 24 (2005), 49–79.
5. Hadfield-Menell, D., Dragan, A., Abbeel, P. & Russell, S. Cooperative Inverse Reinforcement Learning (2016). https://arxiv.org/abs/1606.03137
6. Orseau, L. & Armstrong, S. Safely Interruptible Agents. UAI (2016).
7. Hadfield-Menell, D., Dragan, A., Abbeel, P. & Russell, S. The Off-Switch Game (2016/2017). https://arxiv.org/abs/1611.08219
8. Woods, D. D. The Theory of Graceful Extensibility: Basic Rules that Govern Adaptive Systems. *Environment Systems and Decisions* 38 (2018), 433–457. https://doi.org/10.1007/s10669-018-9708-3
9. NIST AI 800-4. *Challenges to the Monitoring of Deployed AI Systems* (March 2026). https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.800-4.pdf
10. *International AI Safety Report 2026*. https://internationalaisafetyreport.org/
11. Butlin, P. et al. Identifying indicators of consciousness in AI systems. *Trends in Cognitive Sciences* (2026).
12. Doyle, J. A Truth Maintenance System. *Artificial Intelligence* 12(3) (1979), 231–272. https://doi.org/10.1016/0004-3702(79)90008-0
13. Stanford Encyclopedia of Philosophy. Logic of Belief Revision. https://plato.stanford.edu/entries/logic-belief-revision/
14. Green, T. J., Karvounarakis, G. & Tannen, V. Provenance Semirings. PODS (2007), 31–40. https://doi.org/10.1145/1265530.1265535
15. Becker, M. & Nanz, S. A Logic for State-Modifying Authorization Policies. Microsoft Research / IEEE INFOCOM. https://www.microsoft.com/en-us/research/publication/a-logic-for-state-modifying-authorization-policies/
16. Chilton, C., Jonsson, B. & Kwiatkowska, M. Compositional assume–guarantee reasoning for input/output component theories. *Science of Computer Programming* 91 (2014), 115–137. https://doi.org/10.1016/j.scico.2013.12.010
17. Dewes, R. & Dimitrova, R. Contract-based Design and Verification of Multi-Agent Systems with Quantitative Temporal Requirements. AAAI (2025). https://doi.org/10.1609/aaai.v39i22.34480
18. Stanford Encyclopedia of Philosophy. Belief Merging and Judgment Aggregation. https://plato.stanford.edu/entries/belief-merging/
19. Williamson, J. Aggregating Judgements by Merging Evidence. *Journal of Logic and Computation* 19(3) (2009), 461–473. https://doi.org/10.1093/logcom/exn011
20. Reiter, R. A Theory of Diagnosis from First Principles. *Artificial Intelligence* 32(1) (1987), 57–95. https://doi.org/10.1016/0004-3702(87)90062-2
21. Leveson, N. & Thomas, J. *STPA Handbook*. https://psas.scripts.mit.edu/home/get_file.php?name=STPA_handbook.pdf
22. Slagel, J. T. et al. A Verification Framework for Runtime Assurance of Autonomous UAS. NASA NTRS 20240007986 (2024). https://ntrs.nasa.gov/citations/20240007986
23. Abeywickrama, D. B. et al. Towards Continuous Assurance with Formal Verification and Assurance Cases (2025 preprint). https://arxiv.org/abs/2511.14805
24. Gentner, D. Structure-Mapping: A Theoretical Framework for Analogy. *Cognitive Science* 7(2) (1983), 155–170. https://doi.org/10.1207/s15516709cog0702_3
25. Bareinboim, E. & Pearl, J. Transportability of Causal Effects: Completeness Results. AAAI (2012), 698–704. https://doi.org/10.1609/aaai.v26i1.8232

## 16. Current bottom line

The current competitive picture does **not** support a claim that Responsibility Topology has discovered a new general theory of finite intelligence, strategic interaction, value, provenance, authorization, compositional verification, or resilient systems. Each broad area has mature neighboring traditions.

The stronger research hypothesis is narrower:

> **There may be under-specified responsibility-bearing transitions between evidence, representation, historical provenance, current qualification, joint determination, authority, continued reliance, revalidation, and recovery, especially when AI systems are heterogeneous, autonomous, fast, and built on correlated epistemic infrastructure.**

Section 4 materially raises the novelty burden. It is no longer enough to show that neighboring disciplines own different broad segments of the chain. A durable residual must survive direct comparison with belief revision, provenance, authorization, contract/interface composition, belief/judgment aggregation, and runtime/continuous assurance.

The framework earns durable value only where the explicit separation of those segments changes what a system is permitted to infer, combine, authorize, execute, continue relying on, withdraw, revalidate, or recover from.

Until such decision-relevant residuals survive competition, the correct interpretation is:

```text
problem value: often high;
neighboring competition: very high;
framework-wide novelty: not established;
interface-level residuals: plausible but narrower than previously stated;
strongest research burden: show a material fact or decision boundary not preserved by direct transition competitors;
AI-era value: likely to concentrate in qualification, composition, correction, reauthorization, continued reliance, and effective reversibility.
```
