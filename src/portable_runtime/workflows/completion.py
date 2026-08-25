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
from portable_runtime.records.verification_binding import BoundVerificationEvidenceValidator
from portable_runtime.workflows.context import validate_run_transition


class CompletionAuthority:
    """Authorize a terminal ``succeeded`` transition from durable proof refs."""

    _DEFAULT_WORKFLOW_OBLIGATIONS: dict[str, tuple[str, ...]] = {
        # IncidentRepairWorkflow runs two independent closed verifiers under
        # its conservative default policy.  Keep those obligations explicit
        # at the shared authority boundary so a partial proof persist cannot
        # be mistaken for a complete verification set.
        "incident": ("verify.http", "verify.git_diff"),
        "alert": ("verify.http", "verify.git_diff"),
        "repair": ("verify.http", "verify.git_diff"),
        "incident-repair": ("verify.http", "verify.git_diff"),
        # DailyScan produces one container observation and one PromQL
        # verification.  Both are required for the scan's terminal claim.
        "maintenance-scan": ("observe.container", "verify.promql"),
        "daily-scan": ("observe.container", "verify.promql"),
        "schedule-scan": ("observe.container", "verify.promql"),
        "scan": ("observe.container", "verify.promql"),
        "daily_scan": ("observe.container", "verify.promql"),
    }

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
    def required_obligation_refs(work: Work) -> list[str]:
        """Return the explicit verification obligations for ``work``.

        Acceptance criteria and policy/verification obligations are separate
        declarations, but they share one proof-coverage contract.  A proof
        may only close a Work after its ``obligation_refs`` cover every
        declared item.  We keep the representation deliberately portable:
        string obligations are used as-is and mapping obligations use their
        stable ``id``/``ref``/``key``/``name`` value.
        """

        values: list[str] = [
            criterion.strip()
            for criterion in work.acceptance_criteria
            if isinstance(criterion, str) and criterion.strip()
        ]

        def add(raw: object) -> None:
            if isinstance(raw, str) and raw.strip():
                values.append(raw.strip())
                return
            if not isinstance(raw, list):
                return
            for item in raw:
                if isinstance(item, str) and item.strip():
                    values.append(item.strip())
                elif isinstance(item, dict):
                    for key in ("id", "ref", "key", "name", "description"):
                        candidate = item.get(key)
                        if isinstance(candidate, str) and candidate.strip():
                            values.append(candidate.strip())
                            break

        metadata = work.metadata if isinstance(work.metadata, dict) else {}
        constraints = work.constraints if isinstance(work.constraints, dict) else {}
        for source in (metadata, constraints):
            for field in (
                "verification_obligations",
                "required_obligations",
                "policy_obligations",
                "obligations",
                "revalidation_obligations",
                "required_revalidation_obligations",
            ):
                add(source.get(field))
            policy = source.get("verification_policy")
            if isinstance(policy, dict):
                for field in (
                    "verification_obligations",
                    "required_obligations",
                    "obligations",
                    "revalidation_obligations",
                    "required_revalidation_obligations",
                ):
                    add(policy.get(field))

        # Workflow-owned defaults are only applied when the Work did not
        # declare an explicit obligation set.  This preserves custom policy
        # declarations while making built-in multi-proof workflows fail
        # closed if one proof artifact is lost during persistence.
        if not values:
            policy = metadata.get("verification_policy")
            mode = policy.get("mode", "all-required") if isinstance(policy, dict) else str(policy or "all-required")
            mode = str(mode).strip().lower()
            if mode in {"all-required", "all_required", "all"}:
                values.extend(CompletionAuthority._DEFAULT_WORKFLOW_OBLIGATIONS.get(work.kind, ()))
            elif work.kind in CompletionAuthority._DEFAULT_WORKFLOW_OBLIGATIONS:
                # A weaker policy is a declaration of a different coverage
                # contract.  Without explicit obligation refs, do not infer
                # which proof subset is sufficient: leave an impossible
                # sentinel that forces the workflow to remain non-terminal.
                values.append(f"{work.kind}:explicit-verification-obligations-required")

        # Preserve declaration order while eliminating duplicate obligations.
        return list(dict.fromkeys(values))

    @staticmethod
    def revalidation_obligation_refs(work: Work) -> list[str]:
        values: list[str] = []

        def add(raw: object) -> None:
            if isinstance(raw, str) and raw.strip():
                values.append(raw.strip())
                return
            if not isinstance(raw, list):
                return
            for item in raw:
                if isinstance(item, str) and item.strip():
                    values.append(item.strip())
                elif isinstance(item, dict):
                    for key in ("id", "ref", "key", "name", "description"):
                        candidate = item.get(key)
                        if isinstance(candidate, str) and candidate.strip():
                            values.append(candidate.strip())
                            break

        metadata = work.metadata if isinstance(work.metadata, dict) else {}
        constraints = work.constraints if isinstance(work.constraints, dict) else {}
        for source in (metadata, constraints):
            add(source.get("revalidation_obligations"))
            add(source.get("required_revalidation_obligations"))
            policy = source.get("verification_policy")
            if isinstance(policy, dict):
                add(policy.get("revalidation_obligations"))
                add(policy.get("required_revalidation_obligations"))
        return list(dict.fromkeys(values))

    @staticmethod
    def _proof_metadata(record: object) -> dict[str, Any] | None:
        return BoundVerificationEvidenceValidator.proof_metadata(record)

    @staticmethod
    def _proof_class(record: object, metadata: dict[str, Any]) -> str:
        return BoundVerificationEvidenceValidator.proof_class(record, metadata)

    @staticmethod
    def _proof_can_cover(proof_class: str, obligation: str) -> bool:
        return BoundVerificationEvidenceValidator.proof_can_cover(proof_class, obligation)

    @staticmethod
    def validate_proof_invariant(
        work: Work,
        run: Run,
        refs: Iterable[str],
        record_lookup: Callable[[str], object | None],
    ) -> tuple[list[str], list[str], list[str]]:
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
        required_obligations = set(CompletionAuthority.required_obligation_refs(work))
        revalidation_obligations = set(CompletionAuthority.revalidation_obligation_refs(work))
        validated = BoundVerificationEvidenceValidator.validate(
            work=work,
            run=run,
            refs=normalized,
            record_lookup=record_lookup,
            expected_scope=expected_scope,
            allowed_results=frozenset({"pass"}),
            expected_work_version=expected_version,
            expected_acceptance_criteria=expected_criteria,
        )
        covered_obligations: set[str] = set()
        for record, proof_class in zip(validated.records, validated.proof_classes, strict=True):
            metadata = BoundVerificationEvidenceValidator.proof_metadata(record) or {}
            raw_coverage = metadata.get(
                "obligation_refs",
                metadata.get("covered_obligations", metadata.get("verification_obligations", [])),
            )
            candidates: list[str] = []
            if isinstance(raw_coverage, str) and raw_coverage.strip():
                candidates.append(raw_coverage.strip())
            elif isinstance(raw_coverage, list):
                candidates.extend(
                    item.strip() for item in raw_coverage if isinstance(item, str) and item.strip()
                )
            covered_obligations.update(
                obligation
                for obligation in candidates
                if (obligation not in revalidation_obligations or proof_class == "revalidation")
                and BoundVerificationEvidenceValidator.proof_can_cover(proof_class, obligation)
            )
        required = sorted(required_obligations)
        covered = sorted(covered_obligations)
        missing = sorted(required_obligations - covered_obligations)
        if missing:
            raise ValueError(
                "terminal completion proofs do not cover required verification obligations: "
                + ", ".join(missing)
            )
        terminal_pairs = ((work, "completed"), (run, "succeeded"))
        for value, terminal_status in terminal_pairs:
            if getattr(value, "status", None) != terminal_status:
                continue
            metadata_value = value.metadata if isinstance(value.metadata, dict) else {}
            expected_audit = {
                "completion_required_obligations": required,
                "completion_covered_obligations": covered,
                "completion_missing_obligations": [],
            }
            for key, expected in expected_audit.items():
                if metadata_value.get(key) != expected:
                    raise ValueError(f"terminal completion metadata {key!r} does not match proof coverage")
        return required, covered, missing

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
        required_obligations, covered_obligations, missing_obligations = self.validate_proof_invariant(
            work,
            run,
            refs,
            self.store.get_record,
        )
        validate_run_transition(run.status, "succeeded")
        metadata = dict(run.metadata) if isinstance(run.metadata, dict) else {}
        metadata["_completion_proof_refs"] = refs
        metadata["completion_verification_scope"] = self._expected_scope(work)
        metadata["completion_work_version"] = self._expected_version(work)
        metadata["completion_acceptance_criteria"] = list(work.acceptance_criteria)
        metadata["completion_required_obligations"] = required_obligations
        metadata["completion_covered_obligations"] = covered_obligations
        metadata["completion_missing_obligations"] = missing_obligations
        from portable_runtime.core.models import utcnow

        updated = run.model_copy(update={"status": "succeeded", "ended_at": utcnow(), "metadata": metadata})
        work_metadata = dict(work.metadata) if isinstance(work.metadata, dict) else {}
        work_metadata["_completion_proof_refs"] = list(refs)
        work_metadata["completion_verification_scope"] = self._expected_scope(work)
        work_metadata["completion_work_version"] = self._expected_version(work)
        work_metadata["completion_acceptance_criteria"] = list(work.acceptance_criteria)
        work_metadata["completion_required_obligations"] = list(required_obligations)
        work_metadata["completion_covered_obligations"] = list(covered_obligations)
        work_metadata["completion_missing_obligations"] = list(missing_obligations)
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
