"""Generic task workflow with fail-closed objective completion semantics.

Provider invocation success is execution evidence only. A generic task is not
considered complete until an explicit objective verifier is injected and
returns a closed positive judgment.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence

from portable_runtime.core.capabilities import CapabilityResult
from portable_runtime.core.models import Run, Work
from portable_runtime.workflows.context import WorkflowContext

ObjectiveVerifier = Callable[
    [WorkflowContext, Work, Run, Sequence[CapabilityResult]],
    bool | Awaitable[bool],
]


class GenericTaskWorkflow:
    id = "generic-task"
    version = "1.0.0"

    def __init__(self, objective_verifier: ObjectiveVerifier | None = None) -> None:
        """Create a generic workflow with an optional objective verifier.

        The portable built-in has no provider-independent way to infer
        whether a free-form prompt was fulfilled. Therefore the default is to
        leave the run waiting after execution/delivery evidence is produced.
        A verifier may be supplied by a deployment or a future task-specific
        workflow; only the literal boolean ``True`` closes the objective.
        """
        self._objective_verifier = objective_verifier

    def accepts(self, work: Work) -> bool:
        """Accept only the canonical generic-task work kind.

        Generic task is a deliberately narrow fallback workflow.  Keeping the
        predicate exact prevents registration order from routing incident,
        maintenance, or future specialised work kinds through this workflow.
        """
        return work.kind == "generic-task"

    @staticmethod
    def _has_delivery_evidence(results: Sequence[CapabilityResult]) -> bool:
        """Return whether any successful invocation delivered durable refs."""
        return any(result.output_artifact_refs or result.evidence_refs for result in results)

    async def _objective_passes(
        self,
        context: WorkflowContext,
        work: Work,
        run: Run,
        results: Sequence[CapabilityResult],
    ) -> bool:
        verifier = self._objective_verifier
        if verifier is None:
            return False
        try:
            verdict = verifier(context, work, run, results)
            if inspect.isawaitable(verdict):
                verdict = await verdict
            # Do not coerce arbitrary truthy values into a closed judgment.
            return verdict is True
        except Exception:
            # An unavailable or broken verifier cannot prove the objective.
            return False

    async def run(self, context: WorkflowContext, work: Work, run: Run) -> str:
        caps = work.requested_capabilities or ["reason.generate"]
        results: list[CapabilityResult] = []
        for cap in caps:
            result = await context.invoke(cap, instruction=work.description or work.title)
            results.append(result)
            if result.status == "failed":
                return "failed"
            if result.status == "needs-input":
                return "waiting"
            if result.status == "unavailable":
                return "blocked"
            if result.status == "cancelled":
                return "cancelled"
            if result.status != "succeeded":
                # Unknown provider outcomes are not success evidence.
                return "waiting"

        # Successful transport/execution alone proves neither delivery nor
        # the natural-language objective. Keep the run non-terminal unless
        # durable delivery evidence exists and an explicit verifier closes
        # the objective.
        if not self._has_delivery_evidence(results):
            return "waiting"
        return "succeeded" if await self._objective_passes(context, work, run, results) else "waiting"
