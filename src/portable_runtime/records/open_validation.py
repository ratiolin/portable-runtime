"""Open vs Closed validation — V1.8 strict (P0-3).

Runtime does NOT synthesize epistemic judgment. OpenValidationResult is a
record of an *external* judgment; Runtime only validates schema / refs / scope.

Closed verification remains a check of predetermined criteria (e.g. HTTP).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OpenResult = Literal["supports", "weakens", "discriminates", "inconclusive", "scope-limited", "structure-questioned"]
ClosedResult = Literal["pass", "fail"]

_ALLOWED_OPEN: set[str] = {
    "supports",
    "weakens",
    "discriminates",
    "inconclusive",
    "scope-limited",
    "structure-questioned",
}


class OpenValidationResult(BaseModel):
    """Result RECORDING contract — not a computation.

    Required (hard boundary, fail-closed):
      - judgment (or result alias) in ALLOWED_OPEN
      - provider_id: non-empty — who judged
      - assertion_refs: non-empty — what was judged
      - evidence_refs: non-empty — on what basis
    Optional:
      - scope: dict with explicit bounds
      - reason_artifact_refs: supporting artifacts
      - counterevidence_refs, suggested_revision_scope, known_limitations, message
    Legacy aliases (read-compat):
      - affected_assertion_refs <-> assertion_refs
      - result <-> judgment
    Runtime only validates; it never computes supports/weakens.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # judgment is canonical; result is legacy alias kept for backward read compat
    judgment: OpenResult | None = Field(default=None, description="external judgment")
    result: OpenResult | None = Field(default=None, description="legacy alias for judgment")
    provider_id: str = Field(description="external provider that produced judgment")
    assertion_refs: list[str] = Field(default_factory=list, description="assertions judged")
    affected_assertion_refs: list[str] = Field(default_factory=list, description="legacy alias for assertion_refs")
    evidence_refs: list[str] = Field(default_factory=list, description="evidence backing judgment")
    counterevidence_refs: list[str] = Field(default_factory=list)
    reason_artifact_refs: list[str] = Field(default_factory=list)
    scope: dict[str, Any] | None = Field(default=None, description="explicit scope bounds")
    suggested_revision_scope: str | None = None
    known_limitations: list[str] = Field(default_factory=list)
    message: str | None = None
    # provenance / version binding (optional but validated if present)
    environment_versions: dict[str, str] | None = None

    @model_validator(mode="after")
    def _check_required(self) -> OpenValidationResult:
        # sync judgment <-> result
        if self.judgment is None and self.result is not None:
            self.judgment = self.result  # type: ignore[assignment]
        if self.result is None and self.judgment is not None:
            self.result = self.judgment  # type: ignore[assignment]
        # merge assertion refs aliases
        if not self.assertion_refs and self.affected_assertion_refs:
            self.assertion_refs = list(self.affected_assertion_refs)
        if self.assertion_refs and not self.affected_assertion_refs:
            self.affected_assertion_refs = list(self.assertion_refs)
        # hard boundaries — fail closed
        if self.judgment is None or self.judgment not in _ALLOWED_OPEN:
            raise ValueError(f"judgment/result required and must be one of {sorted(_ALLOWED_OPEN)}")
        if not isinstance(self.provider_id, str) or not self.provider_id.strip():
            raise ValueError("provider_id required and must be non-empty")
        if not isinstance(self.assertion_refs, list) or not self.assertion_refs or any(not isinstance(x, str) or not x.strip() for x in self.assertion_refs):
            raise ValueError("assertion_refs required non-empty list of non-empty strings")
        if not isinstance(self.evidence_refs, list) or not self.evidence_refs or any(not isinstance(x, str) or not x.strip() for x in self.evidence_refs):
            raise ValueError("evidence_refs required non-empty list of non-empty strings")
        if self.scope is not None and not isinstance(self.scope, dict):
            raise ValueError("scope must be a dict when provided")
        # keep aliases consistent
        self.result = self.judgment
        self.affected_assertion_refs = list(self.assertion_refs)
        return self


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


