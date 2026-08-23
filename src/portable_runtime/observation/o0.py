"""Executable O0 observational bridge contract.

REF-2 keeps runtime/formal internal semantics distinct and projects only explicit
finite observation bundles into a neutral, versioned snapshot.  Information-loss
classifications are first-class values; semantic mismatches are never converted
into adapter errors or silently normalized away.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from portable_runtime.records.authorization import AuthorizationGrant, AuthorizationUse, is_grant_valid
from portable_runtime.records.models import Assertion, BaseRecord, RevisionRecord
from portable_runtime.records.relations import RecordRelation
from portable_runtime.records.reopen import ReopenAssessment
from portable_runtime.records.revalidation import AffectedAssessment, DependencyImpact

ObservationOrigin = Literal["runtime", "formal"]
ObservationQuality = Literal[
    "EXACT-SHAPE",
    "ABSTRACTION",
    "PARTIAL",
    "SEMANTIC-MISMATCH",
    "NOT-REPRESENTED",
]
ObservationFamily = Literal[
    "historicalTrace",
    "historicalDependency",
    "operativeStatus",
    "activationUse",
    "impactObservation",
    "reviewInvalidation",
    "dischargeRequirement",
    "dischargeEvidence",
    "regimeReference",
]


class O0Observation(BaseModel):
    """One neutral observation with explicit source semantics and loss class."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: ObservationOrigin
    family: ObservationFamily
    subject_ref: str
    semantics_tag: str
    quality: ObservationQuality
    bridge_key: str | None = None
    bridge_value: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    coordinates: dict[str, str] = Field(default_factory=dict)


class O0Snapshot(BaseModel):
    """Versioned serialized O0 output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["o0-v1"] = "o0-v1"
    origin: ObservationOrigin
    observed_at: datetime
    observations: list[O0Observation] = Field(default_factory=list)


@dataclass(frozen=True)
class RuntimeObservationBundle0:
    """Finite runtime observation boundary supplied to ``alpha_r0``."""

    observed_at: datetime
    records: list[BaseRecord] = field(default_factory=list)
    relations: list[RecordRelation] = field(default_factory=list)
    authorization_grants: list[AuthorizationGrant] = field(default_factory=list)
    authorization_uses: list[AuthorizationUse] = field(default_factory=list)
    impacts: list[DependencyImpact] = field(default_factory=list)
    assessments: list[AffectedAssessment] = field(default_factory=list)
    reopen_assessments: list[ReopenAssessment] = field(default_factory=list)


class FormalHistoricalTraceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_ref: str
    trace_kind: str
    source_refs: list[str] = Field(default_factory=list)
    coordinates: dict[str, str] = Field(default_factory=dict)


class FormalDependencyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_ref: str
    relation_tag: str
    object_ref: str
    source_refs: list[str] = Field(default_factory=list)
    coordinates: dict[str, str] = Field(default_factory=dict)


class FormalOperativeStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_ref: str
    layer: str
    status: str
    source_refs: list[str] = Field(default_factory=list)
    coordinates: dict[str, str] = Field(default_factory=dict)


class FormalActivationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_ref: str
    activation_kind: str
    source_refs: list[str] = Field(default_factory=list)
    coordinates: dict[str, str] = Field(default_factory=dict)


class FormalImpactInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_ref: str
    target_ref: str
    propagation: str
    source_refs: list[str] = Field(default_factory=list)
    coordinates: dict[str, str] = Field(default_factory=dict)


class FormalReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_ref: str
    review_state: str
    source_refs: list[str] = Field(default_factory=list)
    coordinates: dict[str, str] = Field(default_factory=dict)


class FormalRequirementInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_ref: str
    requirement: str
    source_refs: list[str] = Field(default_factory=list)
    coordinates: dict[str, str] = Field(default_factory=dict)


class FormalEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_ref: str
    evidence_kind: str
    source_refs: list[str] = Field(default_factory=list)
    coordinates: dict[str, str] = Field(default_factory=dict)


class FormalRegimeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_ref: str
    regime_kind: str
    regime_ref: str
    source_refs: list[str] = Field(default_factory=list)
    coordinates: dict[str, str] = Field(default_factory=dict)


@dataclass(frozen=True)
class FormalObservationBundle0:
    """Finite formal observation boundary supplied to ``alpha_f0``.

    The bundle contains already-selected finite observations/witnesses.  It is
    deliberately not a serialized Lean state and does not claim total extraction
    from functional canonical maps.
    """

    observed_at: datetime
    historical_traces: list[FormalHistoricalTraceInput] = field(default_factory=list)
    dependencies: list[FormalDependencyInput] = field(default_factory=list)
    operative_statuses: list[FormalOperativeStatusInput] = field(default_factory=list)
    activations: list[FormalActivationInput] = field(default_factory=list)
    impacts: list[FormalImpactInput] = field(default_factory=list)
    reviews: list[FormalReviewInput] = field(default_factory=list)
    requirements: list[FormalRequirementInput] = field(default_factory=list)
    evidence: list[FormalEvidenceInput] = field(default_factory=list)
    regimes: list[FormalRegimeInput] = field(default_factory=list)


class B0Coordinate(BaseModel):
    """One correspondence coordinate discovered from actual adapter outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    family: ObservationFamily
    bridge_key: str
    witnesses: int


