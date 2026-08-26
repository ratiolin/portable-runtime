"""Durable Historical Experience Use authority.

EUA-D linearizes one exact task/domain Assertion with the exact Experience Use
semantic state that the store re-evaluated as allowed at commit time. The
caller supplies expectations, never an authority event or resolved snapshot.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from portable_runtime.core.models import Event
from portable_runtime.experience.use_admission import (
    CURRENT_EXPERIENCE_USE_ADMISSION_CONTRACT,
    EXPERIENCE_USE_REQUIREMENT_SCHEMA,
    RESOLVED_EXPERIENCE_USE_SNAPSHOT_SCHEMA,
    ExperienceUseAdmission,
    ExperienceUseAdmissionEvaluator,
    ExperienceUseRequirement,
    experience_use_requirement_digest,
    experience_use_snapshot_digest,
)
from portable_runtime.records.models import Assertion

HISTORICAL_EXPERIENCE_USE_EVENT_TYPE = "HistoricalExperienceUseRecorded"
HISTORICAL_EXPERIENCE_USE_SCHEMA = "historical-experience-use-v1"
HISTORICAL_EXPERIENCE_USE_SEMANTIC_ROLE = "historical-experience-use"
DOMAIN_JUDGMENT_SEMANTIC_ROLE = "task-domain-judgment"
SUPPORTED_HISTORICAL_EXPERIENCE_USE_CONTRACTS = frozenset(
    {CURRENT_EXPERIENCE_USE_ADMISSION_CONTRACT}
)

HISTORICAL_EXPERIENCE_USE_GRADUATED_COUNTEREXAMPLES = frozenset(
    {f"HUB-{index:03d}" for index in range(1, 9)}
)


@dataclass(frozen=True)
class HistoricalExperienceUseCommitRequest:
    """Caller expectations for one semantic compare-and-bind operation.

    ``judgment`` and ``requirement`` are inputs to store-owned reconstruction.
    The caller cannot submit a durable binding, resolved snapshot payload, or
    assertion/evidence/counterexample refs independently of the requirement.

    ``expected_admission_contract_version`` is optional for historical replay.
    A new commit always uses the current EUA-B contract. Historical replay
    validates the event-declared contract against the historical support set.
    """

    judgment: Assertion
    requirement: ExperienceUseRequirement
    expected_requirement_digest: str
    expected_snapshot_digest: str
    expected_admission_contract_version: str | None = None


@dataclass(frozen=True)
class HistoricalExperienceUse:
    """Typed reconstruction of one durable historical reliance fact."""

    id: str
    judgment_ref: str
    judgment_version: int
    requirement_digest: str
    snapshot_digest: str
    snapshot_semantic_json: str
    selected_projection_refs: tuple[str, ...]
    admission_contract_version: str

    def materialize_snapshot(self) -> dict[str, Any]:
        value = json.loads(self.snapshot_semantic_json)
        if not isinstance(value, dict):
            raise ValueError("historical experience-use snapshot must decode to an object")
        return value


@dataclass(frozen=True)
class PreparedHistoricalExperienceUseCommit:
    binding: HistoricalExperienceUse
    event: Event
    judgment: Assertion
    replayed: bool


class HistoricalExperienceUseStoreReader(Protocol):
    def get_record(self, record_id: str) -> object | None: ...
    def get_event(self, event_id: str) -> Event | None: ...
    def get_knowledge_projection(self, projection_id: str) -> object | None: ...
    def export_state(self) -> dict[str, list[dict[str, object]]]: ...


def _identity_digest(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _assertion_semantics(value: Assertion) -> dict[str, Any]:
    payload = value.model_dump(mode="json")
    payload.pop("created_at", None)
    return payload


def same_assertion_semantics(left: Assertion, right: Assertion) -> bool:
    return _assertion_semantics(left) == _assertion_semantics(right)


def freeze_historical_experience_use_request(
    request: HistoricalExperienceUseCommitRequest,
) -> HistoricalExperienceUseCommitRequest:
    """Detach a commit request from caller-owned mutable objects."""

    requirement = request.requirement
    frozen_requirement = ExperienceUseRequirement(
        projection_refs=tuple(requirement.projection_refs),
        use_scope=copy.deepcopy(dict(requirement.use_scope)),
        subject_version_refs=tuple(requirement.subject_version_refs),
        environment_bindings=copy.deepcopy(dict(requirement.environment_bindings)),
        use_context=copy.deepcopy(dict(requirement.use_context)),
    )
    expected_contract = request.expected_admission_contract_version
    return HistoricalExperienceUseCommitRequest(
        judgment=request.judgment.model_copy(deep=True),
        requirement=frozen_requirement,
        expected_requirement_digest=str(request.expected_requirement_digest),
        expected_snapshot_digest=str(request.expected_snapshot_digest),
        expected_admission_contract_version=(
            None if expected_contract is None else str(expected_contract)
        ),
    )


def historical_experience_use_event_id(judgment_ref: str, judgment_version: int) -> str:
    identity = {
        "schema": HISTORICAL_EXPERIENCE_USE_SCHEMA,
        "semantic_role": HISTORICAL_EXPERIENCE_USE_SEMANTIC_ROLE,
        "judgment_ref": judgment_ref,
        "judgment_version": judgment_version,
    }
    return f"event_historical_experience_use_{_identity_digest(identity)[:32]}"


def _validate_task_domain_judgment(judgment: Assertion) -> None:
    if not judgment.id.strip():
        raise ValueError("Historical Experience Use requires a non-empty judgment id")
    if judgment.version < 1:
        raise ValueError("Historical Experience Use requires a positive judgment version")
    metadata = judgment.metadata if isinstance(judgment.metadata, dict) else {}
    if metadata.get("semantic_role") != DOMAIN_JUDGMENT_SEMANTIC_ROLE:
        raise ValueError(
            "Historical Experience Use requires Assertion metadata.semantic_role="
            f"{DOMAIN_JUDGMENT_SEMANTIC_ROLE!r}"
        )


def _validate_role_separation_from_current_projections(
    store: HistoricalExperienceUseStoreReader,
    judgment: Assertion,
    requirement: ExperienceUseRequirement,
) -> None:
    for projection_ref in requirement.projection_refs:
        projection = store.get_knowledge_projection(projection_ref)
        if projection is None:
            continue
        for field in ("epistemic_judgment_refs", "current_assertion_refs"):
            refs = getattr(projection, field, ())
            if judgment.id in refs:
                raise ValueError(
                    "task/domain judgment cannot be an assertion or epistemic "
                    "judgment that qualifies selected experience"
                )


def _validate_role_separation(judgment: Assertion, admission: ExperienceUseAdmission) -> None:
    snapshot = admission.resolved_snapshot.materialize()
    projections = snapshot.get("projections")
    if not isinstance(projections, list):
        raise ValueError("Experience Use snapshot is missing canonical projections")
    for raw in projections:
        if not isinstance(raw, dict):
            raise ValueError("Experience Use snapshot contains malformed projection payload")
        qualifying_refs: set[str] = set()
        for field in ("epistemic_judgment_refs", "current_assertion_refs"):
            refs = raw.get(field)
            if isinstance(refs, list):
                qualifying_refs.update(str(ref) for ref in refs if isinstance(ref, str))
        if judgment.id in qualifying_refs:
            raise ValueError(
                "task/domain judgment cannot be an assertion or epistemic "
                "judgment that qualifies selected experience"
            )


def _event_from_admission(judgment: Assertion, admission: ExperienceUseAdmission) -> Event:
    snapshot = admission.resolved_snapshot.materialize()
    requirement_payload = snapshot.get("requirement")
    if not isinstance(requirement_payload, dict):
        raise ValueError("allowed Experience Use snapshot is missing its requirement payload")
    projection_refs = requirement_payload.get("projection_refs")
    if not isinstance(projection_refs, list) or not all(
        isinstance(ref, str) for ref in projection_refs
    ):
        raise ValueError("allowed Experience Use snapshot has malformed projection refs")
    event_id = historical_experience_use_event_id(judgment.id, judgment.version)
    return Event(
        id=event_id,
        type=HISTORICAL_EXPERIENCE_USE_EVENT_TYPE,
        subject_ref=judgment.id,
        payload={
            "schema": HISTORICAL_EXPERIENCE_USE_SCHEMA,
            "semantic_role": HISTORICAL_EXPERIENCE_USE_SEMANTIC_ROLE,
            "judgment_ref": judgment.id,
            "judgment_version": judgment.version,
            "requirement_digest": admission.requirement_digest,
            "snapshot_digest": admission.snapshot_digest,
            "snapshot_semantic_json": admission.resolved_snapshot.semantic_json,
            "selected_projection_refs": list(projection_refs),
            "admission_contract_version": admission.admission_contract_version,
        },
    )


def historical_experience_use_from_event(event: Event) -> HistoricalExperienceUse:
    """Reconstruct and self-validate the typed historical authority."""

    if event.type != HISTORICAL_EXPERIENCE_USE_EVENT_TYPE:
        raise ValueError("event is not a Historical Experience Use authority event")
    payload = event.payload
    if payload.get("schema") != HISTORICAL_EXPERIENCE_USE_SCHEMA:
        raise ValueError("Historical Experience Use schema mismatch")
    if payload.get("semantic_role") != HISTORICAL_EXPERIENCE_USE_SEMANTIC_ROLE:
        raise ValueError("Historical Experience Use semantic role mismatch")

    judgment_ref = payload.get("judgment_ref")
    judgment_version = payload.get("judgment_version")
    requirement_digest = payload.get("requirement_digest")
    snapshot_digest = payload.get("snapshot_digest")
    snapshot_semantic_json = payload.get("snapshot_semantic_json")
    selected_projection_refs = payload.get("selected_projection_refs")
    contract_version = payload.get("admission_contract_version")

    if not isinstance(judgment_ref, str) or not judgment_ref:
        raise ValueError("Historical Experience Use judgment_ref is invalid")
    if not isinstance(judgment_version, int) or judgment_version < 1:
        raise ValueError("Historical Experience Use judgment_version is invalid")
    if event.subject_ref != judgment_ref:
        raise ValueError("Historical Experience Use subject/judgment mismatch")
    expected_id = historical_experience_use_event_id(judgment_ref, judgment_version)
    if event.id != expected_id:
        raise ValueError("Historical Experience Use deterministic identity mismatch")
    if not isinstance(requirement_digest, str) or not _is_sha256(requirement_digest):
        raise ValueError("Historical Experience Use requirement_digest is invalid")
    if not isinstance(snapshot_digest, str) or not _is_sha256(snapshot_digest):
        raise ValueError("Historical Experience Use snapshot_digest is invalid")
    if not isinstance(snapshot_semantic_json, str):
        raise ValueError("Historical Experience Use snapshot payload is invalid")
    if experience_use_snapshot_digest(snapshot_semantic_json) != snapshot_digest:
        raise ValueError("Historical Experience Use snapshot digest mismatch")
    if (
        not isinstance(contract_version, str)
        or contract_version not in SUPPORTED_HISTORICAL_EXPERIENCE_USE_CONTRACTS
    ):
        raise ValueError("Historical Experience Use admission contract is unsupported")
    if not isinstance(selected_projection_refs, list) or not all(
        isinstance(ref, str) and ref for ref in selected_projection_refs
    ):
        raise ValueError("Historical Experience Use selected projection refs are invalid")
    if selected_projection_refs != sorted(set(selected_projection_refs)):
        raise ValueError("Historical Experience Use selected projection refs are not canonical")

    try:
        snapshot = json.loads(snapshot_semantic_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Historical Experience Use snapshot JSON is invalid") from exc
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("schema") != RESOLVED_EXPERIENCE_USE_SNAPSHOT_SCHEMA
    ):
        raise ValueError("Historical Experience Use snapshot schema mismatch")
    requirement = snapshot.get("requirement")
    if (
        not isinstance(requirement, dict)
        or requirement.get("schema") != EXPERIENCE_USE_REQUIREMENT_SCHEMA
    ):
        raise ValueError("Historical Experience Use requirement schema mismatch")
    if experience_use_requirement_digest(requirement) != requirement_digest:
        raise ValueError("Historical Experience Use embedded requirement digest mismatch")
    embedded_refs = requirement.get("projection_refs")
    if embedded_refs != selected_projection_refs:
        raise ValueError("Historical Experience Use projection selection mismatch")
    projections = snapshot.get("projections")
    if not isinstance(projections, list):
        raise ValueError("Historical Experience Use snapshot projections are malformed")
    resolved_projection_ids = [
        raw.get("id")
        for raw in projections
        if isinstance(raw, dict) and isinstance(raw.get("id"), str)
    ]
    if resolved_projection_ids != selected_projection_refs:
        raise ValueError("Historical Experience Use resolved projection set mismatch")

    return HistoricalExperienceUse(
        id=event.id,
        judgment_ref=judgment_ref,
        judgment_version=judgment_version,
        requirement_digest=requirement_digest,
        snapshot_digest=snapshot_digest,
        snapshot_semantic_json=snapshot_semantic_json,
        selected_projection_refs=tuple(selected_projection_refs),
        admission_contract_version=contract_version,
    )


def same_historical_experience_use_semantics(left: Event, right: Event) -> bool:
    left_payload = left.model_dump(mode="json")
    right_payload = right.model_dump(mode="json")
    left_payload.pop("created_at", None)
    right_payload.pop("created_at", None)
    return left_payload == right_payload


def prepare_historical_experience_use_commit(
    store: HistoricalExperienceUseStoreReader,
    request: HistoricalExperienceUseCommitRequest,
) -> PreparedHistoricalExperienceUseCommit:
    """Prepare one new compare-and-bind or exact historical replay.

    New commits re-evaluate EUA-B inside the caller's store transaction.
    Existing historical bindings replay from their immutable payload and do
    not consult future/current KnowledgeProjection state.
    """

    _validate_task_domain_judgment(request.judgment)
    if not _is_sha256(request.expected_requirement_digest):
        raise ValueError("expected Experience Use requirement digest is invalid")
    if not _is_sha256(request.expected_snapshot_digest):
        raise ValueError("expected Experience Use snapshot digest is invalid")

    event_id = historical_experience_use_event_id(
        request.judgment.id,
        request.judgment.version,
    )
    existing_event = store.get_event(event_id)
    if existing_event is None:
        _validate_role_separation_from_current_projections(
            store,
            request.judgment,
            request.requirement,
        )
    existing_record = store.get_record(request.judgment.id)

    if existing_event is not None:
        if existing_record is None:
            raise ValueError("Historical Experience Use authority graph is incomplete: judgment missing")
        if not isinstance(existing_record, Assertion):
            raise ValueError("Historical Experience Use judgment ref does not resolve to Assertion")
        if existing_record.version != request.judgment.version or not same_assertion_semantics(
            existing_record,
            request.judgment,
        ):
            raise ValueError("Historical Experience Use exact judgment identity rebound")
        binding = historical_experience_use_from_event(existing_event)
        request_requirement_digest = experience_use_requirement_digest(request.requirement)
        if request_requirement_digest != binding.requirement_digest:
            raise ValueError("Historical Experience Use requirement rebound")
        if request.expected_requirement_digest != binding.requirement_digest:
            raise ValueError("Historical Experience Use expected requirement rebound")
        if request.expected_snapshot_digest != binding.snapshot_digest:
            raise ValueError("Historical Experience Use snapshot rebound")
        if (
            request.expected_admission_contract_version is not None
            and request.expected_admission_contract_version != binding.admission_contract_version
        ):
            raise ValueError("Historical Experience Use admission contract rebound")
        if tuple(request.requirement.projection_refs) != binding.selected_projection_refs:
            raise ValueError("Historical Experience Use projection selection rebound")
        return PreparedHistoricalExperienceUseCommit(
            binding=binding,
            event=existing_event,
            judgment=existing_record,
            replayed=True,
        )

    if existing_record is not None:
        raise ValueError("retroactive Historical Experience Use backfill onto an existing judgment is closed")

    expected_contract = (
        CURRENT_EXPERIENCE_USE_ADMISSION_CONTRACT
        if request.expected_admission_contract_version is None
        else request.expected_admission_contract_version
    )
    if expected_contract != CURRENT_EXPERIENCE_USE_ADMISSION_CONTRACT:
        raise ValueError("Experience Use admission contract changed before historical commit")

    admission = ExperienceUseAdmissionEvaluator(store).evaluate(request.requirement)
    if admission.status != "allowed":
        raise ValueError(f"Historical Experience Use requires allowed admission, got {admission.status!r}")
    if admission.admission_contract_version != expected_contract:
        raise ValueError("Experience Use admission contract changed before historical commit")
    if admission.requirement_digest != request.expected_requirement_digest:
        raise ValueError("Experience Use requirement changed before historical commit")
    if admission.snapshot_digest != request.expected_snapshot_digest:
        raise ValueError("Experience Use semantic snapshot changed before historical commit")

    _validate_role_separation(request.judgment, admission)
    event = _event_from_admission(request.judgment, admission)
    binding = historical_experience_use_from_event(event)
    return PreparedHistoricalExperienceUseCommit(
        binding=binding,
        event=event,
        judgment=request.judgment,
        replayed=False,
    )


def validate_historical_experience_use_authority_graph(
    state: Mapping[str, list[dict[str, object]]],
) -> None:
    """Validate every durable Historical Experience Use event and its judgment."""

    records = {
        str(raw.get("id")): raw
        for raw in state.get("record", [])
        if isinstance(raw, dict) and isinstance(raw.get("id"), str)
    }
    seen: set[tuple[str, int]] = set()
    for raw in state.get("event", []):
        if not isinstance(raw, dict) or raw.get("type") != HISTORICAL_EXPERIENCE_USE_EVENT_TYPE:
            continue
        event = Event.model_validate(raw)
        binding = historical_experience_use_from_event(event)
        key = (binding.judgment_ref, binding.judgment_version)
        if key in seen:
            raise ValueError("duplicate Historical Experience Use authority for exact judgment identity")
        seen.add(key)
        record = records.get(binding.judgment_ref)
        if record is None:
            raise ValueError("Historical Experience Use authority graph is incomplete: judgment missing")
        if record.get("record_type") != "Assertion":
            raise ValueError("Historical Experience Use judgment must resolve to Assertion")
        if record.get("version") != binding.judgment_version:
            raise ValueError("Historical Experience Use judgment version mismatch")
        metadata = record.get("metadata")
        if (
            not isinstance(metadata, dict)
            or metadata.get("semantic_role") != DOMAIN_JUDGMENT_SEMANTIC_ROLE
        ):
            raise ValueError("Historical Experience Use judgment semantic role mismatch")


def assert_historical_experience_use_import_closed(
    prepared: Mapping[str, list[dict[str, object]]],
) -> None:
    """Generic state/bundle import is never an Historical Experience Use authority path."""

    for raw in prepared.get("event", []):
        if isinstance(raw, dict) and raw.get("type") == HISTORICAL_EXPERIENCE_USE_EVENT_TYPE:
            raise ValueError("Historical Experience Use authority import/backfill is closed")
