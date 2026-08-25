from dataclasses import replace

from portable_runtime.governance.distinction import (
    APPLY_QUALIFICATION,
    APPLY_REVIEW_DISCHARGE,
    DECIDE_QUALIFICATION,
    DECIDE_REVIEW,
    RESOLVE_ASSIGNMENT,
    AuthorityGrant,
    Dependency,
    DistinctionState,
    GovernanceConfiguration,
    GovernanceDecision,
    GovernedApplication,
    ReviewObligation,
    application_committed,
    apply_review_discharge,
    apply_state_transition,
    blocking_review_open,
    candidate_state_effect,
    closure_admissible,
    commit_event_opening,
    decision_fresh_for_application,
    direct_review_targets,
    global_state_admissible,
    grant_authority,
    mapping_freshness,
    obligation_key,
    open_obligation,
    precondition,
    qualification_context,
    record_decision,
    required_transition_realized,
    resolve_allowed,
    review_decision_input_matches,
    state_admissible,
    state_anchor,
    transition_admissible,
    usable,
)

CURRENT_BASIS = mapping_freshness({"evidence": "evidence:v1"})


def base_state(version: int = 10) -> DistinctionState:
    return DistinctionState(
        qualification="qualified",
        activation="active",
        scope=frozenset({"a", "b"}),
        partition=(frozenset({"a"}), frozenset({"b"})),
        version=version,
    )


def second_state(version: int = 3) -> DistinctionState:
    return DistinctionState(
        qualification="qualified",
        activation="suspended",
        scope=frozenset({"x"}),
        partition=(frozenset({"x"}),),
        version=version,
    )


def base_config(version: int = 10) -> GovernanceConfiguration:
    return GovernanceConfiguration(states={"d": base_state(version), "d2": second_state()})


def obligation(
    qid: str = "q1",
    trigger: str = "e1",
    target: str = "d",
    context: str = "ctx",
    basis_refs: tuple[str, ...] = ("evidence",),
    requirements: frozenset[str] = frozenset({"basis_checked"}),
    invalidates: frozenset[str] = frozenset(),
) -> ReviewObligation:
    return ReviewObligation(
        id=qid,
        target=target,
        trigger_ref=trigger,
        basis_refs=basis_refs,
        context=context,
        blocking=True,
        closure_requirements=requirements,
        invalidates_decisions=invalidates,
    )


def with_obligation(config: GovernanceConfiguration, value: ReviewObligation) -> GovernanceConfiguration:
    runtime = open_obligation(config.runtime, value)
    assert runtime is not None
    return replace(config, runtime=runtime)


def without_obligation(config: GovernanceConfiguration, qid: str) -> GovernanceConfiguration:
    obligations = dict(config.runtime.obligations)
    obligations.pop(qid, None)
    return replace(config, runtime=replace(config.runtime, obligations=obligations))


def review_decision(
    config: GovernanceConfiguration,
    did: str = "dec-review",
    qid: str = "q1",
    disposition: str = "no_change",
    target: str = "d",
    context: str = "ctx",
    basis_anchors: tuple[tuple[str, str], ...] = (("evidence", "evidence:v1"),),
) -> GovernanceDecision:
    state = config.states[target]
    return GovernanceDecision(
        id=did,
        actor="reviewer",
        operation=DECIDE_REVIEW,
        target=target,
        context=context,
        review_refs=(qid,),
        disposition=disposition,
        expected_state_anchor=state_anchor(state),
        basis_anchors=basis_anchors,
        scope_snapshot=state.scope,
        partition_snapshot=state.partition,
        closure_facts=frozenset({"basis_checked"}),
    )


def qualification_decision(
    config: GovernanceConfiguration,
    did: str = "dec-q",
    qid: str = "q1",
    target: str = "d",
    required_qualification: str = "qualified",
    required_activation: str = "suspended",
) -> GovernanceDecision:
    state = config.states[target]
    return GovernanceDecision(
        id=did,
        actor="reviewer",
        operation=DECIDE_QUALIFICATION,
        target=target,
        context="ctx",
        review_refs=(qid,),
        disposition="transition_required",
        expected_state_anchor=state_anchor(state),
        basis_anchors=(("evidence", "evidence:v1"),),
        scope_snapshot=state.scope,
        partition_snapshot=state.partition,
        closure_facts=frozenset({"basis_checked"}),
        required_qualification=required_qualification,
        required_activation=required_activation,
    )


def state_app(decision: GovernanceDecision, app_id: str = "app1", actor: str = "operator") -> GovernedApplication:
    return GovernedApplication(
        id=app_id,
        actor=actor,
        operation=APPLY_QUALIFICATION,
        scheme_id=decision.target,
        target=decision.target,
        decision_ref=decision.id,
        context=decision.context,
        new_qualification=decision.required_qualification,
        new_activation=decision.required_activation,
    )


