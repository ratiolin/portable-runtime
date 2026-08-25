from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Literal

DISTINCTION_GOVERNANCE_CONTRACT_VERSION = "distinction-governance-1.0"
DISTINCTION_GOVERNANCE_SOURCE_COMMIT = "ef9e490987ed47ebef3ac455851109304f24a97c"

QUALIFICATIONS = frozenset({"candidate", "qualified", "disqualified"})
ACTIVATIONS = frozenset({"active", "suspended"})

DECIDE_REVIEW = "decide_review_disposition"
APPLY_REVIEW_DISCHARGE = "apply_review_discharge"
DECIDE_QUALIFICATION = "decide_qualification"
APPLY_QUALIFICATION = "apply_qualification_transition"
DECIDE_ACTIVATION = "decide_activation"
APPLY_ACTIVATION = "apply_activation_transition"
RESOLVE_ASSIGNMENT = "resolve_assignment"
STATE_APPLY_OPERATIONS = frozenset({APPLY_QUALIFICATION, APPLY_ACTIVATION})

BasisAnchors = Mapping[str, str]
FreshnessAnchorLookup = Callable[[str], str | None]
AuthorityResourceKind = Literal["distinction_projection", "review_obligation", "assignment"]


@dataclass(frozen=True)
class DistinctionState:
    """Implementation name for the runtime projection of distinction state.

    The semantic axes represented here are qualification, activation, scope,
    and partition. ``version`` is operational sequencing metadata used by the
    runtime anchor; it is not a distinction-semantic axis.
    """

    qualification: str
    activation: str
    scope: frozenset[str]
    partition: tuple[frozenset[str], ...]
    version: int = 0

    @property
    def operational_anchor(self) -> str:
        return state_anchor(self)


# Formal D.5 name. Keep DistinctionState as the implementation/compatibility name.
RuntimeDistinctionProjection = DistinctionState


@dataclass(frozen=True)
class UseContext:
    """Deterministic use context for scope-aware usability checks."""

    name: str
    requested_scope: frozenset[str] = frozenset()


@dataclass(frozen=True)
class BlockingCondition:
    """Serializable, deterministic predicate controlling when an open Q blocks use."""

    context_names: frozenset[str] = frozenset()
    scope_any: frozenset[str] = frozenset()
    scope_all: frozenset[str] = frozenset()


@dataclass(frozen=True)
class GovernanceAuthorityTarget:
    """Structured resource target for governance authorization.

    Projection-bound targets distinguish authority over the same scheme under
    different scope/partition/operational anchors. ``None`` dimensions are
    explicit wildcards used only for deliberately broad grants.
    """

    kind: AuthorityResourceKind
    scheme_id: str
    resource_ref: str
    scope: frozenset[str] | None = None
    partition: tuple[frozenset[str], ...] | None = None
    operational_anchor: str | None = None


@dataclass(frozen=True)
class AuthorityRequest:
    actor: str
    operation: str
    target: GovernanceAuthorityTarget
    context: str


AuthorityCheck = Callable[[AuthorityRequest], bool]


@dataclass(frozen=True)
class Dependency:
    dependent: str
    basis: str
    kind: str
    context: str


@dataclass(frozen=True)
class ReviewObligation:
    id: str
    target: str
    trigger_ref: str
    basis_refs: tuple[str, ...]
    context: str
    blocking: bool = True
    blocking_condition: BlockingCondition | None = None
    closure_requirements: frozenset[str] = frozenset()
    invalidates_decisions: frozenset[str] = frozenset()


@dataclass(frozen=True)
class GovernanceDecision:
    id: str
    actor: str
    operation: str
    target: str
    context: str
    review_refs: tuple[str, ...]
    disposition: str
    expected_state_anchor: str
    basis_anchors: tuple[tuple[str, str], ...]
    scope_snapshot: frozenset[str]
    partition_snapshot: tuple[frozenset[str], ...]
    closure_facts: frozenset[str] = frozenset()
    required_qualification: str | None = None
    required_activation: str | None = None
    superseded: bool = False


@dataclass(frozen=True)
class GovernedApplication:
    id: str
    actor: str
    operation: str
    scheme_id: str
    target: str
    decision_ref: str
    context: str
    new_qualification: str | None = None
    new_activation: str | None = None
    review_obligation_id: str | None = None


@dataclass(frozen=True)
class ApplicationReceipt:
    application: GovernedApplication
    effect_kind: str
    pre_anchor: str
    post_anchor: str


