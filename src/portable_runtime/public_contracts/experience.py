from __future__ import annotations

from typing import Any

from portable_runtime.experience.historical_use import (
    HISTORICAL_EXPERIENCE_USE_EVENT_TYPE,
    HistoricalExperienceUseCommitRequest,
    historical_experience_use_from_event,
)
from portable_runtime.experience.use_admission import (
    ExperienceUseAdmissionEvaluator,
    ExperienceUseRequirement,
)
from portable_runtime.public_contracts.models import (
    ExperienceUseAdmissionV1,
    ExperienceUseRequirementV1,
    HistoricalExperienceUseCommitV1,
    HistoricalExperienceUseV1,
)
from portable_runtime.records.models import Assertion


def _store(value: Any) -> Any:
    return getattr(value, "store", value)


def _requirement(value: ExperienceUseRequirementV1) -> ExperienceUseRequirement:
    return ExperienceUseRequirement(
        projection_refs=tuple(value.projection_refs),
        use_scope=value.use_scope,
        subject_version_refs=tuple(value.subject_version_refs),
        environment_bindings=value.environment_bindings,
        use_context=value.use_context,
    )


def evaluate_experience_use_contract(
    runtime_or_store: Any,
    value: ExperienceUseRequirementV1,
) -> ExperienceUseAdmissionV1:
    """Evaluate through the existing Python oracle without adding semantics."""

    admission = ExperienceUseAdmissionEvaluator(_store(runtime_or_store)).evaluate(_requirement(value))
    return ExperienceUseAdmissionV1(
        status=admission.status,
        requirement_digest=admission.requirement_digest,
        snapshot_digest=admission.snapshot_digest,
        resolved_snapshot=admission.resolved_snapshot.materialize(),
        reasons=list(admission.reasons),
    )


def commit_historical_experience_use_contract(
    runtime_or_store: Any,
    value: HistoricalExperienceUseCommitV1,
) -> HistoricalExperienceUseV1:
    """Compare-and-bind through store authority; caller-supplied digests are expectations only."""

    store = _store(runtime_or_store)
    judgment = Assertion.model_validate(value.judgment)
    binding = store.commit_historical_experience_use(
        HistoricalExperienceUseCommitRequest(
            judgment=judgment,
            requirement=_requirement(value.requirement),
            expected_requirement_digest=value.expected_requirement_digest,
            expected_snapshot_digest=value.expected_snapshot_digest,
            expected_admission_contract_version=value.expected_admission_contract_version,
        )
    )
    return HistoricalExperienceUseV1(
        id=binding.id,
        judgment_ref=binding.judgment_ref,
        judgment_version=binding.judgment_version,
        requirement_digest=binding.requirement_digest,
        snapshot_digest=binding.snapshot_digest,
        snapshot_semantic_json=binding.snapshot_semantic_json,
        selected_projection_refs=list(binding.selected_projection_refs),
        admission_contract_version=binding.admission_contract_version,
    )


def get_historical_experience_use_contract(
    runtime_or_store: Any,
    judgment_id: str,
) -> HistoricalExperienceUseV1 | None:
    store = _store(runtime_or_store)
    candidates = []
    for event in store.list_events(judgment_id):
        if event.type != HISTORICAL_EXPERIENCE_USE_EVENT_TYPE:
            continue
        candidates.append(historical_experience_use_from_event(event))
    if not candidates:
        return None
    binding = max(candidates, key=lambda item: item.judgment_version)
    return HistoricalExperienceUseV1(
        id=binding.id,
        judgment_ref=binding.judgment_ref,
        judgment_version=binding.judgment_version,
        requirement_digest=binding.requirement_digest,
        snapshot_digest=binding.snapshot_digest,
        snapshot_semantic_json=binding.snapshot_semantic_json,
        selected_projection_refs=list(binding.selected_projection_refs),
        admission_contract_version=binding.admission_contract_version,
    )
