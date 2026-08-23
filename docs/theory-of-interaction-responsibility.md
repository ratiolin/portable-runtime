---
document_type: theory
document_status: stable
framework_version: 1.0.0
knowledge_scope: original-synthesis
evidence_basis: original-framework
external_evidence: required-for-empirical-claims
updated: 2026-08-20
revision_basis: framework-v1-public-interface-2026-08-20
semantic_contract:
  role: canonical-definition
  defines:
    - finite_system_strategic_interaction
    - strategic_actor
    - strategic_situation_representation
    - other_actor_model
    - strategic_representation_closure
    - strategic_reopen_attribution
    - formal_game_handoff
  imports:
    - concept: distinction
      from: Finite Change Theory
      mode: specialize
    - concept: factor
      from: Finite Change Theory
      mode: specialize
    - concept: organization_structure
      from: Finite Change Theory
      mode: specialize
    - concept: orientation
      from: Finite Change Theory
      mode: reference
    - concept: judgment
      from: Finite Change Theory
      mode: specialize
    - concept: action
      from: Finite Change Theory
      mode: specialize
    - concept: open_closure
      from: Finite Change Theory
      mode: specialize
    - concept: candidate_generation
      from: Finite Intelligence
      mode: reference
    - concept: cognitive_frontier
      from: Finite Intelligence
      mode: specialize
    - concept: counterfactual_construction
      from: Finite Intelligence
      mode: specialize
    - concept: epistemic_action
      from: Finite Intelligence
      mode: specialize
    - concept: epistemic_material_acquisition
      from: Finite Intelligence
      mode: reference
    - concept: open_validation
      from: Finite Intelligence
      mode: reference
    - concept: revision_depth_judgment
      from: Finite Intelligence
      mode: specialize
    - concept: finite_reflexivity
      from: Finite Intelligence
      mode: specialize
    - concept: cognitive_search_allocation_judgment
      from: Finite Intelligence
      mode: reference
    - concept: subject_working_boundary
      from: Finite Intelligence
      mode: boundary-reference
    - concept: structure_candidate
      from: Cross-Domain Structure Candidates
      mode: reference
    - concept: change_procedure
      from: Finite Change Practice
      mode: handoff
  excludes:
    - second_meta_model
    - subjectivity_determination
    - universal_game_form
    - equilibrium_theory
    - domain_specific_payoff_claims
    - domain_specific_strategy_claims
    - normative_legitimacy
    - action_procedure
    - record_schema
    - operational_facts
---

# Theory of Interaction Responsibility

> **Knowledge and evidence boundary:** This document specializes the finite-system intervention and shared-affairs layers of the [Theory of Determinative Responsibility](theory-of-determinative-responsibility.md). It explains how multiple finite systems, under incomplete, heterogeneous, and potentially mutually influencing information and representation conditions, form strategic structures, models of others, judgments, and actions, and when an open strategic problem can be provisionally closed into a joint representation suitable for handoff to formal tools. It does not presuppose a unique, complete, actor-accessible “true game,” does not establish a second cognitive machine, and does not replace game theory, economics, organization studies, political science, military studies, law, or other domain models.
>
> **Core discipline:** Finite strategic actors act on currently callable, fallible, and potentially incomplete strategic structures. Their actions then enter subsequent interaction through each other actor's own connection to reality, distinction, organization, and judgment. Only after analytical purpose, scope, and residual unknowns have been made explicit, and the joint strategic representation has reached proportionate closure, should the current representation be handed to closed formal tools.

## Definition Dependencies

The V1 public interface includes finite-system strategic interaction, strategic actor, strategic-situation representation, other-actor model, joint strategic-representation closure, strategic reopen attribution, and formal-model handoff. Strategic cognitive frontier, relational strategic signal, strategic epistemic closure, and strategic epistemic action remain rigorously defined here but are document-local working vocabulary.

Distinction, factor, organizational structure, orientation, judgment, action, and open / closure are inherited from the [Theory of Determinative Responsibility](theory-of-determinative-responsibility.md). Candidate generation, cognitive frontier, counterfactual construction, epistemic action, material acquisition, open validation, revision-depth judgment, cognitive-search-allocation judgment, finite reflexivity, and the working boundary of subjectivity are inherited from the [Theory of Cognitive Responsibility](theory-of-cognitive-responsibility.md). Relevant cross-domain patterns are taken only as candidate questions from the [Responsibility Structure Candidate Catalog](responsibility-structure-candidate-catalog.md); real-world action procedures are handed off to [Action Responsibility Practice](action-responsibility-practice.md).