@dataclass(frozen=True)
class AuthorityGrant:
    actor: str
    operation: str
    target: GovernanceAuthorityTarget | str
    context: str


@dataclass(frozen=True)
class GovernanceRuntime:
    obligations: Mapping[str, ReviewObligation] = field(default_factory=dict)
    decisions: Mapping[str, GovernanceDecision] = field(default_factory=dict)
    applications: Mapping[str, ApplicationReceipt] = field(default_factory=dict)


@dataclass(frozen=True)
class GovernanceConfiguration:
    # Scheme identity is a runtime-store key, not another projection axis.
    states: Mapping[str, DistinctionState]
    runtime: GovernanceRuntime = field(default_factory=GovernanceRuntime)


def canonical_partition(
    partition: tuple[frozenset[str], ...],
) -> tuple[tuple[str, ...], ...]:
    return tuple(sorted(tuple(sorted(cell)) for cell in partition))


def state_anchor(state: DistinctionState) -> str:
    scope = ",".join(sorted(state.scope))
    partition = repr(canonical_partition(state.partition))
    return (
        f"v={state.version}|q={state.qualification}|a={state.activation}"
        f"|scope={scope}|partition={partition}"
    )


def projection_authority_target(
    scheme_id: str,
    scope: frozenset[str],
    partition: tuple[frozenset[str], ...],
    operational_anchor: str,
) -> GovernanceAuthorityTarget:
    return GovernanceAuthorityTarget(
        kind="distinction_projection",
        scheme_id=scheme_id,
        resource_ref=f"distinction:{scheme_id}",
        scope=scope,
        partition=partition,
        operational_anchor=operational_anchor,
    )


def decision_authority_request(decision: GovernanceDecision) -> AuthorityRequest:
    return AuthorityRequest(
        actor=decision.actor,
        operation=decision.operation,
        target=projection_authority_target(
            decision.target,
            decision.scope_snapshot,
            decision.partition_snapshot,
            decision.expected_state_anchor,
        ),
        context=decision.context,
    )


def application_authority_request(
    application: GovernedApplication,
    decision: GovernanceDecision,
) -> AuthorityRequest:
    return AuthorityRequest(
        actor=application.actor,
        operation=application.operation,
        target=projection_authority_target(
            decision.target,
            decision.scope_snapshot,
            decision.partition_snapshot,
            decision.expected_state_anchor,
        ),
        context=application.context,
    )


def review_discharge_authority_request(
    application: GovernedApplication,
    obligation: ReviewObligation,
    state: DistinctionState,
) -> AuthorityRequest:
    return AuthorityRequest(
        actor=application.actor,
        operation=application.operation,
        target=GovernanceAuthorityTarget(
            kind="review_obligation",
            scheme_id=obligation.target,
            resource_ref=f"review_obligation:{obligation.id}",
            scope=state.scope,
            partition=state.partition,
            operational_anchor=state_anchor(state),
        ),
        context=application.context,
    )


def assignment_authority_request(
    *,
    actor: str,
    operation: str,
    scheme_id: str,
    item: str,
    assignment_mode: str,
    context: str,
    state: DistinctionState,
) -> AuthorityRequest:
    return AuthorityRequest(
        actor=actor,
        operation=operation,
        target=GovernanceAuthorityTarget(
            kind="assignment",
            scheme_id=scheme_id,
            resource_ref=f"assignment:{scheme_id}:{item}:{assignment_mode}",
            scope=state.scope,
            partition=state.partition,
            operational_anchor=state_anchor(state),
        ),
        context=context,
    )


def authority_target_covers(
    granted: GovernanceAuthorityTarget,
    requested: GovernanceAuthorityTarget,
) -> bool:
    if (
        granted.kind != requested.kind
        or granted.scheme_id != requested.scheme_id
        or granted.resource_ref != requested.resource_ref
    ):
        return False
    if granted.scope is not None and granted.scope != requested.scope:
        return False
    if granted.partition is not None and canonical_partition(granted.partition) != canonical_partition(requested.partition or ()): 
        return False
    return granted.operational_anchor is None or granted.operational_anchor == requested.operational_anchor


def _legacy_target_covers(granted: str, requested: GovernanceAuthorityTarget) -> bool:
    # Compatibility grants are deliberately broad scheme grants. New adapters
    # must emit structured targets; this branch exists only for the Phase B-D
    # pure conformance fixtures and pre-D.5 internal callers.
    return granted in {requested.scheme_id, requested.resource_ref}


