"""Public semantic façade for verification-authorized confirmed Outcomes."""

from __future__ import annotations

from typing import Any, Protocol

from portable_runtime.records.models import OutcomeRecord
from portable_runtime.records.verified_outcome_commit import VerifiedOutcomeCommitRequest


class VerifiedOutcomeCommitStore(Protocol):
    """The only store capability exposed to the public authority façade."""

    def commit_verified_outcome(self, request: VerifiedOutcomeCommitRequest) -> OutcomeRecord: ...


class VerifiedOutcomeAuthority:
    """Thin public façade over the store-owned verified Outcome authority primitive."""

    def __init__(self, store: VerifiedOutcomeCommitStore) -> None:
        self._store = store

    def confirm(
        self,
        *,
        action_ref: str,
        evidence_refs: list[str],
        expected_work_id: str,
        expected_run_id: str,
        expected_request_id: str,
        expected_attempt_ref: str,
        verification_scope: dict[str, Any],
        subject_version_refs: list[str],
    ) -> OutcomeRecord:
        request = VerifiedOutcomeCommitRequest(
            action_ref=action_ref,
            evidence_refs=tuple(evidence_refs),
            expected_work_id=expected_work_id,
            expected_run_id=expected_run_id,
            expected_request_id=expected_request_id,
            expected_attempt_ref=expected_attempt_ref,
            verification_scope=dict(verification_scope),
            subject_version_refs=tuple(subject_version_refs),
        )
        return self._store.commit_verified_outcome(request)