@dataclass(frozen=True)
class O0ComparisonCase:
    runtime: O0Snapshot
    formal: O0Snapshot
    runtime_to_formal_ids: dict[str, str]


def _runtime_assertion_bridge_value(status: str | None) -> str | None:
    if status == "supported":
        return "qualified"
    if status in {"revalidation-required", "refuted"}:
        return "withdrawn"
    return None


def alpha_r0(bundle: RuntimeObservationBundle0) -> O0Snapshot:
    """Project one finite runtime bundle into the neutral O0 contract."""

    observations: list[O0Observation] = []

    for record in bundle.records:
        observations.append(
            O0Observation(
                origin="runtime",
                family="historicalTrace",
                subject_ref=record.id,
                semantics_tag=f"runtime.record.{record.record_type}",
                quality="ABSTRACTION",
                bridge_key="trace.referent-present",
                bridge_value="present",
                source_refs=[record.id],
                coordinates={
                    "record_type": record.record_type,
                    "version": str(record.version),
                    "lifecycle": record.lifecycle_status,
                },
            )
        )
        if isinstance(record, Assertion) and record.epistemic_status is not None:
            bridge_value = _runtime_assertion_bridge_value(record.epistemic_status)
            observations.append(
                O0Observation(
                    origin="runtime",
                    family="operativeStatus",
                    subject_ref=record.id,
                    semantics_tag="runtime.assertion-epistemic-status",
                    quality="ABSTRACTION",
                    bridge_key="qualification.current" if bridge_value is not None else None,
                    bridge_value=bridge_value,
                    source_refs=[record.id],
                    coordinates={
                        "layer": "assertion.epistemic_status",
                        "status": record.epistemic_status,
                    },
                )
            )
        for name, value in record.environment_versions.items():
            observations.append(
                O0Observation(
                    origin="runtime",
                    family="regimeReference",
                    subject_ref=record.id,
                    semantics_tag="runtime.environment-version",
                    quality="ABSTRACTION",
                    source_refs=[record.id],
                    coordinates={"name": name, "version": value},
                )
            )
        if isinstance(record, RevisionRecord) and record.lifecycle_status in {"applied", "verified", "accepted"}:
            observations.append(
                O0Observation(
                    origin="runtime",
                    family="dischargeEvidence",
                    subject_ref=record.subject_ref,
                    semantics_tag="runtime.revision-lifecycle-evidence",
                    quality="PARTIAL",
                    source_refs=[record.id],
                    coordinates={"status": record.lifecycle_status},
                )
            )

    for relation in bundle.relations:
        observations.append(
            O0Observation(
                origin="runtime",
                family="historicalDependency",
                subject_ref=relation.subject_ref,
                semantics_tag=f"runtime.relation.{relation.relation_type}",
                quality="ABSTRACTION",
                source_refs=[relation.id],
                coordinates={"object_ref": relation.object_ref, "relation_type": relation.relation_type},
            )
        )

    for grant in bundle.authorization_grants:
        current = is_grant_valid(grant, now=bundle.observed_at)
        observations.append(
            O0Observation(
                origin="runtime",
                family="historicalTrace",
                subject_ref=grant.id,
                semantics_tag="runtime.authorization-grant-record",
                quality="ABSTRACTION",
                bridge_key="trace.referent-present",
                bridge_value="present",
                source_refs=[grant.id],
                coordinates={"grantee_ref": grant.grantee_ref},
            )
        )
        observations.append(
            O0Observation(
                origin="runtime",
                family="operativeStatus",
                subject_ref=grant.id,
                semantics_tag="runtime.authorization-current-at-observedAt",
                quality="PARTIAL",
                source_refs=[grant.id],
                coordinates={"layer": "authorization", "status": "current" if current else "not-current"},
            )
        )

    for use in bundle.authorization_uses:
        observations.append(
            O0Observation(
                origin="runtime",
                family="historicalTrace",
                subject_ref=use.id,
                semantics_tag="runtime.authorization-use-at-time",
                quality="ABSTRACTION",
                bridge_key="trace.referent-present",
                bridge_value="present",
                source_refs=[use.id, use.authorization_ref],
                coordinates={"authorized_at": use.authorized_at.isoformat()},
            )
        )
        observations.append(
            O0Observation(
                origin="runtime",
                family="activationUse",
                subject_ref=use.id,
                semantics_tag="runtime.authorization-use-at-time",
                quality="PARTIAL",
                source_refs=[use.id, use.authorization_ref],
                coordinates={
                    "actor_ref": use.actor_ref,
                    "resource_ref": use.resource_ref,
                    "capability": use.capability,
                },
            )
        )

    for impact in bundle.impacts:
        observations.append(
            O0Observation(
                origin="runtime",
                family="impactObservation",
                subject_ref=impact.affected_ref,
                semantics_tag="runtime.direct-typed-impact",
                quality="SEMANTIC-MISMATCH",
                source_refs=list(impact.reason_refs),
                coordinates={
                    "change_ref": impact.change_ref,
                    "relation_type": impact.relation_type,
                },
            )
        )

    for assessment in bundle.assessments:
        disposition = assessment.revalidation_disposition
        if disposition is not None:
            observations.append(
                O0Observation(
                    origin="runtime",
                    family="dischargeRequirement",
                    subject_ref=assessment.affected_ref,
                    semantics_tag="runtime.policy-disposition",
                    quality="SEMANTIC-MISMATCH",
                    source_refs=list(disposition.rationale_refs),
                    coordinates={
                        "action": disposition.action,
                        "policy_ref": disposition.policy_ref,
                    },
                )
            )
            if disposition.action in {"block-next-use", "require-human-review", "reopen"}:
                observations.append(
                    O0Observation(
                        origin="runtime",
                        family="reviewInvalidation",
                        subject_ref=assessment.affected_ref,
                        semantics_tag="runtime.review-or-block-disposition",
                        quality="PARTIAL",
                        source_refs=list(disposition.rationale_refs),
                        coordinates={"action": disposition.action},
                    )
                )

    for reopen in bundle.reopen_assessments:
        observations.append(
            O0Observation(
                origin="runtime",
                family="reviewInvalidation",
                subject_ref=reopen.record_ref,
                semantics_tag="runtime.reopen-assessment",
                quality="PARTIAL",
                source_refs=list(reopen.reason_refs),
                coordinates={"revision_scope": reopen.revision_scope},
            )
        )
        observations.append(
            O0Observation(
                origin="runtime",
                family="dischargeRequirement",
                subject_ref=reopen.record_ref,
                semantics_tag="runtime.reopen-scope",
                quality="PARTIAL",
                source_refs=list(reopen.reason_refs),
                coordinates={"revision_scope": reopen.revision_scope},
            )
        )

    return O0Snapshot(origin="runtime", observed_at=bundle.observed_at, observations=observations)