def grant_authority(grants: Iterable[AuthorityGrant]) -> AuthorityCheck:
    frozen = tuple(grants)

    def allows(request: AuthorityRequest) -> bool:
        for grant in frozen:
            if (
                grant.actor != request.actor
                or grant.operation != request.operation
                or grant.context != request.context
            ):
                continue
            if isinstance(grant.target, GovernanceAuthorityTarget):
                if authority_target_covers(grant.target, request.target):
                    return True
            elif _legacy_target_covers(grant.target, request.target):
                return True
        return False

    return allows


def mapping_freshness(anchors: BasisAnchors) -> FreshnessAnchorLookup:
    return anchors.get


def obligations_anchor(obligations: Mapping[str, ReviewObligation]) -> str:
    return "|".join(sorted(obligations))


def partition_matches_scope(
    partition: tuple[frozenset[str], ...],
    scope: frozenset[str],
) -> bool:
    if not scope:
        return not partition
    if not partition:
        return False
    union: set[str] = set()
    for cell in partition:
        if not cell or union.intersection(cell):
            return False
        union.update(cell)
    return frozenset(union) == scope


def state_admissible(state: DistinctionState) -> bool:
    if state.qualification not in QUALIFICATIONS or state.activation not in ACTIVATIONS:
        return False
    if not partition_matches_scope(state.partition, state.scope):
        return False
    if state.activation == "active" and (
        state.qualification != "qualified" or not state.scope
    ):
        return False
    if state.qualification == "disqualified" and state.activation != "suspended":
        return False
    return bool(state.scope) or state.activation == "suspended"


def state_admissible_for(scheme_id: str, state: DistinctionState) -> bool:
    return bool(scheme_id) and state_admissible(state)


def global_state_admissible(config: GovernanceConfiguration) -> bool:
    return all(
        state_admissible_for(scheme_id, state)
        for scheme_id, state in config.states.items()
    )


def qualification_context(
    state: DistinctionState,
) -> tuple[frozenset[str], tuple[tuple[str, ...], ...]]:
    return state.scope, canonical_partition(state.partition)


def normalize_use_context(context: str | UseContext) -> UseContext:
    return context if isinstance(context, UseContext) else UseContext(name=context)


def scope_matches(scope: frozenset[str], context: str | UseContext) -> bool:
    use = normalize_use_context(context)
    return bool(scope) and (
        not use.requested_scope or use.requested_scope.issubset(scope)
    )


def blocking_condition_matches(
    condition: BlockingCondition,
    context: str | UseContext,
    state_scope: frozenset[str],
) -> bool:
    use = normalize_use_context(context)
    if condition.context_names and use.name not in condition.context_names:
        return False
    effective_scope = use.requested_scope or state_scope
    if condition.scope_any and not condition.scope_any.intersection(effective_scope):
        return False
    if condition.scope_all and not condition.scope_all.issubset(effective_scope):
        return False
    return True


def obligation_key(
    obligation: ReviewObligation,
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        obligation.target,
        obligation.trigger_ref,
        tuple(sorted(set(obligation.basis_refs))),
        obligation.context,
    )


def open_obligation(
    runtime: GovernanceRuntime,
    obligation: ReviewObligation,
) -> GovernanceRuntime | None:
    key = obligation_key(obligation)
    if any(
        obligation_key(existing) == key
        for existing in runtime.obligations.values()
    ):
        return None
    obligations = dict(runtime.obligations)
    obligations[obligation.id] = obligation
    return replace(runtime, obligations=obligations)


def commit_event_opening(
    config: GovernanceConfiguration,
    obligations: Iterable[ReviewObligation],
    event_key: str,
    processed_event_keys: frozenset[str],
) -> tuple[GovernanceConfiguration, frozenset[str]] | None:
    """Open review obligations without adding event history to Gamma=(Q,Dec,App)."""
    if event_key in processed_event_keys:
        return None
    requested = tuple(obligations)
    if any(obligation.trigger_ref != event_key for obligation in requested):
        return None
    runtime = config.runtime
    for obligation in requested:
        candidate = open_obligation(runtime, obligation)
        if candidate is not None:
            runtime = candidate
    return replace(config, runtime=runtime), processed_event_keys | frozenset({event_key})


def direct_review_targets(
    dependencies: Iterable[Dependency],
    changed_basis: str,
    context: str,
) -> set[str]:
    return {
        dependency.dependent
        for dependency in dependencies
        if dependency.basis == changed_basis and dependency.context == context
    }


