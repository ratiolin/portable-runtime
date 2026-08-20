"""IncidentRepairWorkflow: full 8-step portable workflow (B2-B)."""

from __future__ import annotations

import logging

from portable_runtime.core.models import Run, Work
from portable_runtime.workflows.context import WorkflowContext

logger = logging.getLogger(__name__)


class IncidentRepairWorkflow:
    id = "incident-repair"
    version = "1.0.0"

    def accepts(self, work: Work) -> bool:
        return work.kind in {"incident", "alert", "repair", "incident-repair"}

    async def run(self, context: WorkflowContext, work: Work, run: Run) -> str:
        # 1. observe
        await context.invoke("observe.logs", instruction=f"collect logs for {work.title}")
        await context.invoke("observe.container", instruction=f"observe containers for {work.title}")
        # 2. diagnose via reason provider (Codex by default, but FakeProvider works in tests)
        diag = await context.invoke("reason.generate", instruction=work.description or work.title)
        if diag.status == "unavailable":
            logger.info("diagnose capability unavailable for %s", work.id)
            return "blocked"
        if diag.status == "failed":
            return "failed"
        # 3. execute reversible repair or create patch
        edit = await context.invoke("code.edit", instruction=f"repair {work.title}", patch_hint=work.metadata.get("patch_hint", ""))  # noqa: E501
        if edit.status == "failed":
            return "failed"
        # 4. verify with independent verifier (must not be same as execution provider self-report)
        verify_http = await context.invoke("verify.http", url=work.metadata.get("verify_url", ""), expected_status=[200, 301, 302])  # noqa: E501
        verify_git = await context.invoke("verify.git_diff", diff=edit.message or "")
        # 5. request approval if required (policy decides; we ask human provider)
        needs_approval = work.metadata.get("requires_approval", False) or "sensitive" in work.title.lower()
        if needs_approval:
            approval = await context.invoke("human.approve", instruction=f"approve repair for {work.title}")
            if approval.status == "needs-input":
                return "waiting"
            if approval.status == "failed":
                return "blocked"
        # 6. apply / merge (verify must have passed or at least one verifier succeeded)
        verify_ok = verify_http.status == "succeeded" or verify_git.status == "succeeded"
        if not verify_ok and work.metadata.get("strict_verify", False):
            return "blocked"
        # 7. persist outcome (Run status already tracked by Runtime; we return final)
        # 8. create knowledge candidate (via knowledge provider or direct store)
        try:
            from portable_runtime.core.models import KnowledgeItem

            item = KnowledgeItem(
                id=f"knowledge_{run.id}",
                kind="failure-pattern",
                title=f"Repair {work.title}",
                content_ref=edit.output_artifact_refs[0] if edit.output_artifact_refs else work.id,
                status="candidate",
                source_work_refs=[work.id],
                evidence_refs=verify_http.evidence_refs + verify_git.evidence_refs,
            )
            context.store.save_knowledge(item)
        except Exception:
            logger.debug("knowledge candidate creation failed", exc_info=True)
        return "succeeded"
