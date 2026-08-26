from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiProblemV1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_: Literal["api-problem-v1"] = Field("api-problem-v1", alias="schema")
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False


class ExperienceUseRequirementV1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_: Literal["experience-use-requirement-v1"] = Field(
        "experience-use-requirement-v1",
        alias="schema",
    )
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
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_: Literal["historical-experience-use-commit-v1"] = Field(
        "historical-experience-use-commit-v1",
        alias="schema",
    )
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
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_: Literal["governance-use-admission-view-v1"] = Field(
        "governance-use-admission-view-v1",
        alias="schema",
    )
    status: str
    scheme_id: str | None = None
    requirement_digest: str | None = None
    snapshot_digest: str | None = None
    reasons: list[str] = Field(default_factory=list)
    authority_bearing: Literal[False] = False


class InvocationPermitView(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_: Literal["invocation-permit-view-v1"] = Field(
        "invocation-permit-view-v1",
        alias="schema",
    )
    permit_digest: str
    provider_id: str | None = None
    qualification_digest: str | None = None
    governance_bound: bool = False
    governance_requirement_digest: str | None = None
    governance_snapshot_digest: str | None = None
    issued_at: str | None = None
    authority_bearing: Literal[False] = False


class InvocationDispatchCommittedView(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_: Literal["invocation-dispatch-committed-view-v1"] = Field(
        "invocation-dispatch-committed-view-v1",
        alias="schema",
    )
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
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_: Literal["confirmed-outcome-view-v1"] = Field(
        "confirmed-outcome-view-v1",
        alias="schema",
    )
    outcome_id: str
    action_ref: str | None = None
    status: str = "confirmed"
    verification_refs: list[str] = Field(default_factory=list)
    authority_bearing: Literal[False] = False


class RecoveryView(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_: Literal["recovery-view-v1"] = Field(
        "recovery-view-v1",
        alias="schema",
    )
    subject_ref: str
    observation: dict[str, Any] | None = None
    disposition: dict[str, Any] | None = None
    application: dict[str, Any] | None = None
    authority_bearing: Literal[False] = False
