from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from portable_runtime.core.models import Event
from portable_runtime.governance.distinction import (
    ApplicationReceipt,
    BlockingCondition,
    DistinctionState,
    GovernanceConfiguration,
    GovernanceDecision,
    GovernanceRuntime,
    GovernedApplication,
    ReviewObligation,
    global_state_admissible,
    state_admissible_for,
)

GOVERNANCE_STATE_SEEDED = "governance.distinction.state.seeded"
GOVERNANCE_REVIEW_OPENED = "governance.distinction.review.opened"
GOVERNANCE_DECISION_RECORDED = "governance.distinction.decision.recorded"
GOVERNANCE_APPLICATION_COMMITTED = "governance.distinction.application.committed"
GOVERNANCE_EVENT_PROCESSED = "governance.distinction.event.processed"

GOVERNANCE_HISTORY_EVENT_TYPES = frozenset(
    {
        GOVERNANCE_STATE_SEEDED,
        GOVERNANCE_REVIEW_OPENED,
        GOVERNANCE_DECISION_RECORDED,
        GOVERNANCE_APPLICATION_COMMITTED,
        GOVERNANCE_EVENT_PROCESSED,
    }
)


@dataclass(frozen=True)
class CanonicalGovernanceHistory:
    configuration: GovernanceConfiguration
    processed_event_obligations: dict[str, tuple[str, ...]]


def _event_id(prefix: str, identity: str) -> str:
    digest = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return f"gov_{prefix}_{digest}"


def _blocking_payload(value: BlockingCondition | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "context_names": sorted(value.context_names),
        "scope_any": sorted(value.scope_any),
        "scope_all": sorted(value.scope_all),
    }


def _restore_blocking(value: object) -> BlockingCondition | None:
    if not isinstance(value, dict):
        return None
    return BlockingCondition(
        context_names=frozenset(str(item) for item in value.get("context_names", [])),
        scope_any=frozenset(str(item) for item in value.get("scope_any", [])),
        scope_all=frozenset(str(item) for item in value.get("scope_all", [])),
    )


def state_payload(scheme_id: str, state: DistinctionState) -> dict[str, Any]:
    return {
        "scheme_id": scheme_id,
        "qualification": state.qualification,
        "activation": state.activation,
        "scope": sorted(state.scope),
        "partition": [sorted(cell) for cell in state.partition],
        "version": state.version,
    }


def restore_state(payload: dict[str, Any]) -> tuple[str, DistinctionState]:
    scheme_id = str(payload["scheme_id"])
    state = DistinctionState(
        qualification=str(payload["qualification"]),
        activation=str(payload["activation"]),
        scope=frozenset(str(item) for item in payload.get("scope", [])),
        partition=tuple(
            frozenset(str(item) for item in cell)
            for cell in payload.get("partition", [])
        ),
        version=int(payload.get("version", 0)),
    )
    if not state_admissible_for(scheme_id, state):
        raise ValueError("canonical governance history contains inadmissible state")
    return scheme_id, state


def obligation_payload(value: ReviewObligation) -> dict[str, Any]:
    return {
        "id": value.id,
        "target": value.target,
        "trigger_ref": value.trigger_ref,
        "basis_refs": list(value.basis_refs),
        "context": value.context,
        "blocking": value.blocking,
        "blocking_condition": _blocking_payload(value.blocking_condition),
        "closure_requirements": sorted(value.closure_requirements),
        "invalidates_decisions": sorted(value.invalidates_decisions),
    }


def restore_obligation(payload: dict[str, Any]) -> ReviewObligation:
    return ReviewObligation(
        id=str(payload["id"]),
        target=str(payload["target"]),
        trigger_ref=str(payload["trigger_ref"]),
        basis_refs=tuple(str(item) for item in payload.get("basis_refs", [])),
        context=str(payload["context"]),
        blocking=bool(payload.get("blocking", True)),
        blocking_condition=_restore_blocking(payload.get("blocking_condition")),
        closure_requirements=frozenset(
            str(item) for item in payload.get("closure_requirements", [])
        ),
        invalidates_decisions=frozenset(
            str(item) for item in payload.get("invalidates_decisions", [])
        ),
    )