This document must not redefine `G` as “game” or “strategic situation.” In this framework:

$$
G\subseteq S
$$

continues to designate orientation. Strategic-situation representation uniformly uses $\mathscr G$; the currently formalized joint strategic representation uses $\widehat{\mathscr G}$.

### Local notation boundary

See the [Responsibility Topology Overview](responsibility-topology-overview.md) for general notation discipline. This document adds only that $M_i^j$ does not automatically denote a probabilistic belief, $\mathscr G_i$ does not automatically denote a standard game, and $C^{\mathscr G}$ does not mean that reality itself “has closed.” If formal tools are to promote these working symbols into mathematical objects, participants, states, types, actions, information, preferences, time, probability, observations, and validation conditions must be specified separately.

## I. Working Boundary of Finite-System Strategic Interaction

### 1. Strategic actor

A **strategic actor** is a finite-system role whose distinctions, judgments, selections, or actions can enter the later real situation, acquisition conditions, judgment conditions, or feasible paths of another actor in the current analysis.

A strategic actor may be a person or group already accorded subject status, or it may be an organization, institutional arrangement, delegated system, technical system, or another action position from which subjectivity cannot yet be inferred. Therefore:

$$
\boxed{\text{strategic actor}\not\Rightarrow\text{subjectivity}}
$$

$$
\boxed{\text{strategic capability}\not\Rightarrow\text{qualification for responsibility, decision authority, or legitimate authority}}
$$

Concrete judgments of subjectivity use the working boundary in the [Theory of Cognitive Responsibility](theory-of-cognitive-responsibility.md). Rights, authorization, and responsibility belong to shared affairs, domain institutions, and [Action Responsibility Practice](action-responsibility-practice.md).

### 2. Finite-system strategic interaction

**Finite-system strategic interaction** is the process in which two or more strategic actors, where each actor's actions may change its own or others' later reality, information conditions, judgment conditions, or reachable paths, form strategic structures and act on them under finite acquisition, finite distinction, finite candidate generation, and finite reflexivity.

The minimum requirement is not “competition exists” and not “every actor maximizes the same form of utility,” but that actions can enter the later conditions of other actors:

$$
A_{i,t}\leadsto R_{t+1}\leadsto\{D,F,S,G,J,A\}_{j,t+1}.
$$

The arrows indicate only possible mechanism-entry relations. Concrete direction, strength, delay, and causal mechanism are owned by domain evidence.

### 3. A strategic problem does not presuppose a complete game

A finite actor may not merely be uncertain about the value of some already-defined type or state; it may not yet have adequately determined which actors matter, which factors constitute the current state, which actions are feasible in reality, under what orientations and constraints others judge, what temporal structure the interaction has, or which local determinations can enter the same joint strategic representation.

Therefore:

$$
\boxed{
\text{not knowing the value of a defined variable}
\neq
\text{not knowing how the strategic problem should currently be defined}
}
$$

Strategic uncertainty may be within-model unknown, or it may reflect incompleteness in the candidate space and strategic representation themselves. This document does not presuppose a unique, complete $\mathscr G^\ast$ of strategic reality that every actor can in principle obtain.

## II. Formation of Strategic Structure and Finite Representation

### 1. Specialized strategic main chain

For actor $i$, when connection to reality must be analyzed explicitly:

$$
R_t
\xrightarrow{\mathcal Q_{i,t}}
E^{\mathrm{mat}}_{i,t}
\xrightarrow{D_{i,t}}
F_{i,t}
\xrightarrow{\mathcal O_{i,t}}
S_{i,t}
\xrightarrow{J_{i,t}}
A_{i,t}
\rightarrow
R_{t+1}.
$$

Strategically relevant structures do not establish an independent cognitive layer; they are retained as callable organizational structures within $S_{i,t}$:

$$
S_{i,t}
\supseteq
\{W_{i,t},M_{i,t}^{-i},\mathscr G_{i,t},G_{i,t},\ldots\}.
$$

