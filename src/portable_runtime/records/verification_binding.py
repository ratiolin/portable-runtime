"""Pure validation for typed verification evidence bound to durable execution facts."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal, cast

from portable_runtime.core.models import Action, Run, Step, StepAttempt, Work
from portable_runtime.records.models import BaseRecord, EvidenceArtifact

ObjectiveResult = Literal["pass", "fail"]


@dataclass(frozen=True)
class BoundVerificationEvidence:
    """Validated verification closure; it carries no persistence authority."""

    records: tuple[EvidenceArtifact, ...]
    objective_result: ObjectiveResult
    proof_classes: tuple[str, ...]


class BoundVerificationEvidenceValidator:
    """Validate durable verification facts without creating semantic records."""

    _KINDS = frozenset({"closed-verification", "verification-result", "task-objective-proof"})
    _PROOF_CLASSES = frozenset(
        {"execution", "observation", "closed-verification", "objective-verification", "revalidation"}
    )

    @staticmethod
    def proof_metadata(record: object) -> dict[str, Any] | None:
        metadata = getattr(record, "metadata", None)
        return metadata if isinstance(metadata, dict) else None

    @classmethod
    def proof_class(cls, record: object, metadata: dict[str, Any]) -> str:
        explicit = metadata.get("proof_class")
        if explicit is not None:
            value = str(explicit).strip().lower()
            if value not in cls._PROOF_CLASSES:
                raise ValueError(f"verification proof has unknown proof_class {explicit!r}")
            return value
        kind = str(getattr(record, "kind", "")).strip().lower()
        if kind == "task-objective-proof":
            return "objective-verification"
        return "closed-verification"

    @staticmethod
    def proof_can_cover(proof_class: str, obligation: str) -> bool:
        if proof_class == "execution":
            return False
        normalized = obligation.strip().lower()
        if normalized.startswith("revalidate."):
            return proof_class == "revalidation"
        if normalized.startswith("verify."):
            return proof_class in {"closed-verification", "objective-verification", "revalidation"}
        if normalized.startswith("observe."):
            return proof_class in {"observation", "closed-verification", "revalidation"}
        return proof_class in {
            "observation",
            "closed-verification",
            "objective-verification",
            "revalidation",
        }

    @classmethod
    def validate(
        cls,
        *,
        work: Work,
        run: Run,
        refs: Iterable[str],
        record_lookup: Callable[[str], object | None],
        expected_scope: dict[str, Any],
        allowed_results: frozenset[ObjectiveResult] = frozenset({"pass", "fail"}),
        expected_work_version: object | None = None,
        expected_subject_version_refs: Iterable[str] | None = None,
        expected_acceptance_criteria: list[str] | None = None,
        action: Action | None = None,
        step: Step | None = None,
        attempt: StepAttempt | None = None,
        expected_request_id: str | None = None,
        expected_attempt_ref: str | None = None,
        require_execution_binding: bool = False,
        require_verifier_provenance: bool = False,
    ) -> BoundVerificationEvidence:
        normalized = [str(ref) for ref in refs if str(ref).strip()]
        if not normalized:
            raise ValueError("verification requires durable proof refs")
        if len(set(normalized)) != len(normalized):
            raise ValueError("verification proof refs must be unique")
        if work.id != run.work_id:
            raise ValueError("verification work/run binding mismatch")

        if require_execution_binding:
            if action is None or step is None or attempt is None:
                raise ValueError("verification requires complete durable execution graph")
            if action.work_id != work.id or action.run_id != run.id:
                raise ValueError("verification Action is not bound to expected Work/Run")
            if step.run_id != run.id or attempt.step_id != step.id:
                raise ValueError("verification Attempt/Step/Run binding mismatch")
            if expected_attempt_ref != attempt.id:
                raise ValueError("verification attempt identity mismatch")
            if not expected_request_id or attempt.request_ref != expected_request_id:
                raise ValueError("verification request identity mismatch")
            if action.request_ref != expected_request_id or attempt.request_ref != action.request_ref:
                raise ValueError("verification Action/Attempt request binding mismatch")
            if attempt.provider_id != action.provider_id:
                raise ValueError("verification execution provider identity mismatch")

        expected_versions = (
            sorted({str(value) for value in expected_subject_version_refs if str(value).strip()})
            if expected_subject_version_refs is not None
            else None
        )
        records: list[EvidenceArtifact] = []
        proof_classes: list[str] = []
        results: set[ObjectiveResult] = set()
        for ref in normalized:
            record = record_lookup(ref)
            if getattr(record, "record_type", None) != "EvidenceArtifact":
                raise ValueError("verification requires typed EvidenceArtifact proofs")
            try:
                if isinstance(record, EvidenceArtifact):
                    artifact = record
                elif isinstance(record, BaseRecord):
                    artifact = EvidenceArtifact.model_validate(record.model_dump(mode="python"))
                else:
                    raise ValueError("verification requires typed EvidenceArtifact proofs")
            except (ValueError, TypeError) as exc:
                raise ValueError("verification requires typed EvidenceArtifact proofs") from exc
            if artifact.kind not in cls._KINDS:
                raise ValueError("verification requires typed closed verification proof kinds")
            metadata = cls.proof_metadata(artifact)
            if metadata is None:
                raise ValueError("verification proof metadata required")
            closed = metadata.get("verification_result")
            if not isinstance(closed, dict):
                raise ValueError("verification requires explicit closed result")
            result = str(closed.get("result", "")).strip().lower()
            if result not in {"pass", "fail"}:
                raise ValueError("verification result must be explicit pass or fail")
            typed_result = cast(ObjectiveResult, result)
            if typed_result not in allowed_results:
                raise ValueError("verification result is not allowed for this authority")
            results.add(typed_result)
            if metadata.get("work_id") != work.id or metadata.get("run_id") != run.id:
                raise ValueError("verification proof is not bound to expected Work/Run")
            proof_scope = metadata.get("verification_scope", metadata.get("scope"))
            if not isinstance(proof_scope, dict) or proof_scope != expected_scope:
                raise ValueError("verification proof scope mismatch")
            if expected_work_version is not None:
                proof_version = metadata.get("work_version", metadata.get("task_version", metadata.get("version")))
                if proof_version != expected_work_version:
                    raise ValueError("verification proof Work version mismatch")
            if expected_versions is not None:
                raw_versions = metadata.get("subject_version_refs")
                if not isinstance(raw_versions, list):
                    raise ValueError("verification proof subject version refs required")
                actual_versions = sorted({str(value) for value in raw_versions if str(value).strip()})
                if actual_versions != expected_versions:
                    raise ValueError("verification proof subject version binding mismatch")
            if expected_acceptance_criteria is not None:
                criteria = metadata.get("acceptance_criteria", metadata.get("criteria"))
                if not isinstance(criteria, list) or criteria != expected_acceptance_criteria:
                    raise ValueError("verification proof acceptance criteria mismatch")
            if require_execution_binding:
                if action is None or attempt is None:
                    raise ValueError("verification requires complete durable execution graph")
                if metadata.get("action_ref") != action.id or action.id not in artifact.source_refs:
                    raise ValueError("verification proof is not bound to exact Action")
                if metadata.get("request_id") != action.request_ref:
                    raise ValueError("verification proof request binding mismatch")
                if metadata.get("attempt_ref") != attempt.id:
                    raise ValueError("verification proof attempt binding mismatch")
            if require_verifier_provenance:
                provenance = metadata.get("verifier_provenance")
                if not isinstance(provenance, dict):
                    raise ValueError("verification proof requires verifier provenance")
                identity = provenance.get("verifier_id") or provenance.get("provider_id")
                method = provenance.get("method")
                if not isinstance(identity, str) or not identity.strip():
                    raise ValueError("verification proof requires verifier identity")
                if not isinstance(method, str) or not method.strip():
                    raise ValueError("verification proof requires verifier method provenance")
            records.append(artifact)
            proof_classes.append(cls.proof_class(artifact, metadata))

        if len(results) != 1:
            raise ValueError("inconsistent verification closure: pass/fail conflict")
        objective_result = next(iter(results))
        return BoundVerificationEvidence(tuple(records), objective_result, tuple(proof_classes))