def obligation_blocks(
    obligation: ReviewObligation,
    context: str | UseContext,
    state_scope: frozenset[str],
) -> bool:
    if not obligation.blocking:
        return False
    if obligation.blocking_condition is not None:
        return blocking_condition_matches(obligation.blocking_condition, context, state_scope)
    use = normalize_use_context(context)
    return obligation.context == use.name


def blocking_review_open(
    config: GovernanceConfiguration,
    scheme_id: str,
    context: str | UseContext,
) -> bool:
    state = config.states.get(scheme_id)
    if state is None:
        return False
    return any(
        obligation.target == scheme_id
        and obligation_blocks(obligation, context, state.scope)
        for obligation in config.runtime.obligations.values()
    )


def usable(
    config: GovernanceConfiguration,
    scheme_id: str,
    context: str | UseContext,
) -> bool:
    state = config.states.get(scheme_id)
    return bool(
        state
        and state.qualification == "qualified"
        and state.activation == "active"
        and scope_matches(state.scope, context)
        and not blocking_review_open(config, scheme_id, context)
    )


def decision_recorded(
    decision: GovernanceDecision,
    config: GovernanceConfiguration,
) -> bool:
    return config.runtime.decisions.get(decision.id) == decision


def application_committed(
    application: GovernedApplication,
    config: GovernanceConfiguration,
) -> bool:
    receipt = config.runtime.applications.get(application.id)
    return receipt is not None and receipt.application == application


def relevant_basis_unchanged(
    decision: GovernanceDecision,
    freshness: FreshnessAnchorLookup,
) -> bool:
    return all(freshness(basis) == anchor for basis, anchor in decision.basis_anchors)


def no_invalidating_review(
    decision: GovernanceDecision,
    config: GovernanceConfiguration,
) -> bool:
    return not any(
        decision.id in obligation.invalidates_decisions
        for obligation in config.runtime.obligations.values()
    )


def common_decision_freshness(
    decision: GovernanceDecision,
    config: GovernanceConfiguration,
    freshness: FreshnessAnchorLookup,
) -> bool:
    return (
        decision_recorded(decision, config)
        and not decision.superseded
        and relevant_basis_unchanged(decision, freshness)
        and no_invalidating_review(decision, config)
    )


def decision_fresh_for_application(
    decision: GovernanceDecision,
    config: GovernanceConfiguration,
    freshness: FreshnessAnchorLookup,
) -> bool:
    state = config.states.get(decision.target)
    if state is None:
        return False
    return (
        common_decision_freshness(decision, config, freshness)
        and state_anchor(state) == decision.expected_state_anchor
        and state.scope == decision.scope_snapshot
        and canonical_partition(state.partition)
        == canonical_partition(decision.partition_snapshot)
    )


def precondition(
    application: GovernedApplication,
    config: GovernanceConfiguration,
) -> bool:
    if (
        not application.id
        or not application.operation
        or not application.target
        or not application.scheme_id
    ):
        return False
    if (
        application.id in config.runtime.applications
        or application.scheme_id not in config.states
    ):
        return False
    return (
        application.operation != APPLY_REVIEW_DISCHARGE
        or bool(application.review_obligation_id)
    )


def candidate_state_effect(
    application: GovernedApplication,
    state: DistinctionState,
) -> DistinctionState:
    return replace(
        state,
        qualification=(
            application.new_qualification
            if application.new_qualification is not None
            else state.qualification
        ),
        activation=(
            application.new_activation
            if application.new_activation is not None
            else state.activation
        ),
        version=state.version + 1,
    )


def candidate_discharge_effect(
    obligation_id: str,
    runtime: GovernanceRuntime,
) -> Mapping[str, ReviewObligation]:
    candidate = dict(runtime.obligations)
    candidate.pop(obligation_id, None)
    return candidate


def linked(
    application: GovernedApplication,
    decision: GovernanceDecision,
) -> bool:
    if (
        application.decision_ref != decision.id
        or application.scheme_id != decision.target
    ):
        return False
    if application.operation == APPLY_REVIEW_DISCHARGE:
        return decision.disposition in {"no_change", "transition_required"}
    compatibility = {
        DECIDE_QUALIFICATION: APPLY_QUALIFICATION,
        DECIDE_ACTIVATION: APPLY_ACTIVATION,
    }
    return compatibility.get(decision.operation) == application.operation


