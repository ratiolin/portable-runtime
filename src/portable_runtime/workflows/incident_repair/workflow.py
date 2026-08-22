"""IncidentRepairWorkflow: full 8-step portable workflow (hardened B)."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Sequence

from portable_runtime.core.models import Artifact, Run, Work, new_id
from portable_runtime.core.policies import (
    PolicyEngine,
    WorkflowPolicyConfig,
    build_incident_policy_context,
    create_default_incident_policy_engine,
)
from portable_runtime.records.knowledge import KnowledgeProjection
from portable_runtime.workflows.context import WorkflowContext

logger = logging.getLogger(__name__)


def _closed_verification_pass(result: object) -> bool:
    """Return the closed judgment, never an epistemic inference.

    New verifier providers expose ``verification_result`` independently from
    ``CapabilityResult.status``.  A provider execution without a closed
    judgment is not proof and therefore fails closed.
    """
    judgment = getattr(result, "verification_result", None)
    if judgment is not None:
        return getattr(judgment, "result", None) == "pass"
    return False


def _verification_policy_passes(results: Sequence[object], policy: object) -> bool:
    checks = [_closed_verification_pass(result) for result in results]
    if not checks:
        return False
    if isinstance(policy, dict):
        mode = str(policy.get("mode", "all-required"))
        threshold = int(policy.get("threshold", len(checks)))
    else:
        mode = str(policy or "all-required")
        threshold = len(checks)
    if mode == "any-of":
        return any(checks)
    if mode == "threshold":
        return sum(checks) >= threshold
    # all-required is the conservative default; callers must opt into a
    # weaker policy explicitly in Work metadata.
    return all(checks)


def _save_knowledge_projection(
    context: WorkflowContext,
    projection: KnowledgeProjection,
    run: Run,
) -> None:
    """Persist canonical knowledge, with an artifact fallback for old stores."""
    if hasattr(context.store, "save_knowledge_projection"):
        context.store.save_knowledge_projection(projection)  # type: ignore[attr-defined]
        _append_projection_event(context, projection)
        return
    artifact = Artifact(
        id=new_id("artifact"),
        kind="knowledge-projection",
        media_type="application/json",
        inline_data=projection.model_dump(mode="json"),  # type: ignore[attr-defined]
        created_by_run_id=run.id,
    )
    context.store.save_artifact(artifact)


def _append_projection_event(context: WorkflowContext, projection: KnowledgeProjection) -> None:
    store = context.store
    if not hasattr(store, "append_event") and not hasattr(store, "save_event"):
        return
    from portable_runtime.core.models import Event, new_id

    event = Event(
        id=new_id("event"),
        type="KnowledgeProjected",
        subject_ref=projection.id,
        payload={
            "lifecycle_status": projection.lifecycle_status,
            "source_work_refs": list(projection.source_work_refs),
        },
    )
    try:
        if hasattr(store, "append_event"):
            store.append_event(event)
        else:
            store.save_event(event)  # type: ignore[attr-defined]
    except Exception:
        logger.debug("knowledge projection journal append failed", exc_info=True)


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
        if context.run.status == "succeeded":
            return "succeeded"
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
            # R1.4 HOOK: human.approve must generate Decision + AuthorizationGrant, not just approved=True
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

        # 6. apply / merge.  A verifier's execution status is not its
        # proposition judgment: an executed verifier may return
        # ``status=succeeded`` with ``verification_result.result=fail``.
        # Default to all-required; an explicit work obligation may choose
        # ``any-of`` or ``threshold``.
        verification_results = [verify_http, verify_git]
        verify_ok = _verification_policy_passes(
            verification_results,
            work.metadata.get("verification_policy", "all-required"),
        )
        # Use StrictVerificationPolicy via same engine
        verification_ctx = build_incident_policy_context(
            work_id=work.id,
            work_title=work.title,
            work_metadata=dict(work.metadata) if isinstance(work.metadata, dict) else {},
            capability="verify.http",
        )
        await self._policy_engine.evaluate(verification_ctx)
        # A failed or missing closed judgment is never a successful repair,
        # regardless of whether a legacy policy requested strict verification.
        if not verify_ok:
            with contextlib.suppress(ValueError):
                context.transition_run("blocked", current_step="verify-blocked")
            return "blocked"

        # 7. persist outcome
        with contextlib.suppress(Exception):
            context.set_step("persist")
        # 8. create canonical knowledge candidate.  The runtime no longer
        # creates legacy KnowledgeItem/Evidence objects.  Existing legacy
        # records remain readable through store/compat adapters.
        try:
            from portable_runtime.records.knowledge import KnowledgeProjection
            from portable_runtime.records.models import Assertion, Derivation, EvidenceArtifact

            verification_refs: list[str] = []
            for capability, result in (("verify.http", verify_http), ("verify.git_diff", verify_git)):
                closed = getattr(result, "verification_result", None)
                evidence = EvidenceArtifact(
                    id=new_id("record"),
                    kind="closed-verification",
                    lifecycle_status="current",
                    source_refs=list(getattr(result, "output_artifact_refs", []) or []),
                    metadata={
                        "work_id": work.id,
                        "run_id": run.id,
                        "verification_scope": dict(
                            (work.metadata.get("verification_scope") if isinstance(work.metadata, dict) else {})
                            or (
                                work.constraints.get("verification_scope")
                                if isinstance(work.constraints, dict)
                                else {}
                            )
                            or {}
                        ),
                        "work_version": (
                            (work.metadata.get("work_version") if isinstance(work.metadata, dict) else None)
                            or (work.metadata.get("task_version") if isinstance(work.metadata, dict) else None)
                            or (work.metadata.get("version") if isinstance(work.metadata, dict) else None)
                            or 1
                        ),
                        "acceptance_criteria": list(work.acceptance_criteria),
                        "capability": capability,
                        "provider_id": getattr(result, "provider_id", ""),
                        "execution_status": getattr(result, "status", None),
                        "verification_result": closed.model_dump(mode="json") if closed is not None else None,
                        "message": getattr(result, "message", None),
                    },
                )
                context.store.save_record(evidence)
                verification_refs.append(evidence.id)

            assertion = Assertion(
                id=new_id("record"),
                statement=f"Repair candidate for {work.title}",
                lifecycle_status="draft",
                epistemic_status="unverified",
                source_refs=verification_refs,
                metadata={
                    "work_id": work.id,
                    "run_id": run.id,
                    "verification_execution_statuses": {
                        "verify.http": verify_http.status,
                        "verify.git_diff": verify_git.status,
                    },
                    "closed_verification_refs": verification_refs,
                },
            )
            context.store.save_record(assertion)

            derivation = Derivation(
                id=new_id("record"),
                premise_refs=[work.id],
                evidence_refs=verification_refs,
                rule_or_method_refs=["incident-repair.closed-verification"],
                conclusion_ref=assertion.id,
                provider_id="portable-runtime:incident-repair",
                domain="incident-repair",
                evaluator_version=self.version,
                lifecycle_status="current",
                metadata={
                    "run_id": run.id,
                    "verification_policy": work.metadata.get("verification_policy", "all-required"),
                },
            )
            context.store.save_record(derivation)

            projection = KnowledgeProjection(
                id=f"knowledge_projection_{run.id}",
                kind="failure-pattern",
                title=f"Repair {work.title}",
                source_work_refs=[work.id],
                current_assertion_refs=[assertion.id],
                evidence_summary_refs=verification_refs,
                validity_scope=dict(work.metadata.get("valid_scope") or {"work_id": work.id}),
                environment_bindings=dict(work.metadata.get("environment_versions") or {"runtime": "portable-runtime"}),
                reopen_conditions=list(work.metadata.get("reopen_conditions") or []),
                history_refs=[work.id, run.id],
                metadata={
                    "run_id": run.id,
                    "verification_policy": work.metadata.get("verification_policy", "all-required"),
                    "verification_execution_statuses": {
                        "verify.http": verify_http.status,
                        "verify.git_diff": verify_git.status,
                    },
                    "derivation_ref": derivation.id,
                },
            )
            _save_knowledge_projection(context, projection, run)
        except Exception:
            logger.debug("knowledge candidate creation failed", exc_info=True)

        try:
            context.complete_with_proofs(verification_refs)
        except ValueError:
            with contextlib.suppress(ValueError):
                context.transition_run("blocked", current_step="verify-proof-missing")
            return "blocked"
        return "succeeded"


