"""Fail-closed authority for terminal workflow completion.

Workflow execution is not itself a verification judgment.  This module is the
single portable primitive used by workflows that claim a successful terminal
state: every supplied proof reference must resolve to a typed semantic record
whose closed verification result is explicitly ``pass``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
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

    @staticmethod
    def validate_proof_invariant(
        work: Work,
        run: Run,
        refs: Iterable[str],
        record_lookup: Callable[[str], object | None],
    ) -> None:
        """Validate the complete terminal-proof contract for a Work/Run pair.

        This is deliberately usable by stores while they hold their commit
        lock.  A terminal status is only valid when every proof is a typed,
        passing EvidenceArtifact bound to the exact Work, Run, scope, version,
        and acceptance criteria.  No provider status or metadata flag is
        accepted as a substitute.
        """
        normalized = [str(ref) for ref in refs if str(ref).strip()]
        if not normalized:
            raise ValueError("terminal completion requires verification proof refs")
        if len(set(normalized)) != len(normalized):
            raise ValueError("terminal completion proof refs must be unique")
        if work.id != run.work_id:
            raise ValueError("terminal completion work/run binding mismatch")
        expected_scope = CompletionAuthority._expected_scope(work)
        expected_version = CompletionAuthority._expected_version(work)
        expected_criteria = list(work.acceptance_criteria)
        for ref in normalized:
            record = record_lookup(ref)
            metadata = CompletionAuthority._proof_metadata(record)
            if metadata is None:
                raise ValueError("terminal completion requires explicit passing verification proofs")
            closed = metadata.get("verification_result")
            if not isinstance(closed, dict) or str(closed.get("result", "")).lower() != "pass":
                raise ValueError("terminal completion requires explicit passing verification proofs")
            if getattr(record, "record_type", None) != "EvidenceArtifact" or getattr(record, "kind", None) not in {
                "closed-verification",
                "verification-result",
                "task-objective-proof",
            }:
                raise ValueError("terminal completion requires typed verification EvidenceArtifact proofs")
            if metadata.get("work_id") != work.id or metadata.get("run_id") != run.id:
                raise ValueError("terminal completion proof is not bound to this Work/Run")
            proof_scope = metadata.get("verification_scope", metadata.get("scope"))
            if not isinstance(proof_scope, dict) or proof_scope != expected_scope:
                raise ValueError("terminal completion proof scope does not match Work scope")
            proof_version = metadata.get("work_version", metadata.get("task_version", metadata.get("version")))
            if proof_version != expected_version:
                raise ValueError("terminal completion proof version does not match Work version")
            criteria = metadata.get("acceptance_criteria", metadata.get("criteria"))
            if not isinstance(criteria, list) or criteria != expected_criteria:
                raise ValueError("terminal completion proof acceptance criteria do not match Work")

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
        current_work = self.store.get_work(work.id) or work
        current_run = self.store.get_run(run.id) or run
        if current_work.id != work.id or current_run.work_id != work.id:
            raise ValueError("terminal completion work/run binding mismatch")
        if current_run.status == "succeeded":
            existing = current_run.metadata if isinstance(current_run.metadata, dict) else {}
            existing_refs = existing.get("_completion_proof_refs", [])
            if current_work.status == "completed" and list(existing_refs) == refs:
                return current_run
            raise ValueError("terminal completion cannot reuse a succeeded run")
        if current_work.status == "completed":
            raise ValueError("completed work has no reusable terminal run")
        run = current_run
        work = current_work
        if self._already_consumed(set(refs), run):
            raise ValueError("terminal completion proof refs have already been consumed")
        validate_run_transition(run.status, "succeeded")
        metadata = dict(run.metadata) if isinstance(run.metadata, dict) else {}
        metadata["_completion_proof_refs"] = refs
        metadata["completion_verification_scope"] = self._expected_scope(work)
        metadata["completion_work_version"] = self._expected_version(work)
        metadata["completion_acceptance_criteria"] = list(work.acceptance_criteria)
        from portable_runtime.core.models import utcnow

        updated = run.model_copy(update={"status": "succeeded", "ended_at": utcnow(), "metadata": metadata})
        work_metadata = dict(work.metadata) if isinstance(work.metadata, dict) else {}
        work_metadata["_completion_proof_refs"] = list(refs)
        work_metadata["completion_verification_scope"] = self._expected_scope(work)
        work_metadata["completion_work_version"] = self._expected_version(work)
        work_metadata["completion_acceptance_criteria"] = list(work.acceptance_criteria)
        updated_work = work.model_copy(
            update={"status": "completed", "updated_at": utcnow(), "metadata": work_metadata}
        )
        # The store is the authority boundary for the paired terminal write.
        # It validates the proof invariant while holding its transaction lock
        # and commits both objects as one indivisible operation.
        commit_terminal = getattr(self.store, "commit_terminal", None)
        if not callable(commit_terminal):
            raise ValueError("terminal completion requires the store commit_terminal primitive")
        return commit_terminal(updated_work, updated, refs)


def complete_with_proofs(store: StateStore, work: Work, run: Run, refs: Iterable[str]) -> Run:
    """Convenience wrapper used by workflow implementations."""

    return CompletionAuthority(store).authorize(work=work, run=run, verification_refs=refs)
