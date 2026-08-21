# Workflow authoring

Workflows describe *how* to do a task; they never import a concrete provider.

```python
from portable_runtime.core.models import Run, Work
from portable_runtime.workflows.context import WorkflowContext

class ReviewWorkflow:
    id = "review"
    version = "1.0.0"

    def accepts(self, work: Work) -> bool:
        return work.kind == "review"

    async def run(self, context: WorkflowContext, work: Work, run: Run) -> str:
        # input artifact -> reason.review -> report artifact
        result = await context.invoke(
            "reason.review",
            instruction=work.description,
            input_artifact_refs=work.artifact_refs,
        )
        if result.status == "succeeded":
            return "succeeded"
        if result.status == "needs-input":
            return "waiting"
        return "failed"
```

Register via HTTP or code:

```python
from portable_runtime.workflows.generic_task.workflow import GenericTaskWorkflow
# Workflows are resolved by id in /v1/work/{id}/workflow/{workflow_id}
```

Rules:

- `Workflow` only calls `context.invoke(capability, ...)` and `context.store.*`.
- Never `subprocess.run(["codex", ...])` and never `from providers.codex import ...`.
- `accepts()` filters which `Work.kind` the workflow handles; new kinds do not require Core changes.
- Workflows are restart-safe: they read `run.current_step` and are idempotent, or declare non-resumable.

Built-ins: `incident-repair` (8 steps: observe/diagnose/edit/verify/approve/merge/outcome/knowledge), `generic-task`, `daily-scan`, `knowledge-consolidation`. Add a new workflow by dropping a file under `src/portable_runtime/workflows/` and exposing it in the trigger mapping; no Core modification.

`generic-task` is deliberately fail-closed. Provider invocations with
`status="succeeded"` prove execution only; durable output/evidence references
prove delivery only. Without an explicitly injected objective verifier that
returns the literal boolean `True`, the workflow returns `waiting` rather than
terminal `succeeded`. Its `accepts()` predicate is restricted to
`Work.kind == "generic-task"`, so it cannot capture specialized work through
workflow registration order.
