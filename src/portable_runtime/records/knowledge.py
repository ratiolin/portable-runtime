"""KnowledgeProjection — R1.5 implementation milestone.

Replaces KnowledgeItem=truth object with derived projection view.
Promotion to official is fail-closed: requires explicit epistemic judgment refs
+ authorization/governance refs + validity_scope (scope) + environment version context.
Evidence existence alone MUST NOT imply official.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from portable_runtime.core.models import new_id, utcnow

Maturity = Literal["Compression", "Prediction", "Transfer", "Intervention", "Boundary"]

class KnowledgeProjection(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: new_id("knowledge_proj"))
    kind: str = "projection"
    title: str = ""
    source_work_refs: list[str] = Field(default_factory=list)
    current_assertion_refs: list[str] = Field(default_factory=list)
    evidence_summary_refs: list[str] = Field(default_factory=list)
    validity_scope: dict[str, Any] = Field(default_factory=dict)
    environment_bindings: dict[str, str] = Field(default_factory=dict)
    counterexample_refs: list[str] = Field(default_factory=list)
    negative_knowledge_refs: list[str] = Field(default_factory=list)
    reopen_conditions: list[str] = Field(default_factory=list)
    usage_refs: list[str] = Field(default_factory=list)
    history_refs: list[str] = Field(default_factory=list)
    # P0-3 explicit promotion prerequisites (fail-closed):
    epistemic_judgment_refs: list[str] = Field(default_factory=list, description="explicit epistemic judgment refs")
    authorization_refs: list[str] = Field(default_factory=list, description="governance/authorization refs")
    scope_version_refs: list[str] = Field(default_factory=list, description="version context refs")
    lifecycle_status: Literal["candidate", "official", "deprecated", "archived"] = "candidate"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    maturity: dict[Maturity, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def status(self) -> str:
        """Read-only legacy spelling; canonical state is lifecycle_status."""
        return self.lifecycle_status

def is_negative_knowledge(proj: KnowledgeProjection) -> bool:
    return bool(proj.counterexample_refs or proj.negative_knowledge_refs)

def consolidate(projections: list[KnowledgeProjection], new_assertions: list[str], counterexamples: list[str]) -> KnowledgeProjection:
    """Selective consolidation — never drops counterexamples."""
    all_counters = set()
    for p in projections:
        all_counters.update(p.counterexample_refs)
        all_counters.update(p.negative_knowledge_refs)
    all_counters.update(counterexamples)
    return KnowledgeProjection(
        current_assertion_refs=new_assertions,
        evidence_summary_refs=[],
        counterexample_refs=sorted(all_counters),
        lifecycle_status="candidate",
    )


def validate_projection_for_official(proj: KnowledgeProjection) -> list[str]:
    """Validate promotion prerequisites — evidence alone does NOT imply official."""
    errors: list[str] = []
    if not proj.current_assertion_refs:
        errors.append("current_assertion_refs required for official")
    if not proj.epistemic_judgment_refs:
        errors.append("epistemic_judgment_refs required (explicit judgment, not evidence existence)")
    if not proj.authorization_refs:
        errors.append("authorization_refs required (governance/approval)")
    if not isinstance(proj.validity_scope, dict) or not proj.validity_scope:
        errors.append("validity_scope required non-empty scope for official")
    if not isinstance(proj.environment_bindings, dict) or not proj.environment_bindings:
        errors.append("environment_bindings required non-empty version context for official")
    # also require evidence summary refs? keep strict but not block legacy empty — require at least assertion present
    return errors


def can_promote_to_official(proj: KnowledgeProjection) -> bool:
    return not validate_projection_for_official(proj)


def promote_to_official(proj: KnowledgeProjection) -> KnowledgeProjection:
    """Promote to official only if explicit judgment + authorization + scope + version present. Fail-closed."""
    errs = validate_projection_for_official(proj)
    if errs:
        raise ValueError("cannot promote to official: " + "; ".join(errs))
    if proj.lifecycle_status not in ("candidate", "official"):
        raise ValueError(f"cannot promote from status {proj.lifecycle_status!r}")
    return proj.model_copy(update={"lifecycle_status": "official", "updated_at": utcnow()})
