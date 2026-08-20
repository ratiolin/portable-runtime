from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
)
from portable_runtime.core.models import Action, Event, Outcome, Step, StepAttempt, new_id, utcnow
from portable_runtime.core.reliability import CircuitBreaker, ReliabilityControls
from portable_runtime.core.router import ConstraintRouter

_EffectClass = Literal["pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"]
_CIRCUITS: dict[str, CircuitBreaker] = {}

def _circuit_for(provider_id: str) -> CircuitBreaker:
    if provider_id not in _CIRCUITS:
        _CIRCUITS[provider_id] = CircuitBreaker()
    return _CIRCUITS[provider_id]

def _digest_request(request: CapabilityRequest) -> str:
    payload = json.dumps({"cap": request.capability, "inst": request.instruction, "params": request.parameters}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]

def _extract_lease_generation(request: CapabilityRequest) -> int | None:
    lg = getattr(request, "lease_generation", None)
    if lg is not None:
        return lg  # type: ignore[no-redef]
    if isinstance(request.metadata, dict):
        v = request.metadata.get("lease_generation")
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
    return None

def _extract_lease_owner(request: CapabilityRequest) -> str | None:
    lo = getattr(request, "lease_owner", None)
    if lo is not None:
        return lo  # type: ignore[no-redef]
    if isinstance(request.metadata, dict):
        v = request.metadata.get("lease_owner")
        if isinstance(v, str):
            return v
    return None

def validate_fencing(request: CapabilityRequest, run: Any | None, *, now: datetime | None = None) -> tuple[bool, str]:
    if run is None or request.run_id is None:
        return True, "no run fencing required"
    now = now or datetime.now(UTC)
    if not run.lease_owner and (run.lease_generation == 0 or run.lease_generation is None):
        return True, "unleased run"
    req_gen = _extract_lease_generation(request)
    req_owner = _extract_lease_owner(request)
    if req_gen is None:
        return False, f"fencing: missing lease_generation, expected {run.lease_generation}"
    if req_gen != run.lease_generation:
        return False, f"fencing: generation mismatch request {req_gen} != current {run.lease_generation}"
    if run.lease_owner and req_owner is not None and req_owner != run.lease_owner:
        return False, f"fencing: owner mismatch {req_owner} != {run.lease_owner}"
    if run.lease_owner and req_owner is None:
        return False, f"fencing: missing lease_owner, expected {run.lease_owner}"
    if run.lease_expires_at is not None and run.lease_expires_at <= now:
        return False, f"fencing: lease expired at {run.lease_expires_at.isoformat()}"
    return True, "fencing ok"

def _append_event(store: Any, event_type: str, subject_ref: str, payload: dict[str, Any]) -> None:
    try:
        ev = Event(id=new_id("event"), type=event_type, subject_ref=subject_ref, payload=payload)
        if hasattr(store, "append_event"):
            store.append_event(ev)
        elif hasattr(store, "save_event"):
            store.save_event(ev)
    except Exception:
        pass

