"""Fail-closed authority for terminal workflow completion.

Workflow execution is not itself a verification judgment.  This module is the
single portable primitive used by workflows that claim a successful terminal
state: every supplied proof reference must resolve to a typed semantic record
whose closed verification result is explicitly ``pass``.
"""

from __future__ import annotations

from collections.abc import Iterable

from portable_runtime.core.models import Run, Work
from portable_runtime.interfaces.store import StateStore
from portable_runtime.workflows.context import validate_run_transition


class CompletionAuthority:
    """Authorize a terminal ``succeeded`` transition from durable proof refs."""

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def _passing_proof(self, ref: str) -> bool:
        record = self.store.get_record(ref)
        if record is None:
            return False
        metadata = getattr(record, "metadata", {})
        if not isinstance(metadata, dict):
            return False
        closed = metadata.get("verification_result")
        if not isinstance(closed, dict):
            return False
        if str(closed.get("result", "")).lower() != "pass":
            return False
        # A proof must be explicitly typed; arbitrary metadata flags are not
        # accepted as terminal evidence.
        return getattr(record, "kind", None) in {
            "closed-verification",
            "verification-result",
        } or getattr(record, "record_type", None) in {
            "EvidenceArtifact",
            "VerificationResult",
        }

    def authorize(self, *, work: Work, run: Run, verification_refs: Iterable[str]) -> Run:
        refs = [str(ref) for ref in verification_refs if str(ref).strip()]
        if not refs:
            raise ValueError("terminal completion requires verification proof refs")
        if any(not self._passing_proof(ref) for ref in refs):
            raise ValueError("terminal completion requires explicit passing verification proofs")
        validate_run_transition(run.status, "succeeded")
        updated = run.model_copy(update={"status": "succeeded"})
        self.store.save_run(updated)
        return updated


def complete_with_proofs(store: StateStore, work: Work, run: Run, refs: Iterable[str]) -> Run:
    """Convenience wrapper used by workflow implementations."""

    return CompletionAuthority(store).authorize(work=work, run=run, verification_refs=refs)