def discharge_app(
    decision: GovernanceDecision,
    qid: str = "q1",
    app_id: str = "rda1",
    actor: str = "closer",
) -> GovernedApplication:
    return GovernedApplication(
        id=app_id,
        actor=actor,
        operation=APPLY_REVIEW_DISCHARGE,
        scheme_id=decision.target,
        target=f"review_obligation:{qid}",
        decision_ref=decision.id,
        context=decision.context,
        review_obligation_id=qid,
    )


def authority_for(*grants: AuthorityGrant):
    return grant_authority(grants)


def decision_grant(decision: GovernanceDecision) -> AuthorityGrant:
    return AuthorityGrant(decision.actor, decision.operation, decision.target, decision.context)


def app_grant(application: GovernedApplication) -> AuthorityGrant:
    return AuthorityGrant(application.actor, application.operation, application.target, application.context)


def test_01_candidate_active_inadmissible() -> None:
    state = DistinctionState("candidate", "active", frozenset({"a"}), (frozenset({"a"}),))
    assert not state_admissible(state)


def test_02_partition_must_match_scope() -> None:
    state = DistinctionState("qualified", "suspended", frozenset({"a", "b"}), (frozenset({"a"}),))
    assert not state_admissible(state)


def test_03_global_store_is_multi_scheme_and_admissible() -> None:
    config = base_config()
    assert set(config.states) == {"d", "d2"}
    assert global_state_admissible(config)


def test_04_replay_deduplicates_same_open_obligation() -> None:
    config = base_config()
    q1 = obligation("q1", "same-event")
    q2 = obligation("q2", "same-event")
    runtime = open_obligation(config.runtime, q1)
    assert runtime is not None
    assert open_obligation(runtime, q2) is None
    assert obligation_key(q1) == obligation_key(q2)


def test_05_multiple_blockers_do_not_silently_unblock() -> None:
    config = with_obligation(base_config(), obligation("q1", "e1"))
    config = with_obligation(config, obligation("q2", "e2"))
    config = without_obligation(config, "q1")
    assert blocking_review_open(config, "d", "ctx")
    assert not usable(config, "d", "ctx")


def test_06_dependency_is_direct_not_transitive() -> None:
    deps = [Dependency("x", "b", "evidential", "ctx"), Dependency("y", "x", "qualification_basis", "ctx")]
    assert direct_review_targets(deps, "b", "ctx") == {"x"}


def test_07_same_event_replay_after_discharge_does_not_reopen() -> None:
    config = base_config()
    q = obligation("q1", "event-instance-1")
    opened = commit_event_opening(config, [q], "event-instance-1", frozenset())
    assert opened is not None
    config, processed = opened
    config = without_obligation(config, q.id)
    assert commit_event_opening(config, [q], "event-instance-1", processed) is None
    assert q.id not in config.runtime.obligations


def test_08_new_event_instance_may_open_new_review() -> None:
    opened = commit_event_opening(base_config(), [obligation("q1", "e1")], "e1", frozenset())
    assert opened is not None
    config, processed = opened
    config = without_obligation(config, "q1")
    reopened = commit_event_opening(config, [obligation("q2", "e2")], "e2", processed)
    assert reopened is not None
    config, _ = reopened
    assert "q2" in config.runtime.obligations


def test_09_event_opening_frame_preserves_state_decisions_apps() -> None:
    config = base_config()
    opened = commit_event_opening(config, [obligation("q1", "e1")], "e1", frozenset())
    assert opened is not None
    after, _ = opened
    assert after.states == config.states
    assert after.runtime.decisions == config.runtime.decisions
    assert after.runtime.applications == config.runtime.applications


def test_10_decision_record_frame_preserves_state_q_apps() -> None:
    config = with_obligation(base_config(), obligation())
    decision = review_decision(config)
    after = record_decision(config, decision, authority_for(decision_grant(decision)))
    assert after is not None
    assert after.states == config.states
    assert after.runtime.obligations == config.runtime.obligations
    assert after.runtime.applications == config.runtime.applications


def test_11_unrecorded_decision_cannot_drive_state_application() -> None:
    config = with_obligation(base_config(), obligation())
    decision = qualification_decision(config)
    application = state_app(decision)
    assert not transition_admissible(config, application, authority_for(app_grant(application)), CURRENT_BASIS)


def test_12_decision_authority_does_not_grant_state_mutation() -> None:
    config = with_obligation(base_config(), obligation())
    decision = qualification_decision(config)
    recorded = record_decision(config, decision, authority_for(decision_grant(decision)))
    assert recorded is not None
    application = state_app(decision, actor="reviewer")
    assert not transition_admissible(recorded, application, authority_for(decision_grant(decision)), CURRENT_BASIS)