Here $W_i$ is a working representation of environment, resources, and constraints; $M_i^{-i}$ is the current model of other strategic actors; $\mathscr G_i$ is the working representation of how the overall strategic situation is organized; and $G_i$ continues to denote orientation. These may overlap, be conditional, or be only partially formed. The expression does not require mutually exclusive fields.

### 2. Strategic cognitive frontier

The **strategic cognitive frontier** is the subset of the current cognitive frontier whose candidates concern strategic interaction structure:

$$
\mathcal F_{i,t}^{\mathrm{strat}}
\mathcal F_{i,t}^{\mathrm{strat}} =
\{h\in\mathcal F_{i,t}\mid h\text{ is currently relevant to strategic interaction structure}\}.
$$

Therefore:

$$
\mathcal F_{i,t}^{\mathrm{strat}}\subseteq\mathcal F_{i,t}.
$$

An $h$ in this set need not be a complete strategic-situation representation. It may be only a new actor candidate, variable direction, time scale, interpretation of another actor's orientation, action boundary, strategic epistemic interpretation, $M_i^{j,(k)}$, or a more mature $\mathscr G_i^{(k)}$.

Thus:

$$
\boxed{\text{open strategic thinking}\not\Rightarrow\text{complete game candidates must be generated first}}
$$

and:

$$
\boxed{
\text{a structure adequate to represent the relevant strategic reality
may not yet have appeared in }\mathcal F_{i,t}^{\mathrm{strat}}
}
$$

### 3. Strategic-situation representation $\mathscr G_i$

A **strategic-situation representation** $\mathscr G_{i,t}$ is the currently formed and callable organizational structure of actor $i$ concerning strategically relevant actors, roles, relations, action conditions, information differences, constraints, possible responses, temporal structure, and consequence relations.

$\mathscr G_i$ is the strategic specialization of part of $S_i$. It is not reality itself, need not already be formalized, and does not require all actors to hold the same representation:

$$
\boxed{\mathscr G_i\neq\mathscr G_j\quad\text{is an allowed state}}
$$

Different representations may arise from different $\mathcal Q$, $D$, prior structures, orientations, search histories, and positions in reality, and may also be affected by selective disclosure and strategic manipulation. The fact that a representation supports current action is not evidence that it is the ultimate structure of the relevant strategic reality.

### 4. Other-actor model $M_i^j$

An **other-actor model** $M_{i,t}^j$ is actor $i$'s currently callable strategic structure concerning actor $j$. It may preserve whatever current reason supports treating as relevant about $j$'s state, orientation, capabilities, resources, authority, realistically feasible actions, possible material acquisition, mode of judgment, and $j$'s models of other actors or the situation.

These are analytical positions only. They need not all exist and do not imply accurate access by $i$:

