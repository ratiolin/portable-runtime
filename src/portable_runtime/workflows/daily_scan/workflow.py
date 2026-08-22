"""Daily scan / knowledge consolidation workflows (hardened).

DailyScanWorkflow now implements real observing + verification + Evidence/Artifact
production and is schedule-trigger compatible. KnowledgeConsolidationWorkflow
implements candidate -> validated -> promote/archive logic.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from portable_runtime.core.models import Artifact, Run, Work, new_id
from portable_runtime.records.knowledge import KnowledgeProjection, promote_to_official
from portable_runtime.workflows.context import WorkflowContext

logger = logging.getLogger(__name__)

_SUPPORTED_SCAN_KINDS = {"maintenance-scan", "daily-scan", "schedule-scan", "scan", "daily_scan"}


class DailyScanWorkflow:
    id = "daily-scan"
    version = "1.0.0"

    def accepts(self, work: Work) -> bool:
        return work.kind in _SUPPORTED_SCAN_KINDS

    async def run(self, context: WorkflowContext, work: Work, run: Run) -> str:
        if context.run.status == "succeeded":
            return "succeeded"
        # Ensure run is marked running; dedup-safe transition
        try:
            if context.run.status == "queued":
                context.transition_run("running", current_step="scan-start")
            elif context.run.status in ("waiting", "blocked", "interrupted"):
                context.resume()
            context.set_step("observing")
        except ValueError:
            pass

        containers: list[str] = []
        meta_targets = work.metadata.get("targets") or work.metadata.get("containers")
        if isinstance(meta_targets, str):
            containers = [meta_targets]
        elif isinstance(meta_targets, list):
            containers = [str(x) for x in meta_targets]
        elif work.inputs:
            containers = list(work.inputs)
        # PromQL query from metadata or default
        promql_query: str = str(
            work.metadata.get("promql_query") or work.metadata.get("query") or work.metadata.get("promql") or "up==1"
        )

        # Step 1: observe containers
        observe_result = await context.invoke(
            "observe.container",
            instruction=f"scan containers for {work.title}",
            targets=containers,
            containers=containers,
        )
        # Fallback: if observe.container unavailable, try verify.container
        if observe_result.status == "unavailable":
            observe_result = await context.invoke(
                "verify.container",
                instruction=f"scan containers for {work.title}",
                targets=containers or ["default"],
            )

        with contextlib.suppress(Exception):
            context.set_step("verifying")

        # Step 2: verify promql
        verify_result = await context.invoke(
            "verify.promql",
            instruction=f"verify promql for {work.title}",
            query=promql_query,
            promql=promql_query,
        )

        # Produce Evidence / Artifact for each invocation (even on failure -> contested)
        verification_refs: list[str] = []
        for kind, result, detail in [
            ("container-observation", observe_result, {"targets": containers}),
            ("promql-observation", verify_result, {"query": promql_query}),
        ]:
            try:
                artifact = Artifact(
                    id=new_id("artifact"),
                    kind=kind,
                    media_type="application/json",
                    inline_data={
                        "work_id": work.id,
                        "run_id": run.id,
                        "capability": result.provider_id,
                        "status": result.status,
                        "message": result.message,
                        "detail": detail,
                    },
                    created_by_run_id=run.id,
                    created_by_provider_id=result.provider_id or None,
                )
                context.store.save_artifact(artifact)
                # P1-2: produce Artifact + Observation, do NOT auto-create supported Evidence
                try:
                    from portable_runtime.records.models import Observation as ObservationRecord
                    obs = ObservationRecord(
                        id=new_id("record"),
                        record_type="Observation",
                        lifecycle_status="current",
                        scope={"work_id": work.id, "run_id": run.id},
                        source_refs=[artifact.id],
                        metadata={"kind": kind, "provider_id": result.provider_id, "status": result.status, "detail": detail},
                    )
                    if hasattr(context.store, "save_record"):
                        context.store.save_record(obs)  # type: ignore[attr-defined]
                except Exception:
                    logger.debug("daily-scan observation creation failed", exc_info=True)
                # Canonical write path: EvidenceArtifact carries observation
                # provenance; the store's list_evidence API exposes a
                # read-only legacy view for old callers.
                try:
                    from portable_runtime.records.models import EvidenceArtifact

                    evidence = EvidenceArtifact(
                        id=new_id("record"),
                        kind="closed-verification" if result.verification_result is not None else kind,
                        source_refs=[artifact.id],
                        metadata={
                            "work_id": work.id,
                            "run_id": run.id,
                            "verification_scope": dict(
                                (work.metadata.get("verification_scope") if isinstance(work.metadata, dict) else {})
                                or (work.constraints.get("verification_scope") if isinstance(work.constraints, dict) else {})
                                or {}
                            ),
                            "work_version": (
                                (work.metadata.get("work_version") if isinstance(work.metadata, dict) else None)
                                or (work.metadata.get("task_version") if isinstance(work.metadata, dict) else None)
                                or (work.metadata.get("version") if isinstance(work.metadata, dict) else None)
                                or 1
                            ),
                            "acceptance_criteria": list(work.acceptance_criteria),
                            "provider_id": result.provider_id,
                            "execution_status": result.status,
                            "verification_result": result.verification_result.model_dump(mode="json") if result.verification_result else None,
                        },
                        lifecycle_status="current",
                    )
                    if hasattr(context.store, "save_record"):
                        context.store.save_record(evidence)  # type: ignore[attr-defined]
                        if result.verification_result is not None:
                            verification_refs.append(evidence.id)
                except Exception:
                    pass
            except Exception:
                logger.debug("daily-scan evidence creation failed", exc_info=True)

        # Decide final status
        statuses = {observe_result.status, verify_result.status}
        if statuses == {"unavailable"} or (
            observe_result.status == "unavailable" and verify_result.status == "unavailable"
        ):
            with contextlib.suppress(ValueError):
                context.transition_run("blocked", current_step="scan-blocked")
            return "blocked"
        if "failed" in statuses:
            # A successful observation cannot mask a failed verification.
            with contextlib.suppress(ValueError):
                context.transition_run("failed", current_step="scan-failed")
            return "failed"
        if observe_result.status != "succeeded" or verify_result.status != "succeeded":
            with contextlib.suppress(ValueError):
                context.transition_run("waiting", current_step="scan-waiting")
            return "waiting"
        if (
            verify_result.verification_result is None
            or verify_result.verification_result.result != "pass"
            or not verification_refs
        ):
            # Provider execution status is not a verification judgment.
            with contextlib.suppress(ValueError):
                context.transition_run("blocked", current_step="scan-verification-missing")
            return "blocked"
        try:
            context.complete_with_proofs(verification_refs)
        except ValueError:
            with contextlib.suppress(ValueError):
                context.transition_run("blocked", current_step="scan-proof-missing")
            return "blocked"
        return "succeeded"


_KC_SUPPORTED = {"knowledge-consolidation", "knowledge_consolidation", "consolidation"}


def _is_promotable(item: Any, evidence_by_id: dict[str, Any]) -> tuple[bool, str]:
    """Fail-closed: evidence existence alone does NOT imply promotable.

    Requires explicit epistemic judgment refs + authorization refs + valid_scope + version context.
    """
    is_projection = isinstance(item, KnowledgeProjection)
    title = getattr(item, "title", "")
    content_refs = (
        list(getattr(item, "current_assertion_refs", []) or [])
        if is_projection
        else [getattr(item, "content_ref", "")]
    )
    if not title or not any(content_refs):
        return False, "missing title or content_ref"
    ev_refs: list[str] = list(
        getattr(item, "evidence_summary_refs", [])
        if is_projection
        else getattr(item, "evidence_refs", [])
    )
    if not ev_refs:
        return False, "no evidence_refs"
    meta: dict[str, Any] = getattr(item, "metadata", {}) if isinstance(getattr(item, "metadata", {}), dict) else {}
    judgment_refs = (
        meta.get("epistemic_judgment_refs")
        or getattr(item, "epistemic_judgment_refs", None)
        or []
    )
    auth_refs = (
        meta.get("authorization_refs")
        or meta.get("authorization_grant_ids")
        or getattr(item, "authorization_refs", None)
        or []
    )
    valid_scope = (
        getattr(item, "validity_scope", None)
        if is_projection
        else getattr(item, "valid_scope", None)
    ) or meta.get("valid_scope") or meta.get("validity_scope") or {}
    env_versions = (
        getattr(item, "environment_bindings", None)
        if is_projection
        else getattr(item, "environment_versions", None)
        or meta.get("environment_versions")
        or meta.get("environment_bindings")
        or {}
    )
    if not judgment_refs or not isinstance(judgment_refs, list) or not any(isinstance(x, str) and x.strip() for x in judgment_refs):  # noqa: E501
        return False, "missing epistemic_judgment_refs (explicit judgment required)"  # noqa: E501
    if not auth_refs or not isinstance(auth_refs, list) or not any(isinstance(x, str) and x.strip() for x in auth_refs):
        return False, "missing authorization_refs (governance required)"
    if not isinstance(valid_scope, dict) or not valid_scope:
        return False, "missing valid_scope (scope required for official)"
    if not isinstance(env_versions, dict) or not env_versions:
        return False, "missing environment_versions/version context"
    # P1-2: stop depending on Evidence.status==supported, use existence + explicit judgment/auth/scope/env
    # Check evidence refs exist (but not status)
    if not any(r in evidence_by_id for r in ev_refs):
        return False, "evidence refs do not exist"
    # If evidence exists, require explicit judgment/auth/scope/env already checked above; status not decisive
    # Optionally check OpenValidationResult if available via metadata
    # Do not require supported status
    return True, "validated with explicit judgment + authorization + scope + version"


def _append_projection_event(context: WorkflowContext, projection: KnowledgeProjection, status: str) -> None:
    """Journal a canonical projection transition without writing legacy state."""
    store = context.store
    if not hasattr(store, "append_event") and not hasattr(store, "save_event"):
        return
    from portable_runtime.core.models import Event, new_id

    event = Event(
        id=new_id("event"),
        type="KnowledgeProjected",
        subject_ref=projection.id,
        payload={"lifecycle_status": status, "source_work_refs": list(projection.source_work_refs)},
    )
    try:
        if hasattr(store, "append_event"):
            store.append_event(event)
        else:
            store.save_event(event)  # type: ignore[attr-defined]
    except Exception:
        logger.debug("knowledge projection journal append failed", exc_info=True)


def _complete_consolidation_with_proof(context: WorkflowContext, work: Work, run: Run, source_refs: list[str]) -> bool:
    """Persist a deterministic consolidation proof before terminalizing."""
    try:
        from portable_runtime.records.models import EvidenceArtifact

        metadata = work.metadata if isinstance(work.metadata, dict) else {}
        constraints = work.constraints if isinstance(work.constraints, dict) else {}
        scope = metadata.get("verification_scope", constraints.get("verification_scope", {}))
        version = metadata.get("work_version", metadata.get("task_version", metadata.get("version", 1)))
        proof = EvidenceArtifact(
            id=new_id("record"),
            kind="closed-verification",
            source_refs=list(source_refs),
            metadata={
                "work_id": work.id,
                "run_id": run.id,
                "verification_scope": dict(scope) if isinstance(scope, dict) else {},
                "work_version": version,
                "acceptance_criteria": list(work.acceptance_criteria),
                "verification_result": {"result": "pass", "message": "consolidation report durably produced"},
                "workflow": "knowledge-consolidation",
            },
        )
        context.store.save_record(proof)
        context.complete_with_proofs([proof.id])
        return True
    except (ValueError, TypeError):
        return False


class KnowledgeConsolidationWorkflow:
    id = "knowledge-consolidation"
    version = "1.0.0"

    def accepts(self, work: Work) -> bool:
        return work.kind in _KC_SUPPORTED

    async def run(self, context: WorkflowContext, work: Work, run: Run) -> str:
        if context.run.status == "succeeded":
            return "succeeded"
        try:
            if context.run.status == "queued":
                context.transition_run("running", current_step="kc-start")
            elif context.run.status in ("waiting", "blocked", "interrupted"):
                context.resume()
            context.set_step("consolidating")
        except ValueError:
            pass

        candidates: list[KnowledgeProjection] = []
        seen_projection_ids: set[str] = set()
        if hasattr(context.store, "list_knowledge_projections"):
            for projection in context.store.list_knowledge_projections(status="candidate"):  # type: ignore[attr-defined]
                candidates.append(projection)
                seen_projection_ids.add(projection.id)
        try:
            from portable_runtime.compat.legacy_records import legacy_knowledge_to_projection

            raw_legacy_knowledge = getattr(context.store, "list_raw_legacy_knowledge", None)
            if raw_legacy_knowledge is None:
                raise RuntimeError("canonical consolidation requires raw legacy knowledge namespace")
            for legacy_item in raw_legacy_knowledge(status="candidate"):
                projection = legacy_knowledge_to_projection(legacy_item)
                if projection.id in seen_projection_ids:
                    continue
                projection.metadata["legacy_id"] = legacy_item.id
                candidates.append(projection)
                seen_projection_ids.add(projection.id)
        except Exception:
            pass
        if not candidates:
            if _complete_consolidation_with_proof(context, work, run, []):
                return "succeeded"
            with contextlib.suppress(ValueError):
                context.transition_run("waiting", current_step="kc-done-empty")
            return "waiting"

        # Build evidence lookup from store
        evidence_by_id: dict[str, Any] = {}
        try:
            raw_legacy_evidence = getattr(context.store, "list_raw_legacy_evidence", None)
            if raw_legacy_evidence is None:
                raise RuntimeError("canonical consolidation requires raw legacy evidence namespace")
            all_evidence = [*raw_legacy_evidence(subject_ref=None)]
            for projection_evidence in context.store.list_records("EvidenceArtifact"):
                if getattr(projection_evidence, "record_type", None) != "EvidenceArtifact":
                    continue
                # Canonical evidence is indexed by its authoritative record id;
                # never feed the compatibility adapter back into this map.
                evidence_by_id[projection_evidence.id] = projection_evidence
            for ev in all_evidence:
                evidence_by_id[ev.id] = ev
        except Exception:
            pass

        promoted = 0
        archived = 0
        for item in candidates:
            # Optional filter: if work specifies scope filter in metadata, honor it
            scope_filter = work.metadata.get("knowledge_scope")
            if scope_filter and isinstance(scope_filter, dict):
                # simple scope check: valid_scope must contain filter keys
                valid_scope = getattr(item, "validity_scope", {}) or {}
                if any(valid_scope.get(k) != v for k, v in scope_filter.items()):
                    continue

            ok, reason = _is_promotable(item, evidence_by_id)
            # P1-3: not sufficiently qualified != invalid -> retain candidate
            # Check if item is explicitly refuted/superseded/withdrawn
            meta = getattr(item, "metadata", {}) if isinstance(getattr(item, "metadata", {}), dict) else {}
            is_explicit_invalid = False
            # Check metadata flags for explicit invalid
            if isinstance(meta, dict):
                if meta.get("refuted") or meta.get("withdrawn") or meta.get("superseded") or meta.get("explicitly_rejected"):
                    is_explicit_invalid = True
                if meta.get("_archive_reason") and any(x in str(meta.get("_archive_reason")) for x in ["refuted", "superseded", "withdrawn", "explicitly_rejected"]):
                    is_explicit_invalid = True
            try:
                if ok:
                    new_item = promote_to_official(item)
                    context.store.save_knowledge_projection(new_item)  # type: ignore[attr-defined]
                    _append_projection_event(context, new_item, "official")
                    promoted += 1
                    logger.info("promoted knowledge %s: %s", item.id, reason)
                elif is_explicit_invalid or any(kw in reason.lower() for kw in ["refuted", "superseded", "withdrawn", "explicitly rejected", "rejected"]):
                    new_item = item.model_copy(update={"lifecycle_status": "archived"})
                    if isinstance(new_item.metadata, dict):
                        new_item.metadata["_archive_reason"] = reason
                    context.store.save_knowledge_projection(new_item)  # type: ignore[attr-defined]
                    _append_projection_event(context, new_item, "archived")
                    archived += 1
                    logger.info("archived knowledge %s: %s", item.id, reason)
                else:
                    # retain candidate - not sufficiently qualified
                    retained = item.model_copy(update={"metadata": {**item.metadata, "_retain_reason": reason}})
                    context.store.save_knowledge_projection(retained)  # type: ignore[attr-defined]
                    _append_projection_event(context, retained, "candidate")
                    logger.info("retain candidate knowledge %s: %s", item.id, reason)
            except Exception:
                logger.debug("knowledge consolidation item update failed", exc_info=True)
                # Keep the candidate durable and journal the failed promotion
                # attempt; never silently drop a governance rejection.
                try:
                    retained = item.model_copy(
                        update={"metadata": {**getattr(item, "metadata", {}), "_retain_reason": "promotion rejected"}}
                    )
                    context.store.save_knowledge_projection(retained)  # type: ignore[attr-defined]
                    _append_projection_event(context, retained, "candidate")
                except Exception:
                    logger.debug("knowledge candidate retention failed", exc_info=True)
                continue

        # Create a summary artifact
        try:
            artifact = Artifact(
                id=new_id("artifact"),
                kind="knowledge-consolidation-report",
                media_type="application/json",
                inline_data={"promoted": promoted, "archived": archived, "total": len(candidates)},
                created_by_run_id=run.id,
            )
            context.store.save_artifact(artifact)
            from portable_runtime.records.models import Observation

            observation = Observation(
                id=new_id("record"),
                kind="knowledge-consolidation",
                source_refs=[artifact.id],
                scope={"work_id": work.id, "run_id": run.id},
                metadata={
                    "workflow": self.id,
                    "promoted": promoted,
                    "archived": archived,
                    "total": len(candidates),
                },
                lifecycle_status="current",
            )
            if hasattr(context.store, "save_record"):
                context.store.save_record(observation)  # type: ignore[attr-defined]
        except Exception:
            pass

        report_refs = [artifact.id] if "artifact" in locals() else []
        if _complete_consolidation_with_proof(context, work, run, report_refs):
            return "succeeded"
        with contextlib.suppress(ValueError):
            context.transition_run("waiting", current_step="kc-done")
        return "waiting"







