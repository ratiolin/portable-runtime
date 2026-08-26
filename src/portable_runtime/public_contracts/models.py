from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiProblemV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["api-problem-v1"] = "api-problem-v1"
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False


class ExperienceUseRequirementV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["experience-use-requirement-v1"] = "experience-use-requirement-v1"
    projection_refs: list[str] = Field(default_factory=list)
    use_scope: dict[str, Any] = Field(default_factory=dict)
    subject_version_refs: list[str] = Field(default_factory=list)
    environment_bindings: dict[str, str] = Field(default_factory=dict)
    use_context: dict[str, Any] = Field(default_factory=dict)


class ExperienceUseAdmissionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    admission_contract_version: Literal["experience-use-admission-v1"] = "experience-use-admission-v1"
    status: Literal["not-applicable", "allowed", "blocked", "stale", "unavailable"]
    requirement_digest: str
    snapshot_digest: str
    resolved_snapshot: dict[str, Any]
    reasons: list[str] = Field(default_factory=list)


class HistoricalExperienceUseCommitV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["historical-experience-use-commit-v1"] = "historical-experience-use-commit-v1"
    judgment: dict[str, Any]
    requirement: ExperienceUseRequirementV1
    expected_requirement_digest: str
    expected_snapshot_digest: str
    expected_admission_contract_version: str | None = None


class HistoricalExperienceUseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    judgment_ref: str
    judgment_version: int
    requirement_digest: str
    snapshot_digest: str
    snapshot_semantic_json: str
    selected_projection_refs: list[str]
    admission_contract_version: str


class GovernanceUseAdmissionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["governance-use-admission-view-v1"] = "governance-use-admission-view-v1"
    status: str
    scheme_id: str | None = None
    requirement_digest: str | None = None
    snapshot_digest: str | None = None
    reasons: list[str] = Field(default_factory=list)
    authority_bearing: Literal[False] = False


class InvocationPermitView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["invocation-permit-view-v1"] = "invocation-permit-view-v1"
    permit_digest: str
    provider_id: str | None = None
    qualification_digest: str | None = None
    governance_bound: bool = False
    governance_requirement_digest: str | None = None
    governance_snapshot_digest: str | None = None
    issued_at: str | None = None
    authority_bearing: Literal[False] = False


class InvocationDispatchCommittedView(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema: Literal["invocation-dispatch-committed-view-v1"] = "invocation-dispatch-committed-view-v1"
    event_id: str
    request_id: str | None = None
    provider_id: str | None = None
    attempt_id: str | None = None
    permit_digest: str | None = None
    qualification_digest: str | None = None
    governance_requirement_digest: str | None = None
    governance_snapshot_digest: str | None = None
    authority_bearing: Literal[False] = False


class ConfirmedOutcomeView(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema: Literal["confirmed-outcome-view-v1"] = "confirmed-outcome-view-v1"
    outcome_id: str
    action_ref: str | None = None
    status: str = "confirmed"
    verification_refs: list[str] = Field(default_factory=list)
    authority_bearing: Literal[False] = False


class RecoveryView(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema: Literal["recovery-view-v1"] = "recovery-view-v1"
    subject_ref: str
    observation: dict[str, Any] | None = None
    disposition: dict[str, Any] | None = None
    application: dict[str, Any] | None = None
    authority_bearing: Literal[False] = False
