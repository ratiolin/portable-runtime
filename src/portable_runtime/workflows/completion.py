"""Fail-closed authority for terminal workflow completion.

Workflow execution is not itself a verification judgment.  This module is the
single portable primitive used by workflows that claim a successful terminal
state: every supplied proof reference must resolve to a typed semantic record
whose closed verification result is explicitly ``pass``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from portable_runtime.core.models import Run, Work
from portable_runtime.interfaces.store import StateStore
from portable_runtime.workflows.context import validate_run_transition


class CompletionAuthority:
    """Authorize a terminal ``succeeded`` transition from durable proof refs."""

    def __init__(self, store: StateStore) -> None:
        self.store = store

    @staticmethod
    def _expected_scope(work: Work) -> dict[str, Any]:
        metadata = work.metadata if isinstance(work.metadata, dict) else {}
        constraints = work.constraints if isinstance(work.constraints, dict) else {}
        value = metadata.get("verification_scope", constraints.get("verification_scope", {}))
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _expected_version(work: Work) -> object:
        metadata = work.metadata if isinstance(work.metadata, dict) else {}
        return metadata.get("work_version", metadata.get("task_version", metadata.get("version", 1)))

    @staticmethod
    def _proof_metadata(record: object) -> dict[str, Any] | None:
        metadata = getattr(record, "metadata", None)
        return metadata if isinstance(metadata, dict) else None

    def _passing_proof(self, ref: str, *, work: Work, run: Run) -> bool:
        record = self.store.get_record(ref)
        if record is None:
            return False
        metadata = self._proof_metadata(record)
        if metadata is None:
            return False
        closed = metadata.get("verification_result")
        if not isinstance(closed, dict):
            return False
        if str(closed.get("result", "")).lower() != "pass":
            return False
        # A proof must be explicitly typed; arbitrary metadata flags are not
        # accepted as terminal evidence.
        if getattr(record, "record_type", None) != "EvidenceArtifact":
            return False
        if getattr(record, "kind", None) not in {
            "closed-verification",
            "verification-result",
            "task-objective-proof",
        }:
            return False
        # A terminal proof is a scoped semantic claim, not a free-standing
        # provider result.  Every binding is required even when its expected
        # value is empty/default so a proof cannot be copied between runs.
        if metadata.get("work_id") != work.id or metadata.get("run_id") != run.id:
            return False
        proof_scope = metadata.get("verification_scope", metadata.get("scope"))
        if not isinstance(proof_scope, dict) or proof_scope != self._expected_scope(work):
            return False
        proof_version = metadata.get("work_version", metadata.get("task_version", metadata.get("version")))
        if proof_version != self._expected_version(work):
            return False
        criteria = metadata.get("acceptance_criteria", metadata.get("criteria"))
        expected_criteria = list(work.acceptance_criteria)
        return isinstance(criteria, list) and criteria == expected_criteria

    def _already_consumed(self, refs: set[str], run: Run) -> bool:
        metadata = run.metadata if isinstance(run.metadata, dict) else {}
        own_refs = metadata.get("_completion_proof_refs", [])
        if isinstance(own_refs, list) and refs.intersection(str(item) for item in own_refs):
            return True
        lister = getattr(self.store, "list_runs", None)
        if not callable(lister):
            return False
        try:
            runs = lister()
        except Exception:
            return True
        for other in runs:
            if getattr(other, "id", None) == run.id:
                continue
            other_meta = getattr(other, "metadata", {})
            used = other_meta.get("_completion_proof_refs", []) if isinstance(other_meta, dict) else []
            if isinstance(used, list) and refs.intersection(str(item) for item in used):
                return True
        return False

    def authorize(self, *, work: Work, run: Run, verification_refs: Iterable[str]) -> Run:
        refs = [str(ref) for ref in verification_refs if str(ref).strip()]
        if not refs:
            raise ValueError("terminal completion requires verification proof refs")
        if len(set(refs)) != len(refs):
            raise ValueError("terminal completion proof refs must be unique")
        if work.id != run.work_id:
            raise ValueError("terminal completion work/run binding mismatch")
        if run.status == "succeeded":
            raise ValueError("terminal completion cannot reuse a succeeded run")
        if self._already_consumed(set(refs), run):
            raise ValueError("terminal completion proof refs have already been consumed")
        if any(not self._passing_proof(ref, work=work, run=run) for ref in refs):
            raise ValueError("terminal completion requires explicit passing verification proofs")
        validate_run_transition(run.status, "succeeded")
        metadata = dict(run.metadata) if isinstance(run.metadata, dict) else {}
        metadata["_completion_proof_refs"] = refs
        metadata["completion_verification_scope"] = self._expected_scope(work)
        metadata["completion_work_version"] = self._expected_version(work)
        metadata["completion_acceptance_criteria"] = list(work.acceptance_criteria)
        from portable_runtime.core.models import utcnow

        updated = run.model_copy(update={"status": "succeeded", "ended_at": utcnow(), "metadata": metadata})
        self.store.save_run(updated)
        return updated


def complete_with_proofs(store: StateStore, work: Work, run: Run, refs: Iterable[str]) -> Run:
    """Convenience wrapper used by workflow implementations."""

    return CompletionAuthority(store).authorize(work=work, run=run, verification_refs=refs)