def decision_payload(value: GovernanceDecision) -> dict[str, Any]:
    return {
        "id": value.id,
        "actor": value.actor,
        "operation": value.operation,
        "target": value.target,
        "context": value.context,
        "review_refs": list(value.review_refs),
        "disposition": value.disposition,
        "expected_state_anchor": value.expected_state_anchor,
        "basis_anchors": [list(item) for item in value.basis_anchors],
        "scope_snapshot": sorted(value.scope_snapshot),
        "partition_snapshot": [sorted(cell) for cell in value.partition_snapshot],
        "closure_facts": sorted(value.closure_facts),
        "required_qualification": value.required_qualification,
        "required_activation": value.required_activation,
        "superseded": value.superseded,
    }


def restore_decision(payload: dict[str, Any]) -> GovernanceDecision:
    return GovernanceDecision(
        id=str(payload["id"]),
        actor=str(payload["actor"]),
        operation=str(payload["operation"]),
        target=str(payload["target"]),
        context=str(payload["context"]),
        review_refs=tuple(str(item) for item in payload.get("review_refs", [])),
        disposition=str(payload["disposition"]),
        expected_state_anchor=str(payload["expected_state_anchor"]),
        basis_anchors=tuple(
            (str(item[0]), str(item[1]))
            for item in payload.get("basis_anchors", [])
        ),
        scope_snapshot=frozenset(
            str(item) for item in payload.get("scope_snapshot", [])
        ),
        partition_snapshot=tuple(
            frozenset(str(item) for item in cell)
            for cell in payload.get("partition_snapshot", [])
        ),
        closure_facts=frozenset(str(item) for item in payload.get("closure_facts", [])),
        required_qualification=(
            None
            if payload.get("required_qualification") is None
            else str(payload["required_qualification"])
        ),
        required_activation=(
            None
            if payload.get("required_activation") is None
            else str(payload["required_activation"])
        ),
        superseded=bool(payload.get("superseded", False)),
    )


def application_payload(value: ApplicationReceipt) -> dict[str, Any]:
    application = value.application
    return {
        "application": {
            "id": application.id,
            "actor": application.actor,
            "operation": application.operation,
            "scheme_id": application.scheme_id,
            "target": application.target,
            "decision_ref": application.decision_ref,
            "context": application.context,
            "new_qualification": application.new_qualification,
            "new_activation": application.new_activation,
            "review_obligation_id": application.review_obligation_id,
        },
        "effect_kind": value.effect_kind,
        "pre_anchor": value.pre_anchor,
        "post_anchor": value.post_anchor,
    }


def restore_application(payload: dict[str, Any]) -> ApplicationReceipt:
    raw = payload.get("application")
    if not isinstance(raw, dict):
        raise ValueError("canonical governance application payload is malformed")
    application = GovernedApplication(
        id=str(raw["id"]),
        actor=str(raw["actor"]),
        operation=str(raw["operation"]),
        scheme_id=str(raw["scheme_id"]),
        target=str(raw["target"]),
        decision_ref=str(raw["decision_ref"]),
        context=str(raw["context"]),
        new_qualification=(
            None if raw.get("new_qualification") is None else str(raw["new_qualification"])
        ),
        new_activation=(
            None if raw.get("new_activation") is None else str(raw["new_activation"])
        ),
        review_obligation_id=(
            None
            if raw.get("review_obligation_id") is None
            else str(raw["review_obligation_id"])
        ),
    )
    return ApplicationReceipt(
        application=application,
        effect_kind=str(payload["effect_kind"]),
        pre_anchor=str(payload["pre_anchor"]),
        post_anchor=str(payload["post_anchor"]),
    )


def state_seed_event(scheme_id: str, state: DistinctionState) -> Event:
    return Event(
        id=_event_id("state", scheme_id),
        type=GOVERNANCE_STATE_SEEDED,
        subject_ref=scheme_id,
        payload={"state": state_payload(scheme_id, state)},
    )


def review_opened_event(obligation: ReviewObligation) -> Event:
    return Event(
        id=_event_id("review", obligation.id),
        type=GOVERNANCE_REVIEW_OPENED,
        subject_ref=obligation.target,
        payload={"obligation": obligation_payload(obligation)},
    )


