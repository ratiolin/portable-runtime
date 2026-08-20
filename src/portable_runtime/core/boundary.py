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
from portable_runtime.core.capability_contract import (
    CapabilityContractRegistry,
    EffectContractInvalid,
    compute_effective_impact,
)
from portable_runtime.core.models import Action, Event, Outcome, Step, StepAttempt, new_id, utcnow
from portable_runtime.core.reliability import CircuitBreaker, ReliabilityControls
from portable_runtime.core.router import ConstraintRouter

CODE_FENCING_REJECTED = "FencingRejected"
CODE_LEASE_UNAVAILABLE = "LeaseUnavailable"
CODE_POLICY_DENIED = "PolicyDenied"
CODE_POLICY_UNAVAILABLE = "PolicyUnavailable"
CODE_OBLIGATION_UNSATISFIED = "ObligationUnsatisfied"
CODE_PROCEDURE_INCOMPLETE = "ProcedureIncomplete"
CODE_PROCEDURE_UNAVAILABLE = "ProcedureUnavailable"
CODE_AUTHORIZATION_REQUIRED = "AuthorizationRequired"
CODE_AUTHORIZATION_DENIED = "AuthorizationDenied"
CODE_AUTHORIZATION_UNAVAILABLE = "AuthorizationUnavailable"
CODE_EFFECT_CONTRACT_INVALID = "EffectContractInvalid"
CODE_RELIABILITY_BLOCKED = "ReliabilityBlocked"
CODE_INDEPENDENCE_UNSATISFIED = "IndependenceUnsatisfied"
CODE_NO_ELIGIBLE_PROVIDER = "NoEligibleProvider"
CODE_PRECOMMIT_FAILED = "PrecommitFailed"
CODE_POST_FENCING_REJECTED = "PostFencingRejected"
CODE_RESULT_COMMIT_FAILED = "ResultCommitFailed"
CODE_STALE_RESULT = "StaleResult"
BOUNDARY_ERROR_CODES = {CODE_FENCING_REJECTED, CODE_LEASE_UNAVAILABLE, CODE_POLICY_DENIED, CODE_POLICY_UNAVAILABLE, CODE_OBLIGATION_UNSATISFIED, CODE_PROCEDURE_INCOMPLETE, CODE_PROCEDURE_UNAVAILABLE, CODE_AUTHORIZATION_REQUIRED, CODE_AUTHORIZATION_DENIED, CODE_AUTHORIZATION_UNAVAILABLE, CODE_EFFECT_CONTRACT_INVALID, CODE_RELIABILITY_BLOCKED, CODE_INDEPENDENCE_UNSATISFIED, CODE_NO_ELIGIBLE_PROVIDER, CODE_PRECOMMIT_FAILED, CODE_POST_FENCING_REJECTED, CODE_RESULT_COMMIT_FAILED, CODE_STALE_RESULT}

