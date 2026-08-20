"""Daily scan / knowledge consolidation placeholders (B2)."""

from __future__ import annotations

from portable_runtime.core.models import Run, Work
from portable_runtime.workflows.context import WorkflowContext


class DailyScanWorkflow:
    id = "daily-scan"
    version = "1.0.0"

    def accepts(self, work: Work) -> bool:
        return work.kind == "maintenance-scan"

    async def run(self, context: WorkflowContext, work: Work, run: Run) -> str:
        await context.invoke("observe.container", instruction="scan containers")
        await context.invoke("verify.promql", instruction="scan promql")
        return "succeeded"


class KnowledgeConsolidationWorkflow:
    id = "knowledge-consolidation"
    version = "1.0.0"

    def accepts(self, work: Work) -> bool:
        return work.kind == "knowledge-consolidation"

    async def run(self, context: WorkflowContext, work: Work, run: Run) -> str:
        # Placeholder: promote candidates
        return "succeeded"
