"""Store-owned durable F1-B3 Outcome impact judgment/disposition commit contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from portable_runtime.core.models import Event
from portable_runtime.governance.outcome_impact import (
    OutcomeConfirmedTriggerStore,
    OutcomeGovernanceApplicability,
    OutcomeGovernanceDependency,
    resolve_outcome_applicability,
    resolve_outcome_confirmed_trigger,
)
from portable_runtime.governance.outcome_impact_judgment import (
    OutcomeImpact,
    OutcomeImpactJudgment,
    OutcomeImpactPolicy,
    evaluate_outcome_impact,
)
from portable_runtime.records.revalidation import ImpactType, RevalidationDisposition

OUTCOME_IMPACT_JUDGMENT_EVENT = "OutcomeImpactJudgmentRecorded"
OUTCOME_DISPOSITION_EVENT = "OutcomeRevalidationDispositionRecorded"
OUTCOME_IMPACT_SCHEMA = "outcome-governance-impact-v1"
OUTCOME_IMPACT_AUTHORITY_EVENT_TYPES = frozenset(
    {OUTCOME_IMPACT_JUDGMENT_EVENT, OUTCOME_DISPOSITION_EVENT}
)
_VALID_IMPACTS = frozenset(
    {
        "no-governance-impact",
        "recovery-only",
        "revalidation-required",
        "qualification-challenged",
        "unknown",
    }
)
_VALID_ACTIONS = frozenset(
    {"none", "warn", "background-revalidate", "block-next-use", "require-human-review", "reopen"}
)


class OutcomeDispositionPolicy(Protocol):
    @property
    def policy_ref(self) -> str: ...

    def decide(self, judgment: OutcomeImpactJudgment) -> RevalidationDisposition | None: ...


class OutcomeImpactCommitStore(OutcomeConfirmedTriggerStore, Protocol):
    def append_event(self, value: Event) -> None: ...


@dataclass(frozen=True)
class OutcomeImpactCommitRequest:
    event_ref: str
    dependency: OutcomeGovernanceDependency
    context: str
    requested_scope: frozenset[str]
    subject_version_refs: tuple[str, ...]


@dataclass(frozen=True)
class CommittedOutcomeImpact:
    key_digest: str
    judgment: OutcomeImpactJudgment
    disposition: RevalidationDisposition
    judgment_event_ref: str
    disposition_event_ref: str
    replayed: bool


@dataclass(frozen=True)
class PreparedOutcomeImpactCommit:
    key_digest: str
    judgment: OutcomeImpactJudgment
    disposition: RevalidationDisposition
    events: tuple[Event, Event]
    replayed: bool


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _policy_digest(policy: object) -> str | None:
    value = getattr(policy, "policy_digest", None)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _binding_payload(
    *,
    event_ref: str,
    applicability: OutcomeGovernanceApplicability,
) -> dict[str, object]:
    if applicability.scheme_id is None:
        raise ValueError("outcome impact commit requires applicable scheme")
    return {
        "schema_version": OUTCOME_IMPACT_SCHEMA,
        "trigger_event_ref": event_ref,
        "outcome_ref": applicability.outcome_ref,
        "action_ref": applicability.action_ref,
        "scheme_id": applicability.scheme_id,
        "context": applicability.context,
        "governed_scope": sorted(applicability.governed_scope),
        "subject_version_refs": sorted(applicability.subject_version_refs),
        "applicability_basis_refs": sorted(applicability.basis_refs),
    }


def _event_ids(key_digest: str) -> tuple[str, str]:
    suffix = key_digest[:32]
    return f"event_outcome_impact_{suffix}", f"event_outcome_disposition_{suffix}"


def _nonempty_strings(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        return None
    values = tuple(item.strip() for item in value)
    return values if values and len(set(values)) == len(values) else None


def _replay_existing(
    *,
    store: OutcomeImpactCommitStore,
    key_digest: str,
    binding: dict[str, object],
) -> PreparedOutcomeImpactCommit | None:
    judgment_id, disposition_id = _event_ids(key_digest)
    judgment_event = store.get_event(judgment_id)
    disposition_event = store.get_event(disposition_id)
    if judgment_event is None and disposition_event is None:
        return None
    if judgment_event is None or disposition_event is None:
        raise ValueError("outcome impact durable authority graph incomplete")
    if judgment_event.type != OUTCOME_IMPACT_JUDGMENT_EVENT or disposition_event.type != OUTCOME_DISPOSITION_EVENT:
        raise ValueError("outcome impact durable authority event type mismatch")

    jp = judgment_event.payload
    dp = disposition_event.payload
    expected_common = {
        **binding,
        "semantic_level": "governance-impact",
        "binding_digest": key_digest,
    }
    for key, expected in expected_common.items():
        if jp.get(key) != expected or dp.get(key) != expected:
            raise ValueError("outcome impact durable authority binding mismatch")

    impact = jp.get("impact")
    impact_policy_ref = jp.get("impact_policy_ref")
    rationale_refs = _nonempty_strings(jp.get("rationale_refs"))
    if impact not in _VALID_IMPACTS or impact == "unknown":
        raise ValueError("outcome impact durable judgment has invalid impact")
    if not isinstance(impact_policy_ref, str) or not impact_policy_ref.strip() or rationale_refs is None:
        raise ValueError("outcome impact durable judgment provenance incomplete")
    if dp.get("judgment_event_ref") != judgment_event.id:
        raise ValueError("outcome impact durable disposition judgment binding mismatch")
    action = dp.get("action")
    disposition_policy_ref = dp.get("disposition_policy_ref")
    disposition_rationale = _nonempty_strings(dp.get("rationale_refs"))
    if action not in _VALID_ACTIONS:
        raise ValueError("outcome impact durable disposition action invalid")
    if not isinstance(disposition_policy_ref, str) or not disposition_policy_ref.strip() or disposition_rationale is None:
        raise ValueError("outcome impact durable disposition provenance incomplete")

    scheme_id = binding["scheme_id"]
    context = binding["context"]
    if not isinstance(scheme_id, str) or not isinstance(context, str):
        raise ValueError("outcome impact durable binding is malformed")
    judgment = OutcomeImpactJudgment(
        outcome_ref=str(binding["outcome_ref"]),
        trigger_event_ref=str(binding["trigger_event_ref"]),
        action_ref=str(binding["action_ref"]),
        scheme_id=scheme_id,
        context=context,
        impact=impact,  # type: ignore[arg-type]
        policy_ref=impact_policy_ref,
        rationale_refs=rationale_refs,
        applicability_basis_refs=tuple(binding["applicability_basis_refs"]),  # type: ignore[arg-type]
    )
    disposition = RevalidationDisposition(
        action=action,  # type: ignore[arg-type]
        policy_ref=disposition_policy_ref,
        rationale_refs=list(disposition_rationale),
    )
    return PreparedOutcomeImpactCommit(
        key_digest=key_digest,
        judgment=judgment,
        disposition=disposition,
        events=(judgment_event, disposition_event),
        replayed=True,
    )


def prepare_outcome_impact_commit(
    store: OutcomeImpactCommitStore,
    request: OutcomeImpactCommitRequest,
    impact_policy: OutcomeImpactPolicy,
    disposition_policy: OutcomeDispositionPolicy,
) -> PreparedOutcomeImpactCommit:
    """Re-read trigger/applicability and prepare or replay one durable judgment.

    Existing durable judgment/disposition facts are resolved before either
    current policy is called, preventing policy drift across P3 retries.
    """

    trigger = resolve_outcome_confirmed_trigger(store, request.event_ref)
    if not trigger.authoritative or trigger.outcome is None:
        raise ValueError("outcome impact commit requires authoritative OutcomeConfirmed trigger")
    applicability = resolve_outcome_applicability(
        outcome=trigger.outcome,
        dependency=request.dependency,
        context=request.context,
        requested_scope=request.requested_scope,
        subject_version_refs=request.subject_version_refs,
    )
    if not applicability.applicable:
        raise ValueError(f"outcome impact commit requires applicable dependency: {applicability.status}")

    binding = _binding_payload(event_ref=request.event_ref, applicability=applicability)
    key_digest = _digest(binding)
    replay = _replay_existing(store=store, key_digest=key_digest, binding=binding)
    if replay is not None:
        return replay

    evaluated = evaluate_outcome_impact(
        trigger=trigger,
        applicability=applicability,
        policy=impact_policy,
    )
    if evaluated.status != "ready" or evaluated.judgment is None:
        raise ValueError(f"outcome impact judgment unavailable: {evaluated.reason}")
    judgment = evaluated.judgment
    if judgment.impact == "unknown":
        raise ValueError("unknown Outcome impact cannot be durably committed")

    disposition = disposition_policy.decide(judgment)
    if disposition is None:
        raise ValueError("outcome impact disposition unavailable")
    if disposition.policy_ref != disposition_policy.policy_ref or not disposition.policy_ref.strip():
        raise ValueError("outcome impact disposition policy identity mismatch")
    if disposition.action not in _VALID_ACTIONS:
        raise ValueError("outcome impact disposition action invalid")
    if not disposition.rationale_refs:
        raise ValueError("outcome impact disposition requires rationale refs")

    judgment_id, disposition_id = _event_ids(key_digest)
    common: dict[str, Any] = {
        **binding,
        "semantic_level": "governance-impact",
        "binding_digest": key_digest,
    }
    judgment_payload = {
        **common,
        "impact": judgment.impact,
        "impact_policy_ref": judgment.policy_ref,
        "impact_policy_digest": _policy_digest(impact_policy),
        "rationale_refs": list(judgment.rationale_refs),
    }
    disposition_payload = {
        **common,
        "judgment_event_ref": judgment_id,
        "action": disposition.action,
        "disposition_policy_ref": disposition.policy_ref,
        "disposition_policy_digest": _policy_digest(disposition_policy),
        "rationale_refs": list(disposition.rationale_refs),
    }
    judgment_event = Event(
        id=judgment_id,
        type=OUTCOME_IMPACT_JUDGMENT_EVENT,
        subject_ref=judgment.outcome_ref,
        payload=judgment_payload,
    )
    disposition_event = Event(
        id=disposition_id,
        type=OUTCOME_DISPOSITION_EVENT,
        subject_ref=judgment.outcome_ref,
        payload=disposition_payload,
    )
    return PreparedOutcomeImpactCommit(
        key_digest=key_digest,
        judgment=judgment,
        disposition=disposition,
        events=(judgment_event, disposition_event),
        replayed=False,
    )


def committed_outcome_impact(prepared: PreparedOutcomeImpactCommit) -> CommittedOutcomeImpact:
    return CommittedOutcomeImpact(
        key_digest=prepared.key_digest,
        judgment=prepared.judgment,
        disposition=prepared.disposition,
        judgment_event_ref=prepared.events[0].id,
        disposition_event_ref=prepared.events[1].id,
        replayed=prepared.replayed,
    )


__all__ = [
    "CommittedOutcomeImpact",
    "OUTCOME_DISPOSITION_EVENT",
    "OUTCOME_IMPACT_AUTHORITY_EVENT_TYPES",
    "OUTCOME_IMPACT_JUDGMENT_EVENT",
    "OUTCOME_IMPACT_SCHEMA",
    "OutcomeDispositionPolicy",
    "OutcomeImpactCommitRequest",
    "OutcomeImpactCommitStore",
    "PreparedOutcomeImpactCommit",
    "committed_outcome_impact",
    "prepare_outcome_impact_commit",
]