def effect_matches_decision(
    decision: GovernanceDecision,
    state: DistinctionState,
) -> bool:
    qualification_matches = (
        decision.required_qualification is None
        or state.qualification == decision.required_qualification
    )
    activation_matches = (
        decision.required_activation is None
        or state.activation == decision.required_activation
    )
    return qualification_matches and activation_matches


def review_decision_input_matches(
    decision: GovernanceDecision,
    config: GovernanceConfiguration,
) -> bool:
    if not decision.review_refs:
        return False
    decision_basis_keys = set(dict(decision.basis_anchors))
    for obligation_id in decision.review_refs:
        obligation = config.runtime.obligations.get(obligation_id)
        if obligation is None:
            return False
        if obligation.target != decision.target or obligation.context != decision.context:
            return False
        if not set(obligation.basis_refs).issubset(decision_basis_keys):
            return False
    return True


def decision_record_admissible(
    config: GovernanceConfiguration,
    decision: GovernanceDecision,
    authority: AuthorityCheck,
) -> bool:
    existing = config.runtime.decisions.get(decision.id)
    if existing is not None:
        return existing == decision
    return (
        decision.target in config.states
        and authority(decision_authority_request(decision))
        and review_decision_input_matches(decision, config)
    )


def record_decision(
    config: GovernanceConfiguration,
    decision: GovernanceDecision,
    authority: AuthorityCheck,
) -> GovernanceConfiguration | None:
    if not decision_record_admissible(config, decision, authority):
        return None
    existing = config.runtime.decisions.get(decision.id)
    if existing is not None:
        return config
    decisions = dict(config.runtime.decisions)
    decisions[decision.id] = decision
    return replace(config, runtime=replace(config.runtime, decisions=decisions))


def closure_admissible(
    decision: GovernanceDecision,
    obligation: ReviewObligation,
    config: GovernanceConfiguration,
    freshness: FreshnessAnchorLookup,
) -> bool:
    if not decision_recorded(decision, config):
        return False
    current = config.runtime.obligations.get(obligation.id)
    if (
        current is None
        or current != obligation
        or obligation.id not in decision.review_refs
    ):
        return False
    if decision.target != obligation.target or decision.context != obligation.context:
        return False
    if decision.disposition not in {"no_change", "transition_required"}:
        return False
    state = config.states.get(decision.target)
    if state is None:
        return False
    return (
        state.scope == decision.scope_snapshot
        and canonical_partition(state.partition)
        == canonical_partition(decision.partition_snapshot)
        and relevant_basis_unchanged(decision, freshness)
        and obligation.closure_requirements.issubset(decision.closure_facts)
    )


def application_admissible(
    config: GovernanceConfiguration,
    application: GovernedApplication,
    authority: AuthorityCheck,
    freshness: FreshnessAnchorLookup,
) -> bool:
    if (
        application.operation not in STATE_APPLY_OPERATIONS
        or application.target != application.scheme_id
    ):
        return False
    decision = config.runtime.decisions.get(application.decision_ref)
    if decision is None:
        return False
    if not authority(application_authority_request(application, decision)):
        return False
    if not linked(application, decision) or not decision_fresh_for_application(
        decision,
        config,
        freshness,
    ):
        return False
    if not precondition(application, config):
        return False
    current = config.states.get(application.scheme_id)
    if current is None:
        return False
    candidate = candidate_state_effect(application, current)
    return (
        state_admissible_for(application.scheme_id, candidate)
        and decision.disposition == "transition_required"
        and effect_matches_decision(decision, candidate)
    )


def apply_state_transition(
    config: GovernanceConfiguration,
    application: GovernedApplication,
    authority: AuthorityCheck,
    freshness: FreshnessAnchorLookup,
) -> GovernanceConfiguration | None:
    if not application_admissible(config, application, authority, freshness):
        return None
    current = config.states[application.scheme_id]
    candidate = candidate_state_effect(application, current)
    receipt = ApplicationReceipt(
        application=application,
        effect_kind="state",
        pre_anchor=state_anchor(current),
        post_anchor=state_anchor(candidate),
    )
    states = dict(config.states)
    states[application.scheme_id] = candidate
    applications = dict(config.runtime.applications)
    applications[application.id] = receipt
    return replace(
        config,
        states=states,
        runtime=replace(config.runtime, applications=applications),
    )