def alpha_f0(bundle: FormalObservationBundle0) -> O0Snapshot:
    """Project one explicit finite formal observation bundle into O0."""

    observations: list[O0Observation] = []

    for trace in bundle.historical_traces:
        observations.append(
            O0Observation(
                origin="formal",
                family="historicalTrace",
                subject_ref=trace.subject_ref,
                semantics_tag=f"formal.trace.{trace.trace_kind}",
                quality="ABSTRACTION",
                bridge_key="trace.referent-present",
                bridge_value="present",
                source_refs=list(trace.source_refs),
                coordinates=dict(trace.coordinates),
            )
        )

    for dependency in bundle.dependencies:
        coordinates = dict(dependency.coordinates)
        coordinates.update({"object_ref": dependency.object_ref, "relation_tag": dependency.relation_tag})
        observations.append(
            O0Observation(
                origin="formal",
                family="historicalDependency",
                subject_ref=dependency.subject_ref,
                semantics_tag=f"formal.dependency.{dependency.relation_tag}",
                quality="ABSTRACTION",
                source_refs=list(dependency.source_refs),
                coordinates=coordinates,
            )
        )

    for status in bundle.operative_statuses:
        bridge_value = status.status if status.status in {"qualified", "withdrawn"} else None
        bridge_key = "qualification.current" if status.layer == "warrant.usable" and bridge_value is not None else None
        coordinates = dict(status.coordinates)
        coordinates.update({"layer": status.layer, "status": status.status})
        observations.append(
            O0Observation(
                origin="formal",
                family="operativeStatus",
                subject_ref=status.subject_ref,
                semantics_tag=f"formal.status.{status.layer}",
                quality="ABSTRACTION" if bridge_key is not None else "PARTIAL",
                bridge_key=bridge_key,
                bridge_value=bridge_value,
                source_refs=list(status.source_refs),
                coordinates=coordinates,
            )
        )

    for activation in bundle.activations:
        observations.append(
            O0Observation(
                origin="formal",
                family="activationUse",
                subject_ref=activation.subject_ref,
                semantics_tag=f"formal.activation.{activation.activation_kind}",
                quality="PARTIAL",
                source_refs=list(activation.source_refs),
                coordinates=dict(activation.coordinates),
            )
        )

    for impact in bundle.impacts:
        coordinates = dict(impact.coordinates)
        coordinates.update({"target_ref": impact.target_ref, "propagation": impact.propagation})
        observations.append(
            O0Observation(
                origin="formal",
                family="impactObservation",
                subject_ref=impact.subject_ref,
                semantics_tag="formal.transitive-historical-challenge-impact",
                quality="SEMANTIC-MISMATCH",
                source_refs=list(impact.source_refs),
                coordinates=coordinates,
            )
        )

    for review in bundle.reviews:
        coordinates = dict(review.coordinates)
        coordinates["review_state"] = review.review_state
        observations.append(
            O0Observation(
                origin="formal",
                family="reviewInvalidation",
                subject_ref=review.subject_ref,
                semantics_tag="formal.challenge-review-currentness",
                quality="PARTIAL",
                source_refs=list(review.source_refs),
                coordinates=coordinates,
            )
        )

    for requirement in bundle.requirements:
        coordinates = dict(requirement.coordinates)
        coordinates["requirement"] = requirement.requirement
        observations.append(
            O0Observation(
                origin="formal",
                family="dischargeRequirement",
                subject_ref=requirement.subject_ref,
                semantics_tag="formal.repair-requirement",
                quality="SEMANTIC-MISMATCH",
                source_refs=list(requirement.source_refs),
                coordinates=coordinates,
            )
        )

    for evidence in bundle.evidence:
        coordinates = dict(evidence.coordinates)
        coordinates["evidence_kind"] = evidence.evidence_kind
        observations.append(
            O0Observation(
                origin="formal",
                family="dischargeEvidence",
                subject_ref=evidence.subject_ref,
                semantics_tag="formal.repair-realization-evidence",
                quality="PARTIAL",
                source_refs=list(evidence.source_refs),
                coordinates=coordinates,
            )
        )

    for regime in bundle.regimes:
        coordinates = dict(regime.coordinates)
        coordinates.update({"regime_kind": regime.regime_kind, "regime_ref": regime.regime_ref})
        observations.append(
            O0Observation(
                origin="formal",
                family="regimeReference",
                subject_ref=regime.subject_ref,
                semantics_tag="formal.regime-reference",
                quality="ABSTRACTION",
                source_refs=list(regime.source_refs),
                coordinates=coordinates,
            )
        )

    return O0Snapshot(origin="formal", observed_at=bundle.observed_at, observations=observations)


