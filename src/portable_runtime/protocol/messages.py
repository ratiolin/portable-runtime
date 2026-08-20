from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from portable_runtime.core.models import Artifact


class InvokeMessage(BaseModel):
    type: Literal["invoke"] = "invoke"
    id: str
    capability: str
    work_id: str | None = None
    run_id: str | None = None
    instruction: str | None = None
    input_artifact_refs: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ResultMessage(BaseModel):
    type: Literal["result"] = "result"
    request_id: str
    status: Literal["succeeded", "failed", "unavailable", "needs-input", "cancelled"]
    output_artifacts: list[Artifact] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    message: str | None = None
    error: dict[str, Any] | None = None