_EffectClass = Literal["pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"]
_IMPACT_ORDER = {"read": 0, "write-local": 1, "write-remote": 2, "deploy": 3, "admin": 4, "irreversible": 5}
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
    def __init__(self, store: Any | None = None, registry: Any | None = None, *, routing: Any | None = None, policy_engine: Any | None = None, reliability: ReliabilityControls | None = None, runtime_id: str = "runtime", contract_registry: CapabilityContractRegistry | None = None) -> None:
        self.store = store
        self.registry = registry
        self.routing = routing or ConstraintRouter()
        self.policy_engine = policy_engine
        self.reliability = reliability or ReliabilityControls()
        self.runtime_id = runtime_id
        self.contract_registry = contract_registry or CapabilityContractRegistry()

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

    def _extract_actor(self, request: CapabilityRequest) -> str | None:
        actor = getattr(request, "actor_ref", None)
        if actor:
            return actor
        if isinstance(request.metadata, dict):
            v = request.metadata.get("actor_ref")
            if isinstance(v, str):
                return v
        return None
    def _extract_resource(self, request: CapabilityRequest) -> str | None:
        res = getattr(request, "resource_ref", None)
        if res:
            return res
        if isinstance(request.metadata, dict):
            v = request.metadata.get("resource_ref") or request.metadata.get("resource")
            if isinstance(v, str):
                return v
            if isinstance(v, list) and v:
                return str(v[0])
        if isinstance(request.parameters, dict):
            for k in ("resource", "path", "target"):
                vv = request.parameters.get(k)
                if isinstance(vv, str):
                    return vv
        return None
    def _extract_versions(self, request: CapabilityRequest) -> list[str]:
        svr = getattr(request, "subject_version_refs", None)
        if isinstance(svr, list) and svr:
            return [str(x) for x in svr]
        if isinstance(request.metadata, dict):
            v = request.metadata.get("subject_version_refs")
            if isinstance(v, str):
                return [v]
            if isinstance(v, list) and v:
                return [str(x) for x in v]
        return []
    def _effective_impact(self, request: CapabilityRequest, contract: any) -> str:
        cmin = getattr(contract, "minimum_impact_class", "read") if contract else "read"
        req = getattr(request, "effect_class", "read")
        if isinstance(request.metadata, dict) and "requested_effect_class" in request.metadata:
            req2 = request.metadata.get("requested_effect_class")
            if isinstance(req2, str) and req2 in _IMPACT_ORDER and _IMPACT_ORDER.get(req2, 0) > _IMPACT_ORDER.get(req, 0):
                req = req2
        try:
            return compute_effective_impact(cmin, None, req)  # type: ignore
        except Exception:
            return cmin
    def check_authorization(self, request: CapabilityRequest) -> tuple[bool, str]:
        try:
            contract = self.contract_registry.resolve(request.capability)
        except EffectContractInvalid as exc:
            return False, f"EffectContractInvalid: {exc}"
        except Exception as exc:
            return False, f"contract resolve failed: {exc}"
        req_level = getattr(contract, "authorization_requirement", "required")
        if req_level == "none":
            return True, "authorization not required by contract"
        grants: list[any] | None = None
        if self.store is None or not hasattr(self.store, "list_authorizations"):
            if req_level == "required":
                return False, "AuthorizationRequired: authorization store unavailable"
            return True, "no store, optional auth"
        try:
            grants = self.store.list_authorizations()  # type: ignore[attr-defined]
        except Exception as exc:
            return False, f"AuthorizationUnavailable: authorization store failure: {exc}"
        if not grants:
            if req_level == "required":
                return False, "AuthorizationRequired: no grants for capability requiring authorization"
            return True, "no grants, optional"
        actor = self._extract_actor(request)
        if not actor:
            if req_level == "required":
                return False, "AuthorizationRequired: actor missing"
            return True, "no actor, optional"
        if getattr(contract, "resource_required", False):
            res = self._extract_resource(request)
            if not res:
                return False, "AuthorizationRequired: resource missing but contract requires resource"
        if getattr(contract, "subject_version_required", False):
            vers = self._extract_versions(request)
            if not vers:
                return False, "AuthorizationRequired: subject_version missing but contract requires version"
        effective = self._effective_impact(request, contract)
        from portable_runtime.records.authorization import is_authorized_for  # noqa: PLC0415
        resource = self._extract_resource(request)
        svr = self._extract_versions(request)
        action = {"capability": request.capability, "resource": resource, "subject_version_refs": svr, "actor_ref": actor, "effect_class": effective}
        any_match = False
        for g in grants:
            try:
                if getattr(g, "grantee_ref", None) != actor:
                    continue
                any_match = True
                if is_authorized_for(action, g):
                    return True, "authorized"
            except Exception as exc:
                return False, f"AuthorizationUnavailable: grant parse error {exc}"
        if not any_match:
            return False, f"AuthorizationDenied: no grant for actor {actor}"
        return False, f"AuthorizationDenied: no valid grant authorizes {request.capability} with effective_impact {effective} for actor {actor}"

    async def execute(self, request: CapabilityRequest, *, capability_service: Any | None = None) -> CapabilityResult:
        # CapabilityContract resolve + effective impact (never downgrade)
        _contract: any = None
        try:
            _contract = self.contract_registry.resolve(request.capability)
        except EffectContractInvalid as exc:
            _append_event(self.store, CODE_EFFECT_CONTRACT_INVALID, request.id, {"capability": request.capability, "reason": str(exc)})
            return CapabilityResult(request_id=request.id, provider_id="", status="unavailable", message=str(exc), error={"code": CODE_EFFECT_CONTRACT_INVALID, "reason": str(exc), "capability": request.capability})
        except Exception as exc:
            _append_event(self.store, CODE_EFFECT_CONTRACT_INVALID, request.id, {"reason": str(exc)})
            return CapabilityResult(request_id=request.id, provider_id="", status="unavailable", message=f"contract resolve failed: {exc}", error={"code": CODE_EFFECT_CONTRACT_INVALID, "reason": str(exc)})
        try:
            _effective = self._effective_impact(request, _contract)
            _cur = getattr(request, "effect_class", "read")
            if _IMPACT_ORDER.get(_effective, 0) > _IMPACT_ORDER.get(_cur, 0):
                request = request.model_copy(update={"effect_class": _effective})
                if isinstance(request.metadata, dict):
                    request.metadata["effective_impact"] = _effective
            else:
                if isinstance(request.metadata, dict) and "effective_impact" not in request.metadata:
                    request.metadata["effective_impact"] = _cur
            if _contract and hasattr(_contract, "effect_semantics"):
                if isinstance(request.metadata, dict) and "effect_semantics" not in request.metadata:
                    request.metadata["effect_semantics"] = _contract.effect_semantics
        except Exception:
            pass
        contract = _contract
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
        auth_ok, auth_reason = self.check_authorization(request)
        if not auth_ok:
            if "EffectContractInvalid" in auth_reason:
                _code = CODE_EFFECT_CONTRACT_INVALID
            elif "AuthorizationRequired" in auth_reason:
                _code = CODE_AUTHORIZATION_REQUIRED
            elif "AuthorizationUnavailable" in auth_reason:
                _code = CODE_AUTHORIZATION_UNAVAILABLE
            else:
                _code = CODE_AUTHORIZATION_DENIED
            _append_event(store, _code, request.id, {"reason": auth_reason, "actor": self._extract_actor(request)})
            return CapabilityResult(request_id=request.id, provider_id="", status="unavailable", message=auth_reason, error={"code": _code, "reason": auth_reason})
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
        if contract and hasattr(contract, "effect_semantics"):
            _ord = {"pure": 0, "idempotent": 1, "deduplicatable": 2, "reconcilable": 3, "irreversible-opaque": 4}
            _c = contract.effect_semantics
            if _ord.get(_c, 0) > _ord.get(effect_semantics, 0):
                effect_semantics = _c
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
