"""KnowledgeProjection — V1.5 Selective Consolidation.

Replaces KnowledgeItem=truth object with derived projection view.
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
    current_assertion_refs: list[str] = Field(default_factory=list)
    evidence_summary_refs: list[str] = Field(default_factory=list)
    validity_scope: dict[str, Any] = Field(default_factory=dict)
    environment_bindings: dict[str, str] = Field(default_factory=dict)
    counterexample_refs: list[str] = Field(default_factory=list)
    negative_knowledge_refs: list[str] = Field(default_factory=list)
    reopen_conditions: list[str] = Field(default_factory=list)
    usage_refs: list[str] = Field(default_factory=list)
    history_refs: list[str] = Field(default_factory=list)
    lifecycle_status: Literal["candidate", "official", "deprecated", "archived"] = "candidate"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    maturity: dict[Maturity, str] = Field(default_factory=dict)

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
