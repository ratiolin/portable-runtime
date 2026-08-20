from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from portable_runtime.core.models import utcnow
from portable_runtime.core.runtime import Runtime


class CreateWorkRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=20_000)
    kind: str = Field(default="generic-task", min_length=1, max_length=128)
    requested_capabilities: list[str] = Field(default_factory=list)


class RunCapabilityRequest(BaseModel):
    capability: str = Field(min_length=1, max_length=256)
    instruction: str | None = Field(default=None, max_length=20_000)
    run_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


def _paginate(items: list[Any], limit: int, offset: int) -> list[Any]:
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0
    return items[offset : offset + limit]


def _should_paginate(request: Request) -> bool:
    keys = set(request.query_params.keys())
    return bool(keys & {"limit", "offset", "q", "kind", "type", "subject_ref"})


def create_app(runtime: Runtime | None = None) -> FastAPI:
    runtime = runtime or Runtime()
    app = FastAPI(title="Portable Runtime", version="0.1.0")
    app.state.runtime = runtime

    @app.get("/metrics")
    async def metrics() -> Response:
        from portable_runtime.core.metrics import generate_metrics_content
        try:
            from portable_runtime.core.metrics import snapshot_run_status, snapshot_work_status
            works = runtime.store.list_work()
            wcounts: dict[str, int] = {}
            for w in works:
                wcounts[w.status] = wcounts.get(w.status, 0) + 1
            snapshot_work_status(wcounts)
            runs = runtime.store.list_runs()
            rcounts: dict[str, int] = {}
            for r in runs:
                rcounts[r.status] = rcounts.get(r.status, 0) + 1
            snapshot_run_status(rcounts)
            for desc in runtime.registry.list():
                try:
                    h = await runtime.registry.health(desc.id)
                    from portable_runtime.core.metrics import set_provider_health
                    set_provider_health(desc.id, h.available)
                except Exception:  # noqa: S110
                    pass
        except Exception:  # noqa: S110
            pass
        data, content_type = generate_metrics_content()
        return Response(content=data, media_type=content_type)

    @app.get("/v1/metrics/json")
    async def metrics_json() -> dict[str, Any]:
        return runtime.metrics_snapshot()

    @app.get("/v1/runtime")
    async def runtime_info() -> dict[str, Any]:
        return {"runtime_id": runtime.runtime_id, "provider_count": len(runtime.registry.list())}

    @app.get("/v1/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/health/ready")
    async def ready() -> dict[str, Any]:
        return await runtime.health()

    @app.get("/v1/providers")
    async def providers() -> list[dict[str, Any]]:
        return [descriptor.model_dump(mode="json") for descriptor in runtime.registry.list()]

    @app.get("/v1/providers/{provider_id}")
    async def get_provider(provider_id: str) -> dict[str, Any]:
        try:
            return runtime.registry.get(provider_id).descriptor.model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/providers/{provider_id}/enable")
    async def enable_provider(provider_id: str) -> dict[str, Any]:
        try:
            return runtime.registry.enable(provider_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/providers/{provider_id}/disable")
    async def disable_provider(provider_id: str) -> dict[str, Any]:
        try:
            return runtime.registry.disable(provider_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/providers/{provider_id}/reload")
    async def reload_provider(provider_id: str) -> dict[str, Any]:
        try:
            return runtime.registry.reload(provider_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/capabilities")
    async def capabilities() -> list[str]:
        return sorted({capability for provider in runtime.registry.list() for capability in provider.capabilities})

    @app.post("/v1/work")
    async def create_work(body: CreateWorkRequest) -> dict[str, Any]:
        return runtime.create_work(
            title=body.title,
            description=body.description,
            kind=body.kind,
            requested_capabilities=body.requested_capabilities,
        ).model_dump(mode="json")

    @app.get("/v1/work")
    async def list_work(
        request: Request,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
    ) -> Any:
        items = runtime.list_work(status)
        if kind is not None:
            items = [w for w in items if w.kind == kind]
        if q is not None and q.strip():
            qq = q.lower()
            items = [w for w in items if qq in w.title.lower() or qq in w.description.lower()]
        total = len(items)
        paged = _paginate(items, limit, offset)
        dumped = [w.model_dump(mode="json") for w in paged]
        if _should_paginate(request) or request.query_params.get("format") == "paged":
            return {"total": total, "limit": limit, "offset": offset, "items": dumped}
        return dumped

    @app.get("/v1/work/{work_id}", responses={404: {"description": "Not found"}})
    async def get_work(work_id: str) -> dict[str, Any]:
        work = runtime.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="work not found")
        return work.model_dump(mode="json")

    @app.post("/v1/work/{work_id}/run")
    async def run_work(work_id: str, body: RunCapabilityRequest) -> dict[str, Any]:
        if runtime.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="work not found")
        result = await runtime.run_capability(
            work_id,
            body.capability,
            instruction=body.instruction,
            run_id=body.run_id,
            **body.parameters,
        )
        return result.model_dump(mode="json")

    @app.post("/v1/work/{work_id}/cancel")
    async def cancel_work(work_id: str) -> dict[str, Any]:
        work = runtime.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="work not found")
        cancelled = work.model_copy(update={"status": "cancelled", "updated_at": utcnow()})
        runtime.store.save_work(cancelled)
        return cancelled.model_dump(mode="json")

    @app.get("/v1/runs")
    async def list_runs(
        request: Request,
        work_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Any:
        items = runtime.store.list_runs(work_id)
        if status is not None:
            items = [r for r in items if r.status == status]
        total = len(items)
        paged = _paginate(items, limit, offset)
        dumped = [r.model_dump(mode="json") for r in paged]
        if _should_paginate(request):
            return {"total": total, "limit": limit, "offset": offset, "items": dumped}
        return dumped

    @app.get("/v1/runs/{run_id}", responses={404: {"description": "Not found"}})
    async def get_run(run_id: str) -> dict[str, Any]:
        run = runtime.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return run.model_dump(mode="json")

    @app.post("/v1/state/export")
    async def export_state() -> dict[str, Any]:
        return runtime.export_state()

    @app.post("/v1/state/import")
    async def import_state(body: dict[str, list[dict[str, object]]]) -> dict[str, str]:
        runtime.import_state(body)
        return {"status": "imported"}

    @app.get("/v1/knowledge")
    async def list_knowledge(
        request: Request,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
        negative: bool = False,
    ) -> Any:
        items = runtime.store.list_knowledge(status)
        if kind is not None:
            items = [k for k in items if k.kind == kind]
        if q is not None and q.strip():
            qq = q.lower()
            items = [k for k in items if qq in k.title.lower() or qq in str(k.content_ref).lower()]
        if negative:
            items = [k for k in items if k.metadata.get("counterexample_refs")]
        total = len(items)
        paged = _paginate(items, limit, offset)
        dumped = [i.model_dump(mode="json") for i in paged]
        if _should_paginate(request):
            return {"total": total, "limit": limit, "offset": offset, "items": dumped}
        return dumped

    @app.get("/v1/knowledge/{knowledge_id}", responses={404: {"description": "Not found"}})
    async def get_knowledge(knowledge_id: str) -> dict[str, Any]:
        item = runtime.store.get_knowledge(knowledge_id)
        if item is None:
            raise HTTPException(status_code=404, detail="knowledge item not found")
        return item.model_dump(mode="json")

    @app.get("/v1/evidence")
    async def list_evidence(
        request: Request,
        subject_ref: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
    ) -> Any:
        items = runtime.store.list_evidence(subject_ref)
        if kind is not None:
            items = [e for e in items if e.kind == kind]
        if status is not None:
            items = [e for e in items if e.status == status]
        if q is not None and q.strip():
            qq = q.lower()
            items = [e for e in items if qq in e.kind.lower() or qq in e.source.lower()]
        total = len(items)
        paged = _paginate(items, limit, offset)
        dumped = [e.model_dump(mode="json") for e in paged]
        if _should_paginate(request):
            return {"total": total, "limit": limit, "offset": offset, "items": dumped}
        return dumped

    @app.get("/v1/evidence/{evidence_id}", responses={404: {"description": "Not found"}})
    async def get_evidence(evidence_id: str) -> dict[str, Any]:
        getter = getattr(runtime.store, "get_evidence", None)
        if callable(getter):
            item = getter(evidence_id)
            if item is not None:
                return item.model_dump(mode="json")
        for ev in runtime.store.list_evidence():
            if ev.id == evidence_id:
                return ev.model_dump(mode="json")
        raise HTTPException(status_code=404, detail="evidence not found")

    @app.get("/v1/events")
    async def list_events(
        request: Request,
        subject_ref: str | None = None,
        type: str | None = None,  # noqa: A002
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
    ) -> Any:
        getter = getattr(runtime.store, "list_events", None)
        items: list[Any] = getter(subject_ref) if callable(getter) else []
        if type is not None:
            items = [e for e in items if e.type == type]
        if q is not None and q.strip():
            qq = q.lower()
            items = [e for e in items if qq in e.type.lower() or qq in e.subject_ref.lower() or qq in json.dumps(e.payload).lower()]
        total = len(items)
        paged = _paginate(items, limit, offset)
        dumped = [e.model_dump(mode="json") for e in paged]
        if _should_paginate(request):
            return {"total": total, "limit": limit, "offset": offset, "items": dumped}
        return dumped

    @app.get("/v1/events/{event_id}", responses={404: {"description": "Not found"}})
    async def get_event(event_id: str) -> dict[str, Any]:
        getter = getattr(runtime.store, "get_event", None)
        if callable(getter):
            item = getter(event_id)
            if item is not None:
                return item.model_dump(mode="json")
        lister = getattr(runtime.store, "list_events", None)
        if callable(lister):
            for ev in lister():
                if ev.id == event_id:
                    return ev.model_dump(mode="json")
        raise HTTPException(status_code=404, detail="event not found")

    @app.get("/v1/artifacts/{artifact_id}", responses={404: {"description": "Not found"}})
    async def get_artifact(artifact_id: str) -> dict[str, Any]:
        artifact = runtime.store.get_artifact(artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return artifact.model_dump(mode="json")

    @app.post("/v1/triggers/alertmanager")
    async def alertmanager_webhook(request: Request) -> dict[str, Any]:
        from portable_runtime.triggers.alertmanager.trigger import AlertmanagerTrigger
        from portable_runtime.triggers.base import TriggerError as BTriggerError
        body = await request.json()
        signature = request.headers.get("x-signature") or request.headers.get("x-hub-signature") or request.headers.get("x-webhook-signature")
        raw = await request.body()
        raw_body = raw if raw else json.dumps(body).encode()
        trigger = AlertmanagerTrigger()
        async def _emit(event):
            work_fields = trigger.to_work_fields(event)
            runtime.create_work(**work_fields)
        await trigger.start(_emit)
        try:
            events = await trigger.handle_webhook(body, signature=signature, raw_body=raw_body)
        except BTriggerError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return {"events": [e.model_dump(mode="json") for e in events], "works_created": len(events)}

    @app.post("/v1/triggers/webhook")
    async def webhook_trigger(request: Request, kind: str = "webhook") -> dict[str, Any]:
        from portable_runtime.triggers.base import TriggerError as BTriggerError
        from portable_runtime.triggers.webhook.trigger import WebhookTrigger
        body = await request.json()
        signature = request.headers.get("x-signature") or request.headers.get("x-hub-signature") or request.headers.get("x-webhook-signature")
        raw = await request.body()
        raw_body = raw if raw else json.dumps(body).encode()
        trigger = WebhookTrigger()
        async def _emit(event):
            runtime.create_work(
                title=f"Webhook {event.kind}",
                description=str(event.payload)[:20000],
                kind="generic-task",
                requested_capabilities=[kind] if kind != "webhook" else [],
            )
        await trigger.start(_emit)
        try:
            event = await trigger.handle(body, kind=kind, signature=signature, raw_body=raw_body)
        except BTriggerError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return event.model_dump(mode="json")

    @app.post("/v1/triggers/schedule/emit")
    async def schedule_emit(kind: str = "maintenance-scan") -> dict[str, Any]:
        from portable_runtime.triggers.schedule.trigger import ScheduleTrigger
        trigger = ScheduleTrigger(kind=kind)
        async def _emit(event):
            runtime.create_work(
                title=f"Scheduled {event.kind}",
                description="schedule trigger",
                kind=event.kind,
            )
        await trigger.start(_emit)
        event = await trigger.emit_once()
        return event.model_dump(mode="json")

    @app.post("/v1/work/{work_id}/workflow/{workflow_id}")
    async def run_workflow(work_id: str, workflow_id: str) -> dict[str, Any]:
        work = runtime.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="work not found")
        run = runtime.start_run(work_id, workflow_id=workflow_id)
        workflow: Any = None
        if workflow_id in {"incident-repair", "incident"}:
            from portable_runtime.workflows.incident_repair.workflow import IncidentRepairWorkflow
            workflow = IncidentRepairWorkflow()
        elif workflow_id in {"generic-task", "generic"}:
            from portable_runtime.workflows.generic_task.workflow import GenericTaskWorkflow
            workflow = GenericTaskWorkflow()
        elif workflow_id == "daily-scan":
            from portable_runtime.workflows.daily_scan.workflow import DailyScanWorkflow
            workflow = DailyScanWorkflow()
        elif workflow_id == "knowledge-consolidation":
            from portable_runtime.workflows.knowledge_consolidation.workflow import KnowledgeConsolidationWorkflow
            workflow = KnowledgeConsolidationWorkflow()
        else:
            raise HTTPException(status_code=404, detail=f"unknown workflow: {workflow_id}")
        from portable_runtime.workflows.context import WorkflowContext
        ctx = WorkflowContext(work=work, run=run, store=runtime.store, capabilities=runtime.capabilities, registry=runtime.registry)  # noqa: E501
        status = await workflow.run(ctx, work, run)
        updated_work = work.model_copy(update={"status": "completed" if status == "succeeded" else status, "updated_at": utcnow()})  # noqa: E501
        runtime.store.save_work(updated_work)
        updated_run = run.model_copy(update={"status": status})
        runtime.store.save_run(updated_run)
        return {"work_id": work_id, "run_id": run.id, "workflow_id": workflow_id, "status": status}

    # === Batch8 Semantic Plane ===
    @app.get("/v1/records")
    async def list_records(record_type: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        try:
            items = runtime.store.list_records(record_type)  # type: ignore
        except Exception:
            items = []
        return [i.model_dump(mode="json") if hasattr(i, "model_dump") else i for i in _paginate(items, limit, offset)]

    @app.get("/v1/records/{record_id}", responses={404: {"description": "Not found"}})
    async def get_record(record_id: str) -> Any:
        try:
            rec = runtime.store.get_record(record_id)  # type: ignore[assignment]
        except Exception:
            rec = None  # type: ignore[var-annotated]
        if rec is None:
            raise HTTPException(status_code=404, detail="record not found")
        return rec.model_dump(mode="json") if hasattr(rec, "model_dump") else rec

    @app.get("/v1/relations")
    async def list_relations(relation_type: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        try:
            items = runtime.store.list_relations(relation_type)  # type: ignore
        except Exception:
            items = []
        return [i.model_dump(mode="json") if hasattr(i, "model_dump") else i for i in _paginate(items, limit, offset)]

    @app.post("/v1/relations")
    async def create_relation(payload: dict[str, Any]) -> dict[str, Any]:
        from portable_runtime.records.relations import RecordRelation
        try:
            rel = RecordRelation.model_validate(payload)
            runtime.store.save_relation(rel)  # type: ignore
            return rel.model_dump(mode="json")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/revalidation/pending")
    async def revalidation_pending(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        try:
            recs = runtime.store.list_records()  # type: ignore
            pending = [r for r in recs if getattr(r, "epistemic_status", None) == "revalidation-required"]
            return [r.model_dump(mode="json") for r in _paginate(pending, limit, offset)]
        except Exception:
            return []

    @app.get("/v1/revalidation/affected-by/{change_ref}")
    async def affected_by(change_ref: str, change_type: str = "evaluator") -> list[dict[str, Any]]:
        from portable_runtime.records.revalidation import assess_revalidation
        try:
            relations = runtime.store.list_relations()  # type: ignore
            affected = assess_revalidation(change_ref, change_type, relations)
            return [a.model_dump(mode="json") for a in affected]
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/reopen/{record_id}")
    async def reopen_record(record_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        from portable_runtime.records.reopen import ReopenAssessment, create_reopen_work
        payload = payload or {}
        scope = payload.get("revision_scope", "other")
        reason = payload.get("reason", f"reopen {record_id}")
        assess = ReopenAssessment(record_ref=record_id, revision_scope=scope, reason=reason)
        work = runtime.get_work(record_id)
        if work is None:
            try:
                rec = runtime.store.get_record(record_id)  # type: ignore[assignment]
                if rec is None:
                    raise HTTPException(status_code=404, detail="record not found")
                work = runtime.create_work(title=f"Reopen {record_id}", description=reason, kind="reopen")
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        new_work = create_reopen_work(assess, work)
        runtime.store.save_work(new_work)
        try:
            from portable_runtime.records.relations import RecordRelation
            rel = RecordRelation(relation_type="supersedes", subject_ref=new_work.id, object_ref=work.id, metadata={"reopen_assessment_id": assess.id})
            runtime.store.save_relation(rel)  # type: ignore
        except Exception:
            pass
        return {"assessment": assess.model_dump(mode="json"), "work": new_work.model_dump(mode="json")}

    @app.get("/v1/authorizations")
    async def list_authorizations(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        try:
            items = runtime.store.list_records("Authorization")  # type: ignore
        except Exception:
            items = []
        return [i.model_dump(mode="json") if hasattr(i, "model_dump") else i for i in _paginate(items, limit, offset)]

    @app.get("/v1/authorizations/{auth_id}", responses={404: {"description": "Not found"}})
    async def get_authorization(auth_id: str) -> dict[str, Any]:
        try:
            rec = runtime.store.get_record(auth_id)  # type: ignore
            if rec is not None:
                return rec.model_dump(mode="json")
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="authorization not found")

    @app.get("/v1/policies")
    async def list_policies() -> list[dict[str, Any]]:
        return [{"id": "allow-all"}, {"id": "sensitive-path"}, {"id": "external-side-effect"}]

    @app.get("/v1/procedures/{work_id}", responses={404: {"description": "Not found"}})
    async def get_procedure(work_id: str, profile: str = "standard") -> dict[str, Any]:
        from portable_runtime.workflows.procedure import ProcedureProfile, check_procedure
        work = runtime.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="work not found")
        runs = runtime.store.list_runs(work_id)
        run = runs[0] if runs else None  # noqa: F841
        try:
            prof = ProcedureProfile(profile)
        except Exception:
            prof = ProcedureProfile.standard
        statuses: Any = check_procedure(work, run, prof) if run else []  # type: ignore[assignment]
        return {"work_id": work_id, "profile": prof.value, "gates": [s.model_dump(mode="json") if hasattr(s, "model_dump") else s for s in statuses]}

    @app.get("/v1/steps")
    async def list_steps(run_id: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        try:
            items = runtime.store.list_steps(run_id)  # type: ignore
            return [i.model_dump(mode="json") for i in _paginate(items, limit, offset)]
        except Exception:
            return []

    @app.get("/v1/explain/{record_id}")
    async def explain_record(record_id: str) -> dict[str, Any]:
        from portable_runtime.records.provenance import lineage
        try:
            relations = runtime.store.list_relations()  # type: ignore
            chain = lineage(record_id, relations)
            rec = None  # type: ignore[var-annotated]
            try:
                rec = runtime.store.get_record(record_id)  # type: ignore[assignment]
            except Exception:
                rec = runtime.get_work(record_id)  # type: ignore[assignment]
            return {"record_id": record_id, "record": rec.model_dump(mode="json") if rec and hasattr(rec, "model_dump") else None, "lineage": [r.model_dump(mode="json") for r in chain]}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/why/{action_id}")
    async def why_action(action_id: str) -> dict[str, Any]:
        try:
            relations = runtime.store.list_relations()  # type: ignore
            chain = [r for r in relations if r.subject_ref == action_id or r.object_ref == action_id]
            return {"action_id": action_id, "relations": [r.model_dump(mode="json") for r in chain]}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/lineage/{record_id}")
    async def lineage_record(record_id: str) -> dict[str, Any]:
        from portable_runtime.records.provenance import lineage
        try:
            relations = runtime.store.list_relations()  # type: ignore
            chain = lineage(record_id, relations)
            return {"record_id": record_id, "lineage": [r.model_dump(mode="json") for r in chain]}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/recovery/status")
    async def recovery_status() -> dict[str, Any]:
        try:
            stale = runtime.recover(before_seconds=30)
            return {"stale_steps": [s.model_dump(mode="json") for s in stale], "count": len(stale)}
        except Exception as exc:
            return {"error": str(exc), "stale_steps": []}

    return app