def test_13_state_application_is_atomic_and_frame_preserving() -> None:
    config = with_obligation(base_config(), obligation())
    decision = qualification_decision(config)
    recorded = record_decision(config, decision, authority_for(decision_grant(decision)))
    assert recorded is not None
    application = state_app(decision)
    applied = apply_state_transition(recorded, application, authority_for(app_grant(application)), CURRENT_BASIS)
    assert applied is not None
    assert application_committed(application, applied)
    assert applied.runtime.obligations == recorded.runtime.obligations
    assert applied.runtime.decisions == recorded.runtime.decisions
    assert applied.states["d2"] == recorded.states["d2"]


def test_14_failed_application_is_not_recorded() -> None:
    config = base_config()
    decision = qualification_decision(config)
    application = state_app(decision)
    assert apply_state_transition(config, application, authority_for(app_grant(application)), CURRENT_BASIS) is None
    assert not application_committed(application, config)


def test_15_duplicate_application_id_is_rejected() -> None:
    config = with_obligation(base_config(), obligation())
    decision = qualification_decision(config)
    recorded = record_decision(config, decision, authority_for(decision_grant(decision)))
    assert recorded is not None
    application = state_app(decision)
    applied = apply_state_transition(recorded, application, authority_for(app_grant(application)), CURRENT_BASIS)
    assert applied is not None
    assert not precondition(application, applied)


def test_16_candidate_effect_is_pure_before_commit() -> None:
    config = base_config()
    before = config.states["d"]
    application = GovernedApplication(
        "candidate", "op", APPLY_QUALIFICATION, "d", "d", "dec", "ctx",
        new_activation="suspended",
    )
    candidate = candidate_state_effect(application, before)
    assert config.states["d"] == before
    assert candidate != before


def test_17_relevant_basis_change_makes_decision_stale() -> None:
    config = with_obligation(base_config(), obligation())
    decision = qualification_decision(config)
    recorded = record_decision(config, decision, authority_for(decision_grant(decision)))
    assert recorded is not None
    assert decision_fresh_for_application(decision, recorded, CURRENT_BASIS)
    assert not decision_fresh_for_application(decision, recorded, mapping_freshness({"evidence": "evidence:v2"}))


def test_18_closure_is_rechecked_at_discharge() -> None:
    q = obligation()
    config = with_obligation(base_config(), q)
    decision = review_decision(config)
    recorded = record_decision(config, decision, authority_for(decision_grant(decision)))
    assert recorded is not None
    assert closure_admissible(decision, q, recorded, CURRENT_BASIS)
    assert not closure_admissible(decision, q, recorded, mapping_freshness({"evidence": "evidence:v2"}))


def test_19_no_change_discharge_rechecks_decision_freshness() -> None:
    config = with_obligation(base_config(), obligation())
    decision = review_decision(config)
    recorded = record_decision(config, decision, authority_for(decision_grant(decision)))
    assert recorded is not None
    discharge = discharge_app(decision)
    assert apply_review_discharge(
        recorded,
        discharge,
        authority_for(app_grant(discharge)),
        mapping_freshness({"evidence": "evidence:v2"}),
    ) is None
    assert "q1" in recorded.runtime.obligations


def test_20_transition_required_cannot_discharge_before_state_effect() -> None:
    config = with_obligation(base_config(), obligation())
    decision = qualification_decision(config)
    recorded = record_decision(config, decision, authority_for(decision_grant(decision)))
    assert recorded is not None
    discharge = discharge_app(decision)
    assert apply_review_discharge(recorded, discharge, authority_for(app_grant(discharge)), CURRENT_BASIS) is None


def test_21_transition_discharge_requires_current_application_provenance() -> None:
    config = with_obligation(base_config(), obligation())
    decision = qualification_decision(config)
    recorded = record_decision(config, decision, authority_for(decision_grant(decision)))
    assert recorded is not None
    application = state_app(decision)
    applied = apply_state_transition(recorded, application, authority_for(app_grant(application)), CURRENT_BASIS)
    assert applied is not None
    assert required_transition_realized(decision, application, applied)
    changed = dict(applied.states)
    current = changed["d"]
    changed["d"] = replace(current, version=current.version + 1)
    drifted = replace(applied, states=changed)
    assert not required_transition_realized(decision, application, drifted)


def test_22_review_discharge_frame_preserves_state_decisions() -> None:
    config = with_obligation(base_config(), obligation())
    decision = review_decision(config)
    recorded = record_decision(config, decision, authority_for(decision_grant(decision)))
    assert recorded is not None
    discharge = discharge_app(decision)
    closed = apply_review_discharge(recorded, discharge, authority_for(app_grant(discharge)), CURRENT_BASIS)
    assert closed is not None
    assert closed.states == recorded.states
    assert closed.runtime.decisions == recorded.runtime.decisions
    assert application_committed(discharge, closed)


