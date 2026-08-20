"""Generic task workflow: routes any Work with requested_capabilities through router."""

from __future__ import annotations

from portable_runtime.core.models import Run, Work
from portable_runtime.workflows.context import WorkflowContext


class GenericTaskWorkflow:
    id = "generic-task"
    version = "1.0.0"

    def accepts(self, work: Work) -> bool:
        return True

    async def run(self, context: WorkflowContext, work: Work, run: Run) -> str:
        caps = work.requested_capabilities or ["reason.generate"]
        for cap in caps:
            result = await context.invoke(cap, instruction=work.description or work.title)
            if result.status == "failed":
                return "failed"
            if result.status == "needs-input":
                return "waiting"
            if result.status == "unavailable":
                return "blocked"
        return "succeeded"
