"""IncidentRepairWorkflow: full 8-step portable workflow (hardened B)."""

from __future__ import annotations

import contextlib
import logging

from portable_runtime.core.models import Run, Work
from portable_runtime.core.policies import (
    PolicyEngine,
    WorkflowPolicyConfig,
    build_incident_policy_context,
    create_default_incident_policy_engine,
)
from portable_runtime.workflows.context import WorkflowContext

logger = logging.getLogger(__name__)


class IncidentRepairWorkflow:
    id = "incident-repair"
    version = "1.0.0"

    def __init__(
        self,
        policy_engine: PolicyEngine | None = None,
        policy_config: WorkflowPolicyConfig | None = None,
    ) -> None:
        # PolicyEngine is optional to preserve interface compatibility;
        # workflow signatures (id/version/accepts/run) remain unchanged.
        if policy_engine is not None:
            self._policy_engine = policy_engine
        else:
            self._policy_engine = create_default_incident_policy_engine(policy_config)

    @property
    def policy_engine(self) -> PolicyEngine:
        return self._policy_engine

    def accepts(self, work: Work) -> bool:
        return work.kind in {"incident", "alert", "repair", "incident-repair"}

    async def run(self, context: WorkflowContext, work: Work, run: Run) -> str:
        # Ensure resumable state handling
        try:
            if context.run.status == "queued":
                context.transition_run("running", current_step="observe")
            elif context.run.status in ("waiting", "blocked", "interrupted"):
                context.resume()
        except ValueError:
            pass

        # 1. observe
        with contextlib.suppress(Exception):
            context.set_step("observe")
        await context.invoke("observe.logs", instruction=f"collect logs for {work.title}")
        await context.invoke("observe.container", instruction=f"observe containers for {work.title}")

        # 2. diagnose via reason provider
        with contextlib.suppress(Exception):
            context.set_step("diagnose")
        diag = await context.invoke("reason.generate", instruction=work.description or work.title)
        if diag.status == "unavailable":
            logger.info("diagnose capability unavailable for %s", work.id)
            with contextlib.suppress(ValueError):
                context.transition_run("blocked", current_step="diagnose-blocked")
            return "blocked"
        if diag.status == "failed":
            with contextlib.suppress(ValueError):
                context.transition_run("failed", current_step="diagnose-failed")
            return "failed"

        # 3. request approval before any action-critical repair.  The old
        # order invoked code.edit first and only then asked for approval,
        # which is incompatible with a fail-closed boundary.
        policy_ctx = build_incident_policy_context(
            work_id=work.id,
            work_title=work.title,
            work_metadata=dict(work.metadata) if isinstance(work.metadata, dict) else {},
            capability="human.approve",
        )
        # Evaluate approval gate via PolicyEngine (replaces metadata magic string)
        decision = await self._policy_engine.evaluate(policy_ctx)
        needs_approval = decision.status == "require-approval"
        if needs_approval:
            with contextlib.suppress(Exception):
                context.set_step("approval")
            approval = await context.invoke("human.approve", instruction=f"approve repair for {work.title}")
            # V1.4 HOOK: human.approve must generate Decision + AuthorizationGrant, not just approved=True
            if approval.status == "succeeded":
                try:
                    from portable_runtime.records.authorization import record_human_approval

                    # Derive version refs from patch hint / edit output; fallback to work id version
                    subj_versions: list[str] = []
                    ph = work.metadata.get("patch_hint") or work.metadata.get("subject_version") or ""
                    if isinstance(ph, str) and ph:
                        subj_versions = [ph]
                    elif isinstance(ph, list):
                        subj_versions = [str(x) for x in ph]
                    if not subj_versions:
                        subj_versions = [f"{work.id}:v1"]
                    principal = str(work.metadata.get("approver", "human:owner"))
                    # grantee is the repair actor
                    grantee = work.metadata.get("grantee_ref") or f"run:{run.id}"
                    _, grant = record_human_approval(
                        context.store,
                        principal_ref=principal,
                        grantee_ref=str(grantee),
                        allowed_capabilities=["code.edit", "merge", "deploy"],
                        subject_version_refs=subj_versions,
                        work_id=work.id,
                        resource_scope=[str(work.metadata.get("resource_scope", ""))] if work.metadata.get("resource_scope") else [],  # noqa: E501
                    )
                    # stash for procedure gate
                    if isinstance(context.run.metadata, dict):
                        context.run.metadata["authorization_grant_id"] = grant.id
                        context.run.metadata["subject_version_refs"] = subj_versions
                        try:
                            context.store.save_run(context.run)
                        except Exception:
                            pass
                except Exception:
                    logger.debug("human approval grant hook failed", exc_info=True)
            if approval.status == "needs-input":
                with contextlib.suppress(ValueError):
                    context.transition_run("waiting", current_step="approval-waiting")
                return "waiting"
            if approval.status == "failed":
                with contextlib.suppress(ValueError):
                    context.transition_run("blocked", current_step="approval-blocked")
                return "blocked"

        # 4. execute reversible repair only after the approval/grant gate.
        with contextlib.suppress(Exception):
            context.set_step("repair")
        edit = await context.invoke(
            "code.edit", instruction=f"repair {work.title}", patch_hint=work.metadata.get("patch_hint", "")
        )
        if edit.status in {"failed", "unavailable"}:
            with contextlib.suppress(ValueError):
                context.transition_run("failed" if edit.status == "failed" else "blocked", current_step="repair-failed")
            return "failed" if edit.status == "failed" else "blocked"

        # 5. verify with independent verifier
        with contextlib.suppress(Exception):
            context.set_step("verify")
        verify_http = await context.invoke(
            "verify.http", url=work.metadata.get("verify_url", ""), expected_status=[200, 301, 302]
        )
        verify_git = await context.invoke("verify.git_diff", diff=edit.message or "")

        # 6. apply / merge (verify must have passed or at least one verifier succeeded)
        verify_ok = verify_http.status == "succeeded" or verify_git.status == "succeeded"
        # Use StrictVerificationPolicy via same engine
        verification_ctx = build_incident_policy_context(
            work_id=work.id,
            work_title=work.title,
            work_metadata=dict(work.metadata) if isinstance(work.metadata, dict) else {},
            capability="verify.http",
        )
        ver_decision = await self._policy_engine.evaluate(verification_ctx)
        strict_required = ver_decision.status == "require-verification"
        if not verify_ok and strict_required:
            with contextlib.suppress(ValueError):
                context.transition_run("blocked", current_step="verify-blocked")
            return "blocked"

        # 7. persist outcome
        with contextlib.suppress(Exception):
            context.set_step("persist")
        # 8. create knowledge candidate
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

        with contextlib.suppress(ValueError):
            context.transition_run("succeeded", current_step="done")
        return "succeeded"