$$
\boxed{M_i^j\neq j\text{'s actual internal state}}
$$

$$
\boxed{M_i^j\neq\text{a synonym for probabilistic belief}}
$$

When domain conditions are adequate, parts of the model may be further formalized as probabilities, type distributions, strategy estimates, or other mathematical objects.

### 5. Higher-order models and finite depth

Strategic interaction permits finite higher-order structures that have actually formed about another actor's judgments, for example:

$$
M_i^{j(i)},\qquad M_i^{j(k)},\qquad M_i^{j(i(k))}.
$$

The notation does not require infinite levels or common knowledge. Following finite reflexivity from the [Theory of Cognitive Responsibility](theory-of-cognitive-responsibility.md):

$$
\boxed{
\text{ability to judge another's judgment}
\neq
\text{ability to complete infinite recursive rationality}
}
$$

Whether to continue unfolding higher-order models is decided by $\Lambda$ under time, resources, risk, and the likelihood of changing the current judgment.

## III. Action, Strategic Signals, and Reflexive Change

### 1. Action is not directly a signal

Action is first a real-world intervention. Whether actor $i$'s action becomes a strategic signal for actor $j$ depends on $j$'s connection to reality, acquisition, and distinction:

$$
A_{i,t}
\rightarrow
R_{t+1}
\xrightarrow{\mathcal Q_{j,t+1}}
E^{\mathrm{mat}}_{j,t+1}
\xrightarrow{D_{j,t+1}}
F_{j,t+1}.
$$

The same action may not be acquired at all, or may form different factors for different observers. Therefore $A_i$ cannot be directly identified with $s_{i\to j}$.

### 2. Relational strategic signal

A **relational strategic signal** $s_{x\to i,t}$ is a usable difference relevant to strategic candidates concerning object or actor $x$, formed when real differences related to $x$ pass through actor $i$'s current acquisition and distinction to become factors.

$$
R_t
\xrightarrow{\mathcal Q_{i,t}}
E_{i,t}^{\mathrm{mat}}
\xrightarrow{D_{i,t}}
F_{i,t}
\rightsquigarrow
s_{x\to i,t}.
$$

A “signal” is a relational structure, not a fixed property carried by a real object itself. Whether actions, statements, offers, records, absences, delays, or silence become strategic signals depends on concrete acquisition conditions, expectation structures, and distinction rules.

### 3. Strategic signal is not an evidential conclusion

After a strategic signal forms, its evidential force on candidate structures is still owned by open validation:

$$
s_{x\to i,t}
\rightarrow
V_{\mathrm{open}}
\rightarrow
J_{i,t}^E.
$$

Therefore:

$$
\boxed{\text{strategic signal}\neq\text{strategic evidential conclusion}}
$$

Deception, misreading, and omission should be checked separately at the levels of real material, $\mathcal Q$, $D/F$, strategic relevance, $S$, and $V/J^E$. They must not all be written as “belief-update errors.”

### 4. Strategic epistemic action

**Strategic epistemic action** $A_{i,t}^{e,\mathrm{strat}}$ is the strategic specialization of epistemic action $A^e$: its primary purpose is not immediately achieving a final goal, but arranging interaction under proportionate authority, risk, and real cost so that competing other-actor models, strategic-situation candidates, or action consequences yield distinguishable real-world differences.

$$
\Phi_{S_{i,t}}
\rightsquigarrow
A_{i,t}^{e,\mathrm{strat}}
\rightarrow
R_{t+1}
\xrightarrow{\mathcal Q_i}
E_{i,t+1}^{\mathrm{mat}}
\rightarrow
V_{\mathrm{open}}.
$$

Strategic epistemic action is not purposeless trial and error, nor does potential information value itself confer qualification to act.

### 5. Strategic models participate in changing their later objects

$M_i^j$ and $\mathscr G_i$ may change $J_i$ and $A_i$; action then changes reality and other actors:

$$
M_i^j,\mathscr G_i
\rightarrow
J_i
\rightarrow
A_i
\rightarrow
R'
\rightarrow
\{M_j^i,\mathscr G_j,J_j,A_j\}
\rightarrow
R''.
$$

Therefore:

$$
\boxed{
\text{strategic models describe interaction
and may also, through action, participate in generating the objects they later describe}
}
$$

A regularity that was previously valid may fail after actors adapt, rules change, or information structures shift; this need not mean that the original model was wrong from the beginning.

## IV. Strategic Epistemic Closure and Joint-Representation Closure

### 1. Strategic epistemic closure $C^{E,\mathrm{strat}}$

**Strategic epistemic closure** $C_{i,t}^{E,\mathrm{strat}}(q,a)$ specializes $C^E$ for strategic-interaction problems: for the current problem $q$, actor $i$'s candidates, strategic structure, other-actor models, key unknowns, and evidence are proportionate enough to send action candidate $a$ into downstream action judgment.

It does not mean complete knowledge of strategic reality and does not create action authorization:

$$
C_{i,t}^{E,\mathrm{strat}}\not\Rightarrow C_{i,t}^{A}.
$$

Therefore:

$$
\boxed{
\begin{aligned}
&\text{a preferred action has been formed}\\
\neq{}&
\text{current strategic knowledge is sufficient to send it into action judgment}\\
\neq{}&
\text{current real-world conditions permit its implementation}
\end{aligned}
}
$$

### 2. Joint strategic-representation closure $C^{\mathscr G}$

**Joint strategic-representation closure** $C_{k,t}^{\mathscr G}(q,\rho)$ is a compound working state of analytical system $k$, relative to problem $q$ and analytical purpose, scope, and required precision $\rho$: current local determinations are sufficiently clear, compatible, and proportionate to form a usable joint strategic representation, such that the marginal value of continuing to treat the problem primarily as an open strategic-representation problem has declined and handoff to closed formal tools will not conceal the most important current structural uncertainty.

It may depend on:

$$
\{
J^{\mathrm{def}},
J^{\mathrm{comp}},
J^{\mathrm{det}},
J^{\mathrm{op}},
q,\rho,U_{\mathrm{res}}
\}
\rightsquigarrow
C_{k,t}^{\mathscr G}(q,\rho).
$$

$U_{\mathrm{res}}$ denotes remaining key unknowns, boundaries, dissent, and reopening conditions. The expression marks responsibility dependencies only; it is not a set of necessary and sufficient conditions or an automatic decision procedure.

### 3. Non-entailments of representation closure

Maintain:

$$
\boxed{C_{k,t}^{\mathscr G}\not\Rightarrow\mathscr G_i=\mathscr G_j}
$$

$$
\boxed{
C_{k,t}^{\mathscr G}
\not\Rightarrow
\text{common knowledge, common belief, or common understanding}
}
$$

and:

$$
C_{k,t}^{\mathscr G}
\not\Rightarrow
C_{i,t}^{E,\mathrm{strat}},
\qquad
C_{k,t}^{\mathscr G}
\not\Rightarrow
C_{i,t}^{A}.
$$

An analytical system may form a usable joint representation while preserving the fact that different actors possess different information, representations, orientations, and error structures.

### 4. Two closure paths

Real strategic action often must occur when a complete joint formal representation cannot be established. Therefore:

$$
\text{open strategic interaction}
\rightsquigarrow
C_{i,t}^{E,\mathrm{strat}}
$$

and:

$$
\text{open strategic representation}
\rightsquigarrow
C_{k,t}^{\mathscr G}
\rightsquigarrow
\widehat{\mathscr G}
$$

are different responsibility paths.

An actor may acquire only enough support for a low-exposure, recoverable next action while the overall problem remains open. An analytical system may also obtain a $\widehat{\mathscr G}$ suitable for delimiting the problem while the conditions for real-world action still do not hold.

### 5. Handoff to formal models

When $C_{k,t}^{\mathscr G}(q,\rho)$ has been reached, the current joint strategic representation may be compiled into a domain-appropriate formal object. A working form might be:

$$
\widehat{\mathscr G}
\widehat{\mathscr G} =
(N,\Theta,A,I,U,T,\ldots).
$$

Concrete fields are determined by the formal theory being used. This document does not define Bayesian games, signaling games, repeated games, stochastic games, or equilibrium concepts, nor does it claim that every strategic interaction should be compressed into such a tuple.

The handoff discipline is:

$$
\boxed{\text{first obtain a proportionate joint strategic representation, then choose a proportionate formal tool}}
$$

Formal results are responsible only to the current $\widehat{\mathscr G}$, assumptions, scope, and domain evidence. They do not automatically acquire validity across representations, scales, or institutions.

## V. Strategic Reopening and Revision Attribution

### 1. Candidate attributions for prediction failure

When strategic predictions, interactions, or outcomes deviate, distinguish at least:

1. **Strategic-representation mismatch:** $\mathscr G_i$ omits a key actor, relation, action, constraint, temporal structure, or consequence path;
2. **Other-actor-model mismatch:** $M_i^j$ inadequately represents another's orientation, capabilities, information, constraints, or mode of judgment;
3. **Material-acquisition or distinction mismatch:** the coverage, classification, scale, or correspondence in $\mathcal Q/D/F$ changed;
4. **Evidential-judgment mismatch:** material was given evidential meaning that was too strong, too weak, or pointed in the wrong direction;
5. **Action endogenously changed the object:** one's own action changed the environment, relations, observation conditions, or other actors;
6. **Adaptation by others:** other actors adjusted to one's actions, public models, rules, or expectations;
7. **External environment, orientation, or authority changed:** relevant conditions shifted outside the current interaction or at a higher layer.

Therefore:

$$
\boxed{\text{prediction error}\not\Rightarrow\text{update parameters only}}
$$

### 2. Strategic revision depth

Strategic scenarios continue to use $\Gamma$, adding strategic specialized structures to the candidate revision layers:

$$
Z_t
\rightsquigarrow
\Gamma
\rightsquigarrow
\{\mathcal Q,D,F,\mathcal O,S,M_i^j,\mathscr G_i,G_i,J_i,A_i,V,q\}.
$$

Avoid revision that is too shallow and too deep: the former continually adds local patches after the strategic structure has already mismatched; the latter escalates a single anomaly, a single deception, or a local acquisition failure into an error in the definition of the whole problem.

### 3. Applicability boundary of reflexivity

If a regularity persists only while actors have not noticed, adapted to, or learned to exploit it, that condition should be written into the applicability boundary. When a regularity becomes public, a metric is adopted, a prediction enters action, or a counterparty identifies our model, the original structure may change because of the interaction itself.

This is only a cross-domain problem interface, not an empirical claim about finance, organizations, policy, competition, diplomacy, or any other specific domain.

### 4. Consolidating strategic experience

When strategic experience enters long-term callable structure, do not store only “which strategy succeeded.” Also preserve the contemporaneous $\mathscr G_i$, key $M_i^j$, acquisition and distinction conditions, low-discrimination signals, rejected candidates, action-endogenous changes, adaptation by others, and reopening conditions.

One success does not prove that a strategic representation is complete; one failure does not automatically prove that every relevant structure is invalid.

## VI. Orientation, Qualification to Act, and Shared Affairs

### 1. Strategic representation cannot replace orientation

$\mathscr G_i$ answers “how is the current strategic situation organized?” $G_i$ answers “which states, actions, or retained conditions have what salience, priority, approach/avoid direction, or completion standard?”

Therefore:

$$
\boxed{\mathscr G_i\neq G_i}
$$

A more precise strategic representation does not automatically create a more legitimate orientation. More accurate prediction of another actor also does not automatically grant authority to control that actor.

### 2. Strategic advantage does not automatically create authorization

Even if an action has higher expected return, lower risk, or a superior formal property under the current $\widehat{\mathscr G}$, one cannot infer:

$$
\text{formally preferred}
\Rightarrow
\text{authorized for real-world implementation}.
$$

Where others' rights, shared resources, irreversible loss, public power, privacy, safety, or major asymmetry are involved, hand off to the authority, procedure-strength, verification, recovery, and residual-responsibility checks of [Action Responsibility Practice](action-responsibility-practice.md).

### 3. Power and role positions

Beyond predicting actions, strategic analysis should, where applicable, distinguish: who can acquire materials; who defines classifications, metrics, and success criteria; who proposes, decides, executes, verifies, or stops action; who can selectively disclose or restrict information; who can change interaction rules and entry points; who benefits and bears risk and external cost; and who can exit, refuse, appeal, repair, or demand reopening.

These positions affect strategic outcomes and also have independent significance for shared affairs. They must not be silently swallowed by a single payoff representation.

## VII. Domain and Formal-Tool Handoff

When actor boundaries, key factors, action spaces, others' orientations, information structures, temporal structures, joint compatibility, or real-world acquisition methods retain a substantive possibility of reopening, the problem remains open; formalization must not be used to conceal upstream representational unknowns.

After the joint strategic representation reaches the closure required for the current purpose, one may hand:

$$
\widehat{\mathscr G}
\xrightarrow{\text{formal tool}}
\text{strategy / response / equilibrium / path / comparison}
$$

to game theory or other formal tools. Formal tools answer “what follows under the currently and adequately specified objects, variables, actions, information, preferences, and rules?” This document answers “how are those strategic determinations formed and tested, and when do they have enough qualification to enter formalization?”

On entering a concrete domain, domain models and situational facts must still determine actors, states, actions, information, preferences, time, mechanisms, probabilities, rights, authorization, risk, thresholds, and validation conditions. Formal results must carry applicability scope, key assumptions, residual unknowns, and reopening conditions; authority for real-world action, third-party boundaries, verification, recovery, stopping, and exit are uniformly handed to [Action Responsibility Practice](action-responsibility-practice.md).

The minimum discipline is:

$$
\boxed{
\begin{gathered}
\text{permit strategic representations to form, but reject presenting them as complete reality;}\\
\text{permit formal solution, but reject allowing formal fields to force reality into closure in reverse;}\\
\text{permit strategic capability to affect outcomes, but reject automatically promoting capability into authorization or legitimacy.}
\end{gathered}
}
$$