def decision_recorded_event(decision: GovernanceDecision) -> Event:
    return Event(
        id=_event_id("decision", decision.id),
        type=GOVERNANCE_DECISION_RECORDED,
        subject_ref=decision.target,
        payload={"decision": decision_payload(decision)},
    )


def application_committed_event(
    receipt: ApplicationReceipt,
    *,
    next_state: DistinctionState | None = None,
) -> Event:
    payload: dict[str, Any] = {"receipt": application_payload(receipt)}
    if next_state is not None:
        payload["next_state"] = state_payload(receipt.application.scheme_id, next_state)
    return Event(
        id=_event_id("application", receipt.application.id),
        type=GOVERNANCE_APPLICATION_COMMITTED,
        subject_ref=receipt.application.scheme_id,
        payload=payload,
    )


def processed_event(
    event_ref: str,
    obligation_ids: tuple[str, ...],
) -> Event:
    return Event(
        id=_event_id("processed", event_ref),
        type=GOVERNANCE_EVENT_PROCESSED,
        subject_ref=event_ref,
        payload={
            "event_instance_key": event_ref,
            "obligation_ids": list(obligation_ids),
        },
    )


def processed_event_id(event_ref: str) -> str:
    return _event_id("processed", event_ref)


def reconstruct_governance_history(events: list[Event]) -> CanonicalGovernanceHistory:
    states: dict[str, DistinctionState] = {}
    obligations: dict[str, ReviewObligation] = {}
    decisions: dict[str, GovernanceDecision] = {}
    applications: dict[str, ApplicationReceipt] = {}
    discharged: set[str] = set()
    processed: dict[str, tuple[str, ...]] = {}

    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        if event.type == GOVERNANCE_STATE_SEEDED:
            raw = payload.get("state")
            if isinstance(raw, dict):
                scheme_id, state = restore_state(raw)
                current_state = states.get(scheme_id)
                if current_state is None or state.version > current_state.version:
                    states[scheme_id] = state
        elif event.type == GOVERNANCE_REVIEW_OPENED:
            raw = payload.get("obligation")
            if isinstance(raw, dict):
                obligation = restore_obligation(raw)
                existing_obligation = obligations.get(obligation.id)
                if existing_obligation is not None and existing_obligation != obligation:
                    raise ValueError("canonical history rebinds review obligation identity")
                obligations[obligation.id] = obligation
        elif event.type == GOVERNANCE_DECISION_RECORDED:
            raw = payload.get("decision")
            if isinstance(raw, dict):
                decision = restore_decision(raw)
                existing_decision = decisions.get(decision.id)
                if existing_decision is not None and existing_decision != decision:
                    raise ValueError("canonical history rebinds governance decision identity")
                decisions[decision.id] = decision
        elif event.type == GOVERNANCE_APPLICATION_COMMITTED:
            raw = payload.get("receipt")
            if not isinstance(raw, dict):
                continue
            receipt = restore_application(raw)
            existing_application = applications.get(receipt.application.id)
            if existing_application is not None and existing_application != receipt:
                raise ValueError("canonical history rebinds governed application identity")
            applications[receipt.application.id] = receipt
            if receipt.effect_kind == "review_discharge" and receipt.application.review_obligation_id:
                discharged.add(receipt.application.review_obligation_id)
            next_state = payload.get("next_state")
            if isinstance(next_state, dict):
                scheme_id, state = restore_state(next_state)
                current_state = states.get(scheme_id)
                if current_state is None or state.version > current_state.version:
                    states[scheme_id] = state
        elif event.type == GOVERNANCE_EVENT_PROCESSED:
            key = str(payload.get("event_instance_key") or event.subject_ref)
            ids = tuple(str(item) for item in payload.get("obligation_ids", []))
            existing_processed = processed.get(key)
            if existing_processed is not None and existing_processed != ids:
                raise ValueError("canonical history rebinds processed event identity")
            processed[key] = ids

    for obligation_id in discharged:
        obligations.pop(obligation_id, None)

    configuration = GovernanceConfiguration(
        states=states,
        runtime=GovernanceRuntime(
            obligations=obligations,
            decisions=decisions,
            applications=applications,
        ),
    )
    if not global_state_admissible(configuration):
        raise ValueError("canonical governance history reconstructs inadmissible state")
    return CanonicalGovernanceHistory(
        configuration=configuration,
        processed_event_obligations=processed,
    )
