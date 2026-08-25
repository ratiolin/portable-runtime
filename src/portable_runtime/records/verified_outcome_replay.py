"""Pure replay validation for verification-authorized imported Outcomes.

The reader sees a fully materialized candidate graph.  For merge imports that
means the caller must explicitly construct ``current-state + incoming-state``
before invoking this module; the validator never consults a live target store.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from portable_runtime.core.models import Action, Event, Run, Step, StepAttempt, Work
from portable_runtime.records.models import BaseRecord, EvidenceArtifact, OutcomeRecord
from portable_runtime.records.verified_outcome_commit import (
    PreparedVerifiedOutcomeCommit,
    VerifiedOutcomeCommitRequest,
    prepare_verified_outcome_commit,
    same_verified_outcome_semantics,
)

_AUTHORITY_EVENT_TYPES = frozenset({"ObjectiveVerificationAccepted", "OutcomeConfirmed"})


class VerifiedOutcomeAuthorityHistoryError(ValueError):
    """The candidate graph contains unverifiable confirmed-Outcome authority."""


class VerifiedOutcomeCandidateReader:
    """Read-only adapter over one complete, already normalized candidate state."""

    def __init__(self, candidate_state: Mapping[str, Sequence[Mapping[str, object]]]) -> None:
        self._actions = self._parse_bucket(candidate_state, "action", Action)
        self._attempts = self._parse_bucket(candidate_state, "attempt", StepAttempt)
        self._steps = self._parse_bucket(candidate_state, "step", Step)
        self._runs = self._parse_bucket(candidate_state, "run", Run)
        self._works = self._parse_bucket(candidate_state, "work", Work)
        self._records = self._parse_records(candidate_state.get("record", ()))
        self._events = self._parse_bucket(candidate_state, "event", Event)

    @staticmethod
    def _parse_bucket(
        candidate_state: Mapping[str, Sequence[Mapping[str, object]]],
        kind: str,
        model_type: type[Any],
    ) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for raw in candidate_state.get(kind, ()):
            value = model_type.model_validate(raw)
            identifier = getattr(value, "id", None)
            if not isinstance(identifier, str) or not identifier:
                raise VerifiedOutcomeAuthorityHistoryError(
                    f"incompatible confirmed-outcome authority history: candidate {kind} requires string id"
                )
            if identifier in parsed:
                raise VerifiedOutcomeAuthorityHistoryError(
                    f"incompatible confirmed-outcome authority history: duplicate candidate {kind} id {identifier!r}"
                )
            parsed[identifier] = value
        return parsed

    @staticmethod
    def _parse_records(values: Sequence[Mapping[str, object]]) -> dict[str, BaseRecord]:
        parsed: dict[str, BaseRecord] = {}
        for raw in values:
            record_type = raw.get("record_type")
            if record_type == "EvidenceArtifact":
                value: BaseRecord = EvidenceArtifact.model_validate(raw)
            elif record_type == "Outcome":
                value = OutcomeRecord.model_validate(raw)
            else:
                value = BaseRecord.model_validate(raw)
            if value.id in parsed:
                raise VerifiedOutcomeAuthorityHistoryError(
                    f"incompatible confirmed-outcome authority history: duplicate candidate record id {value.id!r}"
                )
            parsed[value.id] = value
        return parsed

    def get_action(self, action_id: str) -> Action | None:
        return self._actions.get(action_id)

    def get_attempt(self, attempt_id: str) -> StepAttempt | None:
        return self._attempts.get(attempt_id)

    def get_step(self, step_id: str) -> Step | None:
        return self._steps.get(step_id)

    def get_run(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def get_work(self, work_id: str) -> Work | None:
        return self._works.get(work_id)

    def get_record(self, record_id: str) -> BaseRecord | None:
        return self._records.get(record_id)

    def get_event(self, event_id: str) -> Event | None:
        return self._events.get(event_id)

    def confirmed_outcomes(self) -> tuple[OutcomeRecord, ...]:
        return tuple(
            value
            for value in self._records.values()
            if isinstance(value, OutcomeRecord) and value.lifecycle_status == "confirmed"
        )

    def authority_events(self) -> tuple[Event, ...]:
        return tuple(value for value in self._events.values() if value.type in _AUTHORITY_EVENT_TYPES)


def _required_metadata_string(metadata: Mapping[str, object], key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise VerifiedOutcomeAuthorityHistoryError(
            f"incompatible confirmed-outcome authority history: confirmed Outcome requires metadata.{key}"
        )
    return value


def reconstruct_verified_outcome_commit_request(
    candidate: VerifiedOutcomeCandidateReader,
    imported_outcome: OutcomeRecord,
) -> VerifiedOutcomeCommitRequest:
    """Reconstruct only the claims needed to re-run the P4 deterministic derivation."""

    metadata = imported_outcome.metadata
    if not isinstance(metadata, dict):
        raise VerifiedOutcomeAuthorityHistoryError(
            "incompatible confirmed-outcome authority history: confirmed Outcome metadata must be an object"
        )
    scope = metadata.get("verification_scope")
    versions = metadata.get("subject_version_refs")
    if not isinstance(scope, dict):
        raise VerifiedOutcomeAuthorityHistoryError(
            "incompatible confirmed-outcome authority history: confirmed Outcome verification_scope required"
        )
    if not isinstance(versions, list) or any(not isinstance(value, str) for value in versions):
        raise VerifiedOutcomeAuthorityHistoryError(
            "incompatible confirmed-outcome authority history: confirmed Outcome subject_version_refs required"
        )

    action = candidate.get_action(imported_outcome.action_ref)
    if action is None:
        raise VerifiedOutcomeAuthorityHistoryError(
            "incompatible confirmed-outcome authority history: confirmed Outcome references missing Action"
        )
    work_id = _required_metadata_string(metadata, "work_id")
    run_id = _required_metadata_string(metadata, "run_id")
    request_id = _required_metadata_string(metadata, "request_id")
    attempt_ref = _required_metadata_string(metadata, "attempt_ref")

    # These are claims reconstructed from the imported Outcome, not proof.
    # prepare_verified_outcome_commit() re-resolves and cross-validates them
    # against Action/Attempt/Step/Run/Work and the persisted EvidenceArtifact set.
    return VerifiedOutcomeCommitRequest(
        action_ref=action.id,
        evidence_refs=tuple(imported_outcome.evidence_refs),
        expected_work_id=work_id,
        expected_run_id=run_id,
        expected_request_id=request_id,
        expected_attempt_ref=attempt_ref,
        verification_scope={str(key): value for key, value in scope.items()},
        subject_version_refs=tuple(versions),
    )


def validate_verified_outcome_authority_graph(
    candidate_state: Mapping[str, Sequence[Mapping[str, object]]],
) -> tuple[PreparedVerifiedOutcomeCommit, ...]:
    """Re-derive every confirmed Outcome and enforce bidirectional event closure."""

    reader = VerifiedOutcomeCandidateReader(candidate_state)
    expected_event_ids: set[str] = set()
    prepared_commits: list[PreparedVerifiedOutcomeCommit] = []

    for imported_outcome in reader.confirmed_outcomes():
        try:
            request = reconstruct_verified_outcome_commit_request(reader, imported_outcome)
            prepared = prepare_verified_outcome_commit(reader, request)
        except VerifiedOutcomeAuthorityHistoryError:
            raise
        except Exception as exc:
            raise VerifiedOutcomeAuthorityHistoryError(
                f"incompatible confirmed-outcome authority history: {exc}"
            ) from exc

        if imported_outcome.id != prepared.outcome.id or not same_verified_outcome_semantics(
            imported_outcome, prepared.outcome
        ):
            raise VerifiedOutcomeAuthorityHistoryError(
                "incompatible confirmed-outcome authority history: imported confirmed Outcome does not match "
                "deterministic verification replay"
            )

        for expected_event in prepared.events:
            imported_event = reader.get_event(expected_event.id)
            if imported_event is None:
                raise VerifiedOutcomeAuthorityHistoryError(
                    "incompatible confirmed-outcome authority history: required authority event missing"
                )
            if not same_verified_outcome_semantics(imported_event, expected_event):
                raise VerifiedOutcomeAuthorityHistoryError(
                    "incompatible confirmed-outcome authority history: imported authority event does not match "
                    "deterministic verification replay"
                )
            expected_event_ids.add(expected_event.id)
        prepared_commits.append(prepared)

    for imported_event in reader.authority_events():
        if imported_event.id not in expected_event_ids:
            raise VerifiedOutcomeAuthorityHistoryError(
                "incompatible confirmed-outcome authority history: orphan or non-deterministic authority event"
            )

    return tuple(prepared_commits)