def validate_open_validation_result(result: OpenValidationResult | dict[str, Any]) -> list[str]:
    """Runtime-side validation: schema / refs / scope only — never judgment synthesis.

    Returns list of error strings; empty means valid.
    """
    errors: list[str] = []
    try:
        if isinstance(result, dict):
            # allow raw dict; will trigger model validation
            OpenValidationResult.model_validate(result)
        elif isinstance(result, OpenValidationResult):
            # re-validate to catch missing refs (model already validates on construction,
            # but allow explicit re-check for dict-origin instances with extra="allow")
            OpenValidationResult.model_validate(result.model_dump())
        else:
            errors.append("OpenValidationResult must be dict or OpenValidationResult")
    except Exception as exc:  # noqa: BLE001
        # pydantic validation error — surface as string
        errors.append(str(exc))
    return errors


def open_validate(
    judgment: OpenResult | OpenValidationResult | dict[str, Any] | None = None,
    *,
    assertion_refs: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    provider_id: str | None = None,
    scope: dict[str, Any] | None = None,
    reason_artifact_refs: list[str] | None = None,
    counterevidence_refs: list[str] | None = None,
    suggested_revision_scope: str | None = None,
    known_limitations: list[str] | None = None,
    message: str | None = None,
    result: OpenValidationResult | dict[str, Any] | None = None,
    # legacy positional compat is intentionally NOT provided — caller must use explicit judgment contract
    **_deprecated: Any,
) -> OpenValidationResult:
    """Record an external open-validation judgment.

    This function does NOT infer supports/weakens. It only validates that the
    caller-supplied judgment record has required refs/scope/provider and returns
    the validated record. Any auto-inference ``proposed_structure/evidence/counter``
    path has been removed per P0-3.

    Accepted forms:
      open_validate(judgment="supports", assertion_refs=[...], evidence_refs=[...], provider_id="...")
      open_validate(OpenValidationResult(...))
      open_validate({"judgment": "...", "provider_id": "...", ...})
    """
    # Direct record path
    if isinstance(judgment, OpenValidationResult):
        # validate and return
        errs = validate_open_validation_result(judgment)
        if errs:
            raise ValueError("; ".join(errs))
        return judgment
    if isinstance(judgment, dict):
        # treat as raw record dict
        errs = validate_open_validation_result(judgment)
        if errs:
            raise ValueError("; ".join(errs))
        return OpenValidationResult.model_validate(judgment)
    if isinstance(result, (OpenValidationResult, dict)):
        # explicit result= alias
        target: Any = result
        if isinstance(target, dict):
            errs = validate_open_validation_result(target)
            if errs:
                raise ValueError("; ".join(errs))
            return OpenValidationResult.model_validate(target)
        errs = validate_open_validation_result(target)
        if errs:
            raise ValueError("; ".join(errs))
        return target

    # If judgment is still an OpenResult literal, construct from kwargs
    if isinstance(judgment, str):
        if _deprecated:
            raise ValueError("open_validate no longer accepts evidence/counter auto-inference; provide explicit judgment + assertion_refs + evidence_refs + provider_id")
        if judgment not in _ALLOWED_OPEN:
            raise ValueError(f"judgment must be one of {sorted(_ALLOWED_OPEN)}")
        if assertion_refs is None or evidence_refs is None or provider_id is None:
            raise ValueError("open_validate requires judgment + assertion_refs + evidence_refs + provider_id (all non-empty)")
        payload: dict[str, Any] = {
            "judgment": judgment,
            "assertion_refs": assertion_refs,
            "evidence_refs": evidence_refs,
            "provider_id": provider_id,
        }
        if scope is not None:
            payload["scope"] = scope
        if reason_artifact_refs is not None:
            payload["reason_artifact_refs"] = reason_artifact_refs
        if counterevidence_refs is not None:
            payload["counterevidence_refs"] = counterevidence_refs
        if suggested_revision_scope is not None:
            payload["suggested_revision_scope"] = suggested_revision_scope
        if known_limitations is not None:
            payload["known_limitations"] = known_limitations
        if message is not None:
            payload["message"] = message
        errs = validate_open_validation_result(payload)
        if errs:
            raise ValueError("; ".join(errs))
        return OpenValidationResult.model_validate(payload)

    # No valid calling convention
    if _deprecated or assertion_refs is not None or evidence_refs is not None or provider_id is not None:
        raise ValueError("open_validate no longer synthesizes judgment; provide explicit judgment + assertion_refs + evidence_refs + provider_id or an OpenValidationResult")
    raise ValueError("open_validate requires judgment + assertion_refs + evidence_refs + provider_id or an OpenValidationResult dict/instance")
