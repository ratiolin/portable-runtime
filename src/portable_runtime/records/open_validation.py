"""Open vs Closed validation — V1.7."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OpenResult = Literal["supports", "weakens", "discriminates", "inconclusive", "scope-limited", "structure-questioned"]
ClosedResult = Literal["pass", "fail"]

class OpenValidationResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    result: OpenResult
    affected_assertion_refs: list[str] = Field(default_factory=list)
    counterevidence_refs: list[str] = Field(default_factory=list)
    suggested_revision_scope: str | None = None
    known_limitations: list[str] = Field(default_factory=list)
    message: str | None = None

class ClosedVerificationResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    result: ClosedResult
    artifact_refs: list[str] = Field(default_factory=list)
    message: str | None = None

def closed_verify_http(status_code: int, expected: list[int] | None = None) -> ClosedVerificationResult:
    exp = expected or [200]
    if status_code in exp:
        return ClosedVerificationResult(result="pass", message=f"status {status_code} in {exp}")
    return ClosedVerificationResult(result="fail", message=f"status {status_code} not in {exp}")

def open_validate(proposed_structure: str, evidence: list[str], counter: list[str]) -> OpenValidationResult:
    if counter:
        return OpenValidationResult(result="weakens", counterevidence_refs=counter, suggested_revision_scope="representation")
    if not evidence:
        return OpenValidationResult(result="inconclusive", known_limitations=["no evidence"])
    return OpenValidationResult(result="supports", affected_assertion_refs=[proposed_structure])