class RealityBoundary:
    def __init__(self, store: Any | None = None, registry: Any | None = None, *, routing: Any | None = None, policy_engine: Any | None = None, reliability: ReliabilityControls | None = None, runtime_id: str = "runtime") -> None:
        self.store = store
        self.registry = registry
        self.routing = routing or ConstraintRouter()
        self.policy_engine = policy_engine
        self.reliability = reliability or ReliabilityControls()
        self.runtime_id = runtime_id

    def validate_fencing(self, request: CapabilityRequest) -> tuple[bool, str]:
        if self.store is None or request.run_id is None:
            return True, "no store/run"
        try:
            run = self.store.get_run(request.run_id) if hasattr(self.store, "get_run") else None  # type: ignore[attr-defined]
            return validate_fencing(request, run)
        except Exception as exc:  # noqa: BLE001
            return False, f"fencing check failed: {exc}"

    def check_fencing(self, request: CapabilityRequest) -> tuple[bool, str]:
        return self.validate_fencing(request)

    def check_authorization(self, request: CapabilityRequest) -> tuple[bool, str]:
        try:
            if self.store is not None and hasattr(self.store, "list_authorizations"):
                grants = self.store.list_authorizations()  # type: ignore[attr-defined]
                if not grants:
                    return True, "no grants configured"
                actor = getattr(request, "actor_ref", None) or (request.metadata.get("actor_ref") if isinstance(request.metadata, dict) else None)
                if not actor:
                    # if no actor, treat as not requiring auth for read-like
                    return True, "no actor"
                from portable_runtime.records.authorization import is_authorized_for  # noqa: PLC0415

                resource = getattr(request, "resource_ref", None) or (request.metadata.get("resource_ref") if isinstance(request.metadata, dict) else None)
                svr = getattr(request, "subject_version_refs", None) or (request.metadata.get("subject_version_refs") if isinstance(request.metadata, dict) else None) or []
                action = {"capability": request.capability, "resource": resource, "subject_version_refs": svr, "actor_ref": actor, "effect_class": getattr(request, "effect_class", None)}
                for g in grants:
                    if getattr(g, "grantee_ref", None) == actor and is_authorized_for(action, g):
                        return True, "authorized"
                return False, f"no valid grant for actor {actor} capability {request.capability}"
        except Exception as exc:  # noqa: BLE001
            return False, f"auth check failed: {exc}"
        return True, "authorized"

    async def execute(self, request: CapabilityRequest, *, capability_service: Any | None = None) -> CapabilityResult:
        registry = self.registry or (getattr(capability_service, "registry", None) if capability_service else None)
        store = self.store or (getattr(capability_service, "store", None) if capability_service else None)
        routing = self.routing
        if capability_service and getattr(capability_service, "routing", None) and isinstance(capability_service.routing, ConstraintRouter):  # noqa: SIM102
                routing = capability_service.routing
        descriptors: list[ProviderDescriptor] = []
        if registry is not None:
            try:
                descriptors = registry.descriptors_for(request.capability, request.excluded_provider_ids)
            except Exception:
                descriptors = []
        if store is not None and request.run_id:
            try:
                run = store.get_run(request.run_id) if hasattr(store, "get_run") else None
                if run is not None:
                    ok, reason = validate_fencing(request, run)
                    if not ok:
                        _append_event(store, "FencingRejected", request.id, {"reason": reason, "phase": "pre"})
                        return CapabilityResult(request_id=request.id, provider_id="", status="unavailable", message=f"fencing rejected: {reason}", error={"code": "FencingRejected", "reason": reason})
            except Exception:
                pass
        if self.policy_engine is not None:
            try:
                from portable_runtime.core.policies import PolicyContext
                ctx = PolicyContext(work_id=request.work_id, capability=request.capability, provider_id=None, payload={"capability": request.capability, "parameters": request.parameters, "instruction": request.instruction}, metadata=request.metadata)
                decision = await self.policy_engine.evaluate(ctx)
                if decision.disposition == "deny" or decision.status == "deny":
                    _append_event(store, "PolicyDenied", request.id, {"reason": decision.reason or "policy deny"})
                    return CapabilityResult(request_id=request.id, provider_id="", status="unavailable", message=f"policy denied: {decision.reason}", error={"code": "PolicyDenied"})
                if decision.disposition == "defer":
                    _append_event(store, "PolicyDeferred", request.id, {"reason": decision.reason})
                    return CapabilityResult(request_id=request.id, provider_id="", status="unavailable", message=f"policy deferred: {decision.reason}", error={"code": "PolicyDeferred"})
            except Exception:
                pass
        try:
            if store is not None and request.work_id and request.run_id:
                w = store.get_work(request.work_id) if hasattr(store, "get_work") else None
                r = store.get_run(request.run_id) if hasattr(store, "get_run") else None
                if w is not None and r is not None:
                    from portable_runtime.workflows.procedure import check_procedure
                    profile_raw = None
                    if isinstance(w.metadata, dict):
                        profile_raw = w.metadata.get("procedure_profile") or w.metadata.get("profile")
                    if isinstance(r.metadata, dict) and not profile_raw:
                        profile_raw = r.metadata.get("procedure_profile")
                    profile = profile_raw or "minimal"
                    statuses = check_procedure(w, r, profile)
                    blocked = [s for s in statuses if s.status == "blocked"]
                    if blocked:
                        _append_event(store, "ProcedureBlocked", request.id, {"blocked": [str(s.obligation) for s in blocked]})
                        return CapabilityResult(request_id=request.id, provider_id="", status="unavailable", message=f"procedure blocked: {blocked[0].obligation}", error={"code": "ProcedureBlocked"})
        except Exception:
            pass
        try:
            if store is not None and hasattr(store, "list_authorizations"):
                grants = store.list_authorizations()
                if grants:
                    actor = request.actor_ref or (request.metadata.get("actor_ref") if isinstance(request.metadata, dict) else None)
                    if actor:
                        from portable_runtime.records.authorization import is_authorized_for
                        action = {"capability": request.capability, "resource": request.resource_ref or (request.metadata.get("resource_ref") if isinstance(request.metadata, dict) else None) or request.parameters.get("resource") or request.parameters.get("path"), "subject_version_refs": request.subject_version_refs or (request.metadata.get("subject_version_refs") if isinstance(request.metadata, dict) else None), "actor_ref": actor}
                        if not any(is_authorized_for(action, g) for g in grants if getattr(g, "grantee_ref", None) == actor):
                            matches_actor = [g for g in grants if getattr(g, "grantee_ref", None) == actor]
                            if matches_actor:
                                _append_event(store, "AuthorizationDenied", request.id, {"actor": actor})
                                return CapabilityResult(request_id=request.id, provider_id="", status="unavailable", message="authorization denied", error={"code": "AuthorizationDenied"})
        except Exception:
            pass
        try:
            side_effect = False
            if descriptors:
                sc = getattr(descriptors[0], "side_effect_class", "pure")
                side_effect = sc != "pure"
            if not self.reliability.can_execute(side_effect=side_effect):
                _append_event(store, "ReliabilityBlocked", request.id, {"side_effect": side_effect})
                return CapabilityResult(request_id=request.id, provider_id="", status="unavailable", message="reliability budget exceeded", error={"code": "ReliabilityBlocked"})
        except Exception:
            pass
        if registry is None:
            return CapabilityResult(request_id=request.id, provider_id="", status="unavailable", message="no registry")
        healthy: list[ProviderDescriptor] = []
        for descriptor in descriptors:
            try:
                health = await registry.health(descriptor.id)
                if not health.available:
                    continue
                breaker = _circuit_for(descriptor.id)
                if not breaker.allow():
                    continue
                healthy.append(descriptor)
            except Exception:
                continue
        selected = await routing.select(request, healthy) if healthy else None
        if selected is None:
            if store is not None:
                _append_event(store, "NoEligibleProvider", request.id, {"capability": request.capability})
            return CapabilityResult(request_id=request.id, provider_id="", status="unavailable", message=f"capability unavailable: {request.capability}")
        side_effect_class: _EffectClass = getattr(selected, "side_effect_class", "pure")  # type: ignore
        effect_semantics = getattr(selected, "effect_semantics", side_effect_class)
        step_id: str | None = None
        attempt_id: str | None = None
        action_id: str | None = None
        if store is not None and request.work_id and request.run_id:
            try:
                step_key = request.step_key or f"{request.capability}:{request.idempotency_key or request.id}"
                existing_steps: list[Step] = []
                try:
                    existing_steps = store.list_steps(request.run_id)  # type: ignore
                except Exception:
                    pass
                step = next((s for s in existing_steps if s.step_key == step_key), None)
                input_digest = _digest_request(request)
                lease_gen = _extract_lease_generation(request) or 0
                if step is None:
                    step = Step(id=new_id("step"), run_id=request.run_id, step_key=step_key, kind=request.capability.split(".")[0] if "." in request.capability else "generic", status="running", effect_semantics=effect_semantics, side_effect_class=side_effect_class, reversibility=getattr(selected, "reversibility", "unknown"), input_digest=input_digest, lease_generation=lease_gen, version=0)
                    if side_effect_class != "pure":
                        try:
                            if hasattr(store, "transaction"):
                                with store.transaction():
                                    store.save_step(step)
                            else:
                                store.save_step(step)
                        except Exception as exc:
                            _append_event(store, "PrecommitFailed", request.id, {"reason": str(exc), "phase": "save_step"})
                            return CapabilityResult(request_id=request.id, provider_id=selected.id, status="unavailable", message=f"precommit failed: {exc}", error={"code": "PrecommitFailed"})
                    else:
                        try:
                            store.save_step(step)
                        except Exception:
                            pass
                    step_id = step.id
                else:
                    step.status = "running"
                    step.updated_at = utcnow()
                    step.input_digest = input_digest
                    step.effect_semantics = effect_semantics
                    step.side_effect_class = side_effect_class
                    step.lease_generation = lease_gen
                    try:
                        step.version = (step.version or 0) + 1
                    except Exception:
                        step.version = 1
                    if side_effect_class != "pure":
                        try:
                            if hasattr(store, "transaction"):
                                with store.transaction():
                                    store.save_step(step)
                            else:
                                store.save_step(step)
                        except Exception as exc:
                            _append_event(store, "PrecommitFailed", request.id, {"reason": str(exc), "phase": "save_step_update"})
                            return CapabilityResult(request_id=request.id, provider_id=selected.id, status="unavailable", message=f"precommit failed: {exc}", error={"code": "PrecommitFailed"})
                    else:
                        try:
                            store.save_step(step)
                        except Exception:
                            pass
                    step_id = step.id
                current_attempt_no = 1
                try:
                    if step_id:
                        atts = store.list_attempts(step_id)  # type: ignore
                        if atts:
                            current_attempt_no = max(a.attempt_no for a in atts) + 1
                except Exception:
                    pass
                attempt = StepAttempt(id=new_id("attempt"), step_id=step_id or new_id("step"), attempt_no=current_attempt_no, provider_id=selected.id, request_ref=request.id, idempotency_key=request.idempotency_key or request.id, status="running", lease_generation=lease_gen)
                action_id = new_id("action")
                if side_effect_class != "pure":
                    try:
                        if hasattr(store, "transaction"):
                            with store.transaction():
                                if step_id:
                                    s = store.get_step(step_id)  # type: ignore
                                    if s:
                                        s.current_attempt = attempt.attempt_no
                                        store.save_step(s)
                                store.save_attempt(attempt)
                                store.save_action(Action(id=action_id, work_id=request.work_id, run_id=request.run_id, capability=request.capability, provider_id=selected.id, request_ref=request.id, status="running"))
                        else:
                            if step_id:
                                s = store.get_step(step_id)  # type: ignore
                                if s:
                                    s.current_attempt = attempt.attempt_no
                                    store.save_step(s)
                            store.save_attempt(attempt)
                            store.save_action(Action(id=action_id, work_id=request.work_id, run_id=request.run_id, capability=request.capability, provider_id=selected.id, request_ref=request.id, status="running"))
                    except Exception as exc:
                        _append_event(store, "PrecommitFailed", request.id, {"reason": str(exc), "phase": "save_attempt_action"})
                        return CapabilityResult(request_id=request.id, provider_id=selected.id, status="unavailable", message=f"precommit failed: {exc}", error={"code": "PrecommitFailed"})
                else:
                    try:
                        if step_id:
                            s = store.get_step(step_id)  # type: ignore
                            if s:
                                s.current_attempt = attempt.attempt_no
                                store.save_step(s)
                        store.save_attempt(attempt)
                        store.save_action(Action(id=action_id, work_id=request.work_id, run_id=request.run_id, capability=request.capability, provider_id=selected.id, request_ref=request.id, status="running"))
                    except Exception:
                        pass
                attempt_id = attempt.id
                try:
                    self.reliability.record_action(side_effect=side_effect_class != "pure")
                except Exception:
                    pass
            except Exception as exc:
                if side_effect_class != "pure":
                    _append_event(store, "PrecommitFailed", request.id, {"reason": str(exc)})
                    return CapabilityResult(request_id=request.id, provider_id=selected.id, status="unavailable", message=f"precommit failed: {exc}", error={"code": "PrecommitFailed"})
        try:
            provider = registry.get(selected.id)
        except Exception as exc:
            return CapabilityResult(request_id=request.id, provider_id=selected.id, status="unavailable", message=str(exc), error={"type": type(exc).__name__})
        context = InvocationContext(runtime_id=self.runtime_id, work_id=request.work_id, run_id=request.run_id, lease_generation=_extract_lease_generation(request) or 0, idempotency_key=request.idempotency_key)
        if request.metadata:
            context.metadata.update(request.metadata)
        breaker = _circuit_for(selected.id)
        try:
            result = await provider.invoke(request, context)
        except Exception as exc:
            breaker.record_failure()
            result = CapabilityResult(request_id=request.id, provider_id=selected.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        else:
            if result.status == "failed":
                breaker.record_failure()
            elif result.status == "succeeded":
                breaker.record_success()
        if store is not None and request.run_id and step_id:
            try:
                run2 = store.get_run(request.run_id) if hasattr(store, "get_run") else None
                if run2 is not None:
                    ok2, reason2 = validate_fencing(request, run2)
                    if not ok2:
                        _append_event(store, "LateResultRejected", request.id, {"reason": reason2, "phase": "post", "provider_id": selected.id})
                        try:
                            if attempt_id:
                                att = store.get_attempt(attempt_id) if hasattr(store, "get_attempt") else None
                                if att is None and step_id:
                                    atts = store.list_attempts(step_id)  # type: ignore
                                    att = sorted(atts, key=lambda a: a.attempt_no)[-1] if atts else None
                                if att:
                                    att.status = "failed"
                                    att.error = {"code": "LateResultRejected", "reason": reason2}
                                    att.ended_at = utcnow()
                                    store.save_attempt(att)
                            if step_id:
                                st = store.get_step(step_id) if hasattr(store, "get_step") else None
                                if st and st.status == "running":
                                    st.status = "failed"
                                    st.updated_at = utcnow()
                                    store.save_step(st)
                        except Exception:
                            pass
                        if result.status == "succeeded":
                            result = CapabilityResult(request_id=request.id, provider_id=selected.id, status="unavailable", message=f"late result rejected: {reason2}", error={"code": "LateResultRejected", "reason": reason2}, output_artifact_refs=result.output_artifact_refs, evidence_refs=result.evidence_refs)
                        return result
            except Exception:
                pass
        if store is not None and request.work_id and request.run_id and step_id:
            try:
                if hasattr(store, "transaction"):
                    with store.transaction():
                        st = store.get_step(step_id)  # type: ignore
                        if st:
                            if result.status == "succeeded":
                                st.status = "succeeded"
                            elif result.status == "failed":
                                st.status = "failed"
                            elif result.status == "unknown":
                                st.status = "unknown"
                            elif result.status in ("cancelled", "unavailable"):
                                st.status = "failed"
                            else:
                                st.status = "failed"
                            st.updated_at = utcnow()
                            store.save_step(st)
                        atts = store.list_attempts(step_id)  # type: ignore
                        if atts:
                            last = sorted(atts, key=lambda a: a.attempt_no)[-1]
                            last.status = result.status if result.status in ("succeeded", "failed", "cancelled", "unknown") else "failed"
                            last.ended_at = utcnow()
                            last.result_ref = result.request_id
                            if result.error:
                                last.error = result.error
                            store.save_attempt(last)
                        if action_id:
                            store.save_action(Action(id=action_id, work_id=request.work_id, run_id=request.run_id, capability=request.capability, provider_id=selected.id, request_ref=request.id, status=result.status))
                        store.save_outcome(Outcome(id=new_id("outcome"), action_id=action_id or new_id("action"), artifact_refs=result.output_artifact_refs, evidence_refs=result.evidence_refs, status=result.status))
                        _append_event(store, "CapabilitySucceeded" if result.status == "succeeded" else "CapabilityCompleted", request.id, {"provider_id": selected.id, "status": result.status, "capability": request.capability})
                else:
                    st = store.get_step(step_id)  # type: ignore
                    if st:
                        if result.status == "succeeded":
                            st.status = "succeeded"
                        elif result.status == "failed":
                            st.status = "failed"
                        elif result.status == "unknown":
                            st.status = "unknown"
                        else:
                            st.status = "failed"
                        st.updated_at = utcnow()
                        store.save_step(st)
                    atts = store.list_attempts(step_id)  # type: ignore
                    if atts:
                        last = sorted(atts, key=lambda a: a.attempt_no)[-1]
                        last.status = result.status if result.status in ("succeeded", "failed", "cancelled", "unknown") else "failed"
                        last.ended_at = utcnow()
                        last.result_ref = result.request_id
                        if result.error:
                            last.error = result.error
                        store.save_attempt(last)
                    if action_id:
                        store.save_action(Action(id=action_id, work_id=request.work_id, run_id=request.run_id, capability=request.capability, provider_id=selected.id, request_ref=request.id, status=result.status))
                    store.save_outcome(Outcome(id=new_id("outcome"), action_id=action_id or new_id("action"), artifact_refs=result.output_artifact_refs, evidence_refs=result.evidence_refs, status=result.status))
                    _append_event(store, "CapabilityCompleted", request.id, {"provider_id": selected.id, "status": result.status})
            except Exception:
                pass
        return result