def required_transition_realized(
    decision: GovernanceDecision,
    state_application: GovernedApplication,
    config: GovernanceConfiguration,
) -> bool:
    state = config.states.get(decision.target)
    receipt = config.runtime.applications.get(state_application.id)
    if state is None or receipt is None:
        return False
    return (
        decision.disposition == "transition_required"
        and receipt.application == state_application
        and state_application.decision_ref == decision.id
        and linked(state_application, decision)
        and receipt.effect_kind == "state"
        and receipt.pre_anchor == decision.expected_state_anchor
        and receipt.post_anchor == state_anchor(state)
        and effect_matches_decision(decision, state)
        and state_admissible_for(decision.target, state)
    )


def decision_fresh_for_discharge(
    decision: GovernanceDecision,
    config: GovernanceConfiguration,
    freshness: FreshnessAnchorLookup,
    state_application: GovernedApplication | None = None,
) -> bool:
    state = config.states.get(decision.target)
    if state is None or not common_decision_freshness(decision, config, freshness):
        return False
    if decision.disposition == "no_change":
        return (
            state_anchor(state) == decision.expected_state_anchor
            and state.scope == decision.scope_snapshot
            and canonical_partition(state.partition)
            == canonical_partition(decision.partition_snapshot)
        )
    if decision.disposition != "transition_required" or state_application is None:
        return False
    return required_transition_realized(decision, state_application, config)


def discharge_admissible(
    config: GovernanceConfiguration,
    application: GovernedApplication,
    authority: AuthorityCheck,
    freshness: FreshnessAnchorLookup,
    state_application: GovernedApplication | None = None,
) -> bool:
    if application.operation != APPLY_REVIEW_DISCHARGE:
        return False
    decision = config.runtime.decisions.get(application.decision_ref)
    if decision is None or application.review_obligation_id is None:
        return False
    obligation = config.runtime.obligations.get(application.review_obligation_id)
    if (
        obligation is None
        or application.target != f"review_obligation:{obligation.id}"
    ):
        return False
    state = config.states.get(decision.target)
    if state is None or not authority(
        review_discharge_authority_request(application, obligation, state)
    ):
        return False
    if not precondition(application, config) or not linked(application, decision):
        return False
    if not closure_admissible(decision, obligation, config, freshness):
        return False
    if not decision_fresh_for_discharge(
        decision,
        config,
        freshness,
        state_application,
    ):
        return False
    if decision.disposition == "no_change":
        return state_application is None
    return decision.disposition == "transition_required" and state_application is not None


def apply_review_discharge(
    config: GovernanceConfiguration,
    application: GovernedApplication,
    authority: AuthorityCheck,
    freshness: FreshnessAnchorLookup,
    state_application: GovernedApplication | None = None,
) -> GovernanceConfiguration | None:
    if not discharge_admissible(
        config,
        application,
        authority,
        freshness,
        state_application,
    ):
        return None
    obligation_id = application.review_obligation_id
    if obligation_id is None:
        return None
    pre_anchor = obligations_anchor(config.runtime.obligations)
    obligations = candidate_discharge_effect(obligation_id, config.runtime)
    receipt = ApplicationReceipt(
        application=application,
        effect_kind="review_discharge",
        pre_anchor=pre_anchor,
        post_anchor=obligations_anchor(obligations),
    )
    applications = dict(config.runtime.applications)
    applications[application.id] = receipt
    runtime = replace(
        config.runtime,
        obligations=obligations,
        applications=applications,
    )
    return replace(config, runtime=runtime)


def transition_admissible(
    config: GovernanceConfiguration,
    application: GovernedApplication,
    authority: AuthorityCheck,
    freshness: FreshnessAnchorLookup,
    state_application: GovernedApplication | None = None,
) -> bool:
    if application.operation == APPLY_REVIEW_DISCHARGE:
        return discharge_admissible(
            config,
            application,
            authority,
            freshness,
            state_application,
        )
    return application_admissible(config, application, authority, freshness)


def resolve_allowed(
    config: GovernanceConfiguration,
    authority: AuthorityCheck,
    actor: str,
    scheme_id: str,
    item: str,
    cell: frozenset[str],
    assignment_mode: str,
    context: str | UseContext,
) -> bool:
    state = config.states.get(scheme_id)
    if state is None:
        return False
    use = normalize_use_context(context)
    request = assignment_authority_request(
        actor=actor,
        operation=RESOLVE_ASSIGNMENT,
        scheme_id=scheme_id,
        item=item,
        assignment_mode=assignment_mode,
        context=use.name,
        state=state,
    )
    return (
        usable(config, scheme_id, use)
        and item in state.scope
        and cell in state.partition
        and item in cell
        and authority(request)
    )