def test_23_state_application_does_not_auto_discharge_review() -> None:
    config = with_obligation(base_config(), obligation())
    decision = qualification_decision(config)
    recorded = record_decision(config, decision, authority_for(decision_grant(decision)))
    assert recorded is not None
    application = state_app(decision)
    applied = apply_state_transition(recorded, application, authority_for(app_grant(application)), CURRENT_BASIS)
    assert applied is not None
    assert "q1" in applied.runtime.obligations


def test_24_qualification_context_is_indexed_by_scope_partition() -> None:
    s1 = base_state()
    s2 = DistinctionState("qualified", "active", frozenset({"a", "b"}), (frozenset({"a", "b"}),), version=10)
    assert qualification_context(s1) != qualification_context(s2)


def test_25_blocking_review_prevents_resolve_assignment() -> None:
    config = base_config()
    target = "assignment:d:a:observation"
    authority = authority_for(AuthorityGrant("classifier", RESOLVE_ASSIGNMENT, target, "ctx"))
    assert resolve_allowed(config, authority, "classifier", "d", "a", frozenset({"a"}), "observation", "ctx")
    blocked = with_obligation(config, obligation())
    assert not resolve_allowed(blocked, authority, "classifier", "d", "a", frozenset({"a"}), "observation", "ctx")


def test_26_resolve_requires_object_scope_partition_and_authority() -> None:
    config = base_config()
    target = "assignment:d:a:observation"
    authority = authority_for(AuthorityGrant("classifier", RESOLVE_ASSIGNMENT, target, "ctx"))
    assert not resolve_allowed(config, authority, "classifier", "d", "z", frozenset({"a"}), "observation", "ctx")
    assert not resolve_allowed(config, authority_for(), "classifier", "d", "a", frozenset({"a"}), "observation", "ctx")


def test_27_unrelated_scheme_state_is_not_mutated_by_application() -> None:
    config = with_obligation(base_config(), obligation())
    decision = qualification_decision(config)
    recorded = record_decision(config, decision, authority_for(decision_grant(decision)))
    assert recorded is not None
    before = recorded.states["d2"]
    application = state_app(decision)
    applied = apply_state_transition(recorded, application, authority_for(app_grant(application)), CURRENT_BASIS)
    assert applied is not None
    assert applied.states["d2"] == before


def test_28_record_decision_rejects_unmatched_review_target_context() -> None:
    for mismatch in ("target", "context", "basis", "empty_refs"):
        config = base_config()
        if mismatch == "target":
            q = obligation(target="d2")
            decision = review_decision(config)
        elif mismatch == "context":
            q = obligation(context="other")
            decision = review_decision(config)
        elif mismatch == "basis":
            q = obligation(basis_refs=("evidence", "missing"))
            decision = review_decision(config)
        else:
            q = obligation()
            decision = replace(review_decision(config), review_refs=())
        config = with_obligation(config, q)
        assert not review_decision_input_matches(decision, config)
        assert record_decision(config, decision, authority_for(decision_grant(decision))) is None


def test_29_transition_required_cannot_be_satisfied_by_unrelated_application() -> None:
    config = with_obligation(base_config(), obligation("qA", "eA"))
    config = with_obligation(config, obligation("qB", "eB"))
    dec_a = qualification_decision(config, did="dec-A", qid="qA")
    dec_b = qualification_decision(config, did="dec-B", qid="qB")
    recorded = record_decision(config, dec_a, authority_for(decision_grant(dec_a)))
    assert recorded is not None
    recorded = record_decision(recorded, dec_b, authority_for(decision_grant(dec_b)))
    assert recorded is not None
    app_b = state_app(dec_b, app_id="app-B")
    applied = apply_state_transition(recorded, app_b, authority_for(app_grant(app_b)), CURRENT_BASIS)
    assert applied is not None
    assert not required_transition_realized(dec_a, app_b, applied)
    rda_a = discharge_app(dec_a, qid="qA", app_id="rda-A")
    assert apply_review_discharge(
        applied,
        rda_a,
        authority_for(app_grant(rda_a)),
        CURRENT_BASIS,
        state_application=app_b,
    ) is None
    assert "qA" in applied.runtime.obligations


def test_30_decision_id_cannot_be_rebound_and_identical_replay_is_idempotent() -> None:
    config = with_obligation(base_config(), obligation())
    decision = review_decision(config, did="stable-id")
    authority = authority_for(decision_grant(decision))
    recorded = record_decision(config, decision, authority)
    assert recorded is not None
    replayed = record_decision(recorded, decision, authority)
    assert replayed == recorded
    rebound = replace(decision, disposition="transition_required")
    assert record_decision(recorded, rebound, authority) is None
    assert recorded.runtime.decisions["stable-id"] == decision
