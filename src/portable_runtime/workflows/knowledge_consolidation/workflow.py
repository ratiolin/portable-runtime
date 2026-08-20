"""Daily scan / knowledge consolidation workflows (hardened).

DailyScanWorkflow now implements real observing + verification + Evidence/Artifact
production and is schedule-trigger compatible. KnowledgeConsolidationWorkflow
implements candidate -> validated -> promote/archive logic.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from portable_runtime.core.models import Artifact, Evidence, Run, Work, new_id
from portable_runtime.workflows.context import WorkflowContext

logger = logging.getLogger(__name__)

_SUPPORTED_SCAN_KINDS = {"maintenance-scan", "daily-scan", "schedule-scan", "scan", "daily_scan"}


class DailyScanWorkflow:
    id = "daily-scan"
    version = "1.0.0"

    def accepts(self, work: Work) -> bool:
        return work.kind in _SUPPORTED_SCAN_KINDS

    async def run(self, context: WorkflowContext, work: Work, run: Run) -> str:
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
            work.metadata.get("promql_query")
            or work.metadata.get("query")
            or work.metadata.get("promql")
            or "up==1"
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
                ev_status: str = "supported" if result.status == "succeeded" else ("contested" if result.status == "failed" else "unknown")
                if result.status == "unavailable":
                    ev_status = "unknown"
                evidence = Evidence(
                    id=new_id("evidence"),
                    kind=kind,
                    subject_refs=[work.id],
                    artifact_refs=[artifact.id],
                    source=result.provider_id or f"workflow:{self.id}",
                    status=ev_status,  # type: ignore[arg-type]
                )
                # also link provider evidence refs if any
                if result.evidence_refs:
                    evidence.artifact_refs.extend(result.evidence_refs)
                context.store.save_evidence(evidence)
            except Exception:
                logger.debug("daily-scan evidence creation failed", exc_info=True)

        # Decide final status
        statuses = {observe_result.status, verify_result.status}
        if statuses == {"unavailable"} or (observe_result.status == "unavailable" and verify_result.status == "unavailable"):
            with contextlib.suppress(ValueError):
                context.transition_run("blocked", current_step="scan-blocked")
            return "blocked"
        if "failed" in statuses and "succeeded" not in statuses:
            # Both failed -> still record but signal failed so caller can retry
            with contextlib.suppress(ValueError):
                context.transition_run("failed", current_step="scan-failed")
            return "failed"
        with contextlib.suppress(ValueError):
            context.transition_run("succeeded", current_step="scan-done")
        return "succeeded"


_KC_SUPPORTED = {"knowledge-consolidation", "knowledge_consolidation", "consolidation"}


def _is_promotable(item: Any, evidence_by_id: dict[str, Any]) -> tuple[bool, str]:
    # item is KnowledgeItem
    if not getattr(item, "title", "") or not getattr(item, "content_ref", ""):
        return False, "missing title or content_ref"
    ev_refs: list[str] = list(getattr(item, "evidence_refs", []) or [])
    if not ev_refs:
        return False, "no evidence_refs"
    # At least one evidence must be supported or exist
    has_supported = False
    for ref in ev_refs:
        ev = evidence_by_id.get(ref)
        if ev is None:
            continue
        status = getattr(ev, "status", "unknown")
        if status == "supported":
            has_supported = True
            break
        if status in ("unverified", "unknown"):
            has_supported = True
    if not has_supported:
        # If none supported, check if evidence exists at all; if none exists, not promotable
        exists = any(r in evidence_by_id for r in ev_refs)
        if not exists:
            return False, "evidence refs do not exist"
        return False, "no supported evidence"
    return True, "validated"


class KnowledgeConsolidationWorkflow:
    id = "knowledge-consolidation"
    version = "1.0.0"

    def accepts(self, work: Work) -> bool:
        return work.kind in _KC_SUPPORTED

    async def run(self, context: WorkflowContext, work: Work, run: Run) -> str:
        try:
            if context.run.status == "queued":
                context.transition_run("running", current_step="kc-start")
            elif context.run.status in ("waiting", "blocked", "interrupted"):
                context.resume()
            context.set_step("consolidating")
        except ValueError:
            pass

        candidates = context.store.list_knowledge(status="candidate")
        if not candidates:
            with contextlib.suppress(ValueError):
                context.transition_run("succeeded", current_step="kc-done-empty")
            return "succeeded"

        # Build evidence lookup from store
        evidence_by_id: dict[str, Any] = {}
        try:
            all_evidence = context.store.list_evidence(subject_ref=None)
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
                valid_scope = getattr(item, "valid_scope", {}) or {}
                if any(valid_scope.get(k) != v for k, v in scope_filter.items()):
                    continue

            ok, reason = _is_promotable(item, evidence_by_id)
            try:
                if ok:
                    new_item = item.model_copy(update={"status": "official"})
                    context.store.save_knowledge(new_item)
                    promoted += 1
                    logger.info("promoted knowledge %s: %s", item.id, reason)
                else:
                    # Only archive if explicitly invalid; keep candidate if ambiguous?
                    # Spec says promote/archive, so archive invalid ones
                    new_item = item.model_copy(update={"status": "archived"})
                    # store reason in metadata for audit
                    if isinstance(new_item.metadata, dict):
                        new_item.metadata["_archive_reason"] = reason
                    context.store.save_knowledge(new_item)
                    archived += 1
                    logger.info("archived knowledge %s: %s", item.id, reason)
            except Exception:
                logger.debug("knowledge consolidation item update failed", exc_info=True)
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
            evidence = Evidence(
                id=new_id("evidence"),
                kind="knowledge-consolidation",
                subject_refs=[work.id],
                artifact_refs=[artifact.id],
                source=f"workflow:{self.id}",
                status="supported",
            )
            context.store.save_evidence(evidence)
        except Exception:
            pass

        with contextlib.suppress(ValueError):
            context.transition_run("succeeded", current_step="kc-done")
        return "succeeded"