def discover_b0(cases: list[O0ComparisonCase]) -> list[B0Coordinate]:
    """Discover witnessed common coordinates without a hard-coded family allowlist.

    A coordinate is admitted only when both adapters actually emit the same
    ``bridge_key`` and ``bridge_value`` for explicitly mapped subject identities,
    and neither observation is classified as a semantic mismatch or absent.
    """

    counts: dict[tuple[ObservationFamily, str], int] = {}
    excluded = {"SEMANTIC-MISMATCH", "NOT-REPRESENTED"}

    for case in cases:
        formal_index: dict[tuple[ObservationFamily, str, str, str], O0Observation] = {}
        for observation in case.formal.observations:
            if observation.bridge_key is None or observation.bridge_value is None:
                continue
            if observation.quality in excluded:
                continue
            formal_index[
                (
                    observation.family,
                    observation.subject_ref,
                    observation.bridge_key,
                    observation.bridge_value,
                )
            ] = observation

        for observation in case.runtime.observations:
            if observation.bridge_key is None or observation.bridge_value is None:
                continue
            if observation.quality in excluded:
                continue
            formal_subject = case.runtime_to_formal_ids.get(observation.subject_ref)
            if formal_subject is None:
                continue
            lookup = (
                observation.family,
                formal_subject,
                observation.bridge_key,
                observation.bridge_value,
            )
            if lookup not in formal_index:
                continue
            key = (observation.family, observation.bridge_key)
            counts[key] = counts.get(key, 0) + 1

    return [
        B0Coordinate(
            key=f"{family}:{bridge_key}",
            family=family,
            bridge_key=bridge_key,
            witnesses=witnesses,
        )
        for (family, bridge_key), witnesses in sorted(counts.items())
    ]
