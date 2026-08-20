"""Experiment as first-class Work/Capability — V1.7."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from portable_runtime.core.models import Work, new_id, utcnow


class ExperimentPlan(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(default_factory=lambda: new_id("exp_plan"))
    hypothesis_refs: list[str] = Field(default_factory=list)
    discriminates_between: list[str] = Field(default_factory=list)
    expected_outcomes: list[str] = Field(default_factory=list)
    risk_profile: dict[str, Any] = Field(default_factory=dict)
    execution_work_ref: str | None = None
    observation_refs: list[str] = Field(default_factory=list)
    result_interpretation_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)

def create_experiment_work(plan: ExperimentPlan, title: str = "Experiment") -> Work:
    return Work(
        id=new_id("work"),
        title=title,
        description=f"Experiment discriminates {plan.discriminates_between}",
        kind="experiment",
        metadata={"experiment_plan_id": plan.id, "hypothesis_refs": plan.hypothesis_refs, "risk_profile": plan.risk_profile},
    )

def is_low_cost_discriminative(plan: ExperimentPlan) -> bool:
    # Heuristic: low cost if discriminates at least 2 hypotheses with limited risk
    return len(plan.discriminates_between) >= 2 and plan.risk_profile.get("cost", "low") == "low"
