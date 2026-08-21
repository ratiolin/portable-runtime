from __future__ import annotations

import hashlib
import inspect
import json
from datetime import UTC, datetime
from typing import Any, Literal, cast

from portable_runtime.core.boundary_stages import (
    BoundaryStagePlan,
    InvocationStagePlan,
    ReliabilityStageInput,
    evaluate_reliability_stage,
    select_provider_stage,
)
from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
)
from portable_runtime.core.capability_contract import (
    CapabilityContractRegistry,
    CapabilityEffectRegistry,
    EffectContractInvalid,
    EffectContractMissing,
    compute_effective_impact,
)
from portable_runtime.core.models import Action, Event, Outcome, Step, StepAttempt, new_id, utcnow
from portable_runtime.core.qualification import (
    AssessmentContext,
    InvocationPermit,
    QualificationResolutionError,
)
from portable_runtime.core.reliability import CircuitBreaker, ReliabilityControls
from portable_runtime.core.router import ConstraintRouter
from portable_runtime.records.authorization import CanonicalAuthorizationRequest
from portable_runtime.records.authorization import EffectClass as AuthorizationEffectClass

CODE_FENCING_REJECTED = "FencingRejected"
CODE_FENCING_UNAVAILABLE = "FencingUnavailable"
CODE_LEASE_UNAVAILABLE = "LeaseUnavailable"
CODE_POLICY_DENIED = "PolicyDenied"
CODE_POLICY_UNAVAILABLE = "PolicyUnavailable"
CODE_OBLIGATION_UNSATISFIED = "ObligationUnsatisfied"
CODE_PROCEDURE_INCOMPLETE = "ProcedureIncomplete"
CODE_PROCEDURE_UNAVAILABLE = "ProcedureUnavailable"
CODE_AUTHORIZATION_REQUIRED = "AuthorizationRequired"
CODE_AUTHORIZATION_DENIED = "AuthorizationDenied"
CODE_AUTHORIZATION_UNAVAILABLE = "AuthorizationUnavailable"
CODE_RESOURCE_REQUIRED = "ResourceRequired"
CODE_SUBJECT_VERSION_REQUIRED = "SubjectVersionRequired"
CODE_EFFECT_CONTRACT_INVALID = "EffectContractInvalid"
CODE_EFFECT_CONTRACT_MISSING = "EffectContractMissing"
CODE_RELIABILITY_BLOCKED = "ReliabilityBlocked"
CODE_RELIABILITY_UNAVAILABLE = "ReliabilityUnavailable"
CODE_INDEPENDENCE_UNSATISFIED = "IndependenceUnsatisfied"
CODE_NO_ELIGIBLE_PROVIDER = "NoEligibleProvider"
CODE_ROUTING_UNAVAILABLE = "RoutingUnavailable"
CODE_PRECOMMIT_FAILED = "PrecommitFailed"
CODE_POST_FENCING_REJECTED = "PostFencingRejected"
CODE_RESULT_COMMIT_FAILED = "ResultCommitFailed"
CODE_STALE_RESULT = "StaleResult"
CODE_QUALIFICATION_UNAVAILABLE = "QualificationUnavailable"
CODE_QUALIFICATION_CHANGED = "QualificationChanged"
BOUNDARY_ERROR_CODES = {
    CODE_FENCING_REJECTED,
    CODE_FENCING_UNAVAILABLE,
    CODE_LEASE_UNAVAILABLE,
    CODE_POLICY_DENIED,
    CODE_POLICY_UNAVAILABLE,
    CODE_OBLIGATION_UNSATISFIED,
    CODE_PROCEDURE_INCOMPLETE,
    CODE_PROCEDURE_UNAVAILABLE,
    CODE_AUTHORIZATION_REQUIRED,
    CODE_AUTHORIZATION_DENIED,
    CODE_AUTHORIZATION_UNAVAILABLE,
    CODE_RESOURCE_REQUIRED,
    CODE_SUBJECT_VERSION_REQUIRED,
    CODE_EFFECT_CONTRACT_INVALID,
    CODE_EFFECT_CONTRACT_MISSING,
    CODE_RELIABILITY_BLOCKED,
    CODE_RELIABILITY_UNAVAILABLE,
    CODE_INDEPENDENCE_UNSATISFIED,
    CODE_NO_ELIGIBLE_PROVIDER,
    CODE_ROUTING_UNAVAILABLE,
    CODE_PRECOMMIT_FAILED,
    CODE_POST_FENCING_REJECTED,
    CODE_RESULT_COMMIT_FAILED,
    CODE_STALE_RESULT,
    CODE_QUALIFICATION_UNAVAILABLE,
    CODE_QUALIFICATION_CHANGED,
}

_EffectClass = Literal["pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"]
_IMPACT_ORDER = {"read": 0, "write-local": 1, "write-remote": 2, "deploy": 3, "admin": 4, "irreversible": 5}
_CIRCUITS: dict[str, CircuitBreaker] = {}

def _circuit_for(provider_id: str) -> CircuitBreaker:
    if provider_id not in _CIRCUITS:
        _CIRCUITS[provider_id] = CircuitBreaker()
    return _CIRCUITS[provider_id]

def _digest_request(request: CapabilityRequest) -> str:
    payload = request.model_dump(mode="json")
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()

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

def _append_event(store: Any, event_type: str, subject_ref: str, payload: dict[str, Any]) -> bool:
    """Append a durable transition event and report journal availability.

    A transition event is evidence, not a best-effort log line.  Callers keep
    their typed fail-closed result when the journal is unavailable, while the
    boolean lets critical paths/tests distinguish durable evidence from a
    swallowed logging failure.
    """
    if store is None:
        return False
    try:
        ev = Event(id=new_id("event"), type=event_type, subject_ref=subject_ref, payload=payload)
        if hasattr(store, "append_event"):
            store.append_event(ev)
        elif hasattr(store, "save_event"):
            store.save_event(ev)
        else:
            return False
        return True
    except Exception:
        return False


def _call_supported(method: Any, **kwargs: Any) -> Any:
    """Call an additive controller API without hiding controller failures."""

    try:
        signature = inspect.signature(method)
        parameters = signature.parameters
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
            return method(**kwargs)
        accepted = {name: value for name, value in kwargs.items() if name in parameters}
        return method(**accepted)
    except (TypeError, ValueError):
        return method(**kwargs)


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 1 else None

class RealityBoundary:
    def __init__(self, store: Any | None = None, registry: Any | None = None, *, routing: Any | None = None, policy_engine: Any | None = None, reliability: ReliabilityControls | None = None, runtime_id: str = "runtime", contract_registry: CapabilityContractRegistry | None = None, effect_registry: CapabilityEffectRegistry | None = None) -> None:
        self.store = store
        self.registry = registry
        self.routing = routing or ConstraintRouter()
        self.policy_engine = policy_engine
        self.reliability = reliability or ReliabilityControls()
        self.runtime_id = runtime_id
        self.contract_registry = contract_registry or CapabilityContractRegistry(effect_registry=effect_registry)
        self.effect_registry = effect_registry or getattr(self.contract_registry, "effect_registry", CapabilityEffectRegistry())
        self.stage_plan = BoundaryStagePlan()

    def validate_fencing(self, request: CapabilityRequest) -> tuple[bool, str]:
        if self.store is None or request.run_id is None:
            return True, "no store/run"
        try:
            run = self.store.get_run(request.run_id) if hasattr(self.store, "get_run") else None  # type: ignore[attr-defined]
            return validate_fencing(request, run)
        except Exception as exc:  # noqa: BLE001
            return False, f"{CODE_FENCING_UNAVAILABLE}: fencing check failed: {exc}"

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
    def _effective_impact(self, request: CapabilityRequest, contract: Any, provider_minimum: str | None = None) -> str:
        rule = self.effect_registry.resolve(request.capability) if self.effect_registry is not None else None
        cmin = getattr(contract, "minimum_impact_class", None) if contract else None
        if cmin is None and rule is not None:
            cmin = rule.impact_class
        cmin = cmin or "read"
        req = getattr(request, "effect_class", "read")
        if isinstance(request.metadata, dict) and "requested_effect_class" in request.metadata:
            req2 = request.metadata.get("requested_effect_class")
            if isinstance(req2, str) and req2 in _IMPACT_ORDER and _IMPACT_ORDER.get(req2, 0) > _IMPACT_ORDER.get(req, 0):
                req = req2
        try:
            return compute_effective_impact(cmin, provider_minimum, req)  # type: ignore
        except Exception:
            # A malformed impact must never lower the requirement.  The
            # caller will reject malformed contracts before this point.
            return "irreversible"

    @staticmethod
    def _provider_minimum_impact(descriptor: ProviderDescriptor | None) -> str:
        if descriptor is None:
            return "read"
        mapping = {
            "pure": "read",
            "idempotent": "write-local",
            "deduplicatable": "write-local",
            "reconcilable": "write-remote",
            "irreversible-opaque": "irreversible",
        }
        return mapping.get(str(getattr(descriptor, "side_effect_class", "pure")), "irreversible")

    def check_authorization(
        self,
        request: CapabilityRequest,
        *,
        contract: Any | None = None,
        provider_minimum: str | None = None,
        grants: list[Any] | None = None,
    ) -> tuple[bool, str]:
        try:
            contract = contract or self.contract_registry.resolve(request.capability)
            rule = self.effect_registry.resolve(request.capability) if self.effect_registry is not None else None
        except EffectContractInvalid as exc:
            return False, f"EffectContractInvalid: {exc}"
        except Exception as exc:
            return False, f"contract resolve failed: {exc}"
        req_required = bool(getattr(rule, "authorization_required", False)) if rule is not None else getattr(contract, "authorization_requirement", "required") == "required"
        # A full contract can still carry an explicit requirement when an
        # effect-only rule was not registered.
        req_level = "required" if req_required else getattr(contract, "authorization_requirement", "none")
        if req_level == "none" or req_level == "optional":
            return True, "authorization not required by contract"
        # When qualification refs were supplied, callers are restricted to
        # that authoritative snapshot.  Without refs retain the historical
        # store-backed lookup (the store, never request metadata, remains the
        # source of truth).
        if grants is None:
            if self.store is None or not hasattr(self.store, "list_authorizations"):
                return False, "AuthorizationUnavailable: authorization store unavailable"
            try:
                grants = self.store.list_authorizations()  # type: ignore[attr-defined]
            except Exception as exc:
                return False, f"AuthorizationUnavailable: authorization store failure: {exc}"
        if not grants:
            return False, "AuthorizationRequired: no grants for capability requiring authorization"
        actor = self._extract_actor(request)
        if not actor:
            return False, "AuthorizationRequired: actor missing"
        resource_required = bool(getattr(rule, "resource_required", False)) if rule is not None else bool(getattr(contract, "resource_required", False))
        version_required = bool(getattr(rule, "version_required", False)) if rule is not None else bool(getattr(contract, "subject_version_required", False))
        if resource_required:
            res = self._extract_resource(request)
            if not res:
                return False, "ResourceRequired: resource missing but capability rule requires resource"
        if version_required:
            vers = self._extract_versions(request)
            if not vers:
                return False, "SubjectVersionRequired: subject_version missing but capability rule requires version"
        effective = self._effective_impact(request, contract, provider_minimum)
        from portable_runtime.records.authorization import is_authorized_for  # noqa: PLC0415
        resource = self._extract_resource(request)
        svr = self._extract_versions(request)
        action = CanonicalAuthorizationRequest(
            capability=request.capability,
            resource_ref=resource,
            subject_version_refs=svr,
            actor_ref=actor,
            effect_class=cast(AuthorizationEffectClass, effective),
            lease_generation=_extract_lease_generation(request),
        )
        any_match = False
        for g in grants:
            try:
                if getattr(g, "grantee_ref", None) != actor:
                    continue
                any_match = True
                if is_authorized_for(action, g):
                    return True, "authorized"
            except Exception as exc:
                return False, f"AuthorizationDenied: invalid grant: {exc}"
        if not any_match:
            return False, f"AuthorizationDenied: no grant for actor {actor}"
        return False, f"AuthorizationDenied: no valid grant authorizes {request.capability} with effective_impact {effective} for actor {actor}"

    @staticmethod
    def _error_result(request: CapabilityRequest, code: str, reason: str, *, provider_id: str = "", status: Literal["succeeded", "failed", "unavailable", "needs-input", "cancelled", "unknown"] = "unavailable", **metadata: Any) -> CapabilityResult:
        error: dict[str, Any] = {"code": code, "reason": reason}
        if metadata:
            error.update(metadata)
        return CapabilityResult(request_id=request.id, provider_id=provider_id, status=status, message=reason, error=error)

    @staticmethod
    def _authorization_code(reason: str) -> str:
        for code in (
            CODE_EFFECT_CONTRACT_MISSING,
            CODE_EFFECT_CONTRACT_INVALID,
            CODE_AUTHORIZATION_REQUIRED,
            CODE_AUTHORIZATION_UNAVAILABLE,
            CODE_RESOURCE_REQUIRED,
            CODE_SUBJECT_VERSION_REQUIRED,
            CODE_AUTHORIZATION_DENIED,
        ):
            if reason.startswith(code) or f"{code}:" in reason:
                return code
        return CODE_AUTHORIZATION_DENIED

    @staticmethod
    def _status_entry_satisfied(value: Any, obligation: Any) -> bool:
        """Interpret explicit policy proof metadata, never truthy hints."""

        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value in {"satisfied", "waived", "handed-off", "true", "True"}
        if isinstance(value, dict):
            kind = value.get("kind") or value.get("obligation")
            if kind is not None and str(kind) != str(getattr(obligation, "kind", obligation)):
                return False
            status = value.get("status")
            if status in {"satisfied", "waived", "handed-off"}:
                if status == "waived" and not value.get("waiver_authority_ref"):
                    return False
                if status == "waived" and getattr(obligation, "waivable", True) is False:
                    return False
                if status == "handed-off":
                    return bool(value.get("handoff_ref") or value.get("authority_ref"))
                return True
            return bool(value.get("satisfied") is True)
        return False

    def _policy_obligations_satisfied(
        self,
        request: CapabilityRequest,
        decision: Any,
        assessment: AssessmentContext | None = None,
    ) -> tuple[bool, str]:
        obligations = list(getattr(decision, "obligations", None) or [])
        if not obligations:
            return True, "no policy obligations"
        metadata = request.metadata if isinstance(request.metadata, dict) else {}
        # Inline obligation facts are rejected while resolving AssessmentContext.
        # Only the immutable authoritative snapshot can satisfy this gate.
        proofs: Any = None
        if assessment is not None:
            proofs = assessment.proofs.get("obligation_proofs")
        if proofs is None:
            proofs = metadata.get("obligation_refs") or metadata.get("policy_obligation_refs")
        # Accept explicit proof maps/lists only.  A bare ``requires_approval``
        # flag is a policy input, not proof that the obligation was met.
        for obligation in obligations:
            kind = str(getattr(obligation, "kind", obligation))
            value: Any = None
            if isinstance(proofs, dict):
                value = proofs.get(kind)
            elif isinstance(proofs, list):
                for candidate in proofs:
                    if self._status_entry_satisfied(candidate, obligation):
                        value = candidate
                        break
            # An approval obligation can be proven by a valid, actor-bound
            # grant.  This keeps policy and authorization linked while still
            # requiring a real typed grant rather than a boolean hint.
            if value is None and kind == "approval":
                rule = self.effect_registry.resolve(request.capability) if self.effect_registry is not None else None
                contract = self.contract_registry.resolve(request.capability)
                auth_required = bool(getattr(rule, "authorization_required", False)) or getattr(contract, "authorization_requirement", "none") == "required"
                if auth_required:
                    auth_ok, auth_reason = self.check_authorization(
                        request,
                        contract=contract,
                        grants=(assessment.proofs.get("grants") if assessment and assessment.has_authorization_refs else None),
                    )
                    if auth_ok:
                        continue
                    value = False
                    if auth_reason.startswith(CODE_AUTHORIZATION_UNAVAILABLE):
                        return False, auth_reason
            if not self._status_entry_satisfied(value, obligation):
                return False, f"{CODE_OBLIGATION_UNSATISFIED}: required policy obligation {kind} has no satisfied proof"
        return True, "policy obligations satisfied"

    @staticmethod
    def _procedure_blocked(statuses: Any) -> tuple[bool, str]:
        if hasattr(statuses, "executable"):
            if bool(statuses.executable):
                return False, "procedure executable"
            return True, f"{CODE_PROCEDURE_INCOMPLETE}: procedure assessment is not executable"
        if not isinstance(statuses, list):
            return True, f"{CODE_PROCEDURE_UNAVAILABLE}: procedure checker returned malformed assessment"
        blocking = {"open", "required", "blocked", "expired", "invalidated"}
        bad = [s for s in statuses if getattr(s, "status", None) in blocking]
        if bad:
            names = [str(getattr(s, "obligation", "unknown")) for s in bad]
            return True, f"{CODE_PROCEDURE_INCOMPLETE}: unresolved procedure obligations: {', '.join(names)}"
        return False, "procedure executable"

    @staticmethod
    def _procedure_not_applicable(request: CapabilityRequest, effective: str) -> bool:
        """Accept only an explicit typed applicability proof for pure reads."""

        if effective != "read" or not isinstance(request.metadata, dict):
            return False
        proof = request.metadata.get("procedure_applicability")
        if not isinstance(proof, dict):
            return False
        return (
            proof.get("status") == "not-applicable"
            and proof.get("authority") == "capability-effect-rule"
            and proof.get("capability") == request.capability
            and proof.get("impact_class") == "read"
        )

    def _read_fencing(self, request: CapabilityRequest, store: Any | None) -> tuple[bool, str, str]:
        if request.run_id is None:
            return True, "no run fencing required", ""
        if store is None or not hasattr(store, "get_run"):
            return False, f"{CODE_FENCING_UNAVAILABLE}: fencing store unavailable", CODE_FENCING_UNAVAILABLE
        try:
            run = store.get_run(request.run_id)
        except Exception as exc:
            return False, f"{CODE_FENCING_UNAVAILABLE}: fencing read failed: {exc}", CODE_FENCING_UNAVAILABLE
        if run is None:
            return False, f"{CODE_FENCING_UNAVAILABLE}: run {request.run_id!r} not found", CODE_FENCING_UNAVAILABLE
        try:
            ok, reason = validate_fencing(request, run)
        except Exception as exc:
            return False, f"{CODE_FENCING_UNAVAILABLE}: fencing evaluation failed: {exc}", CODE_FENCING_UNAVAILABLE
        if not ok:
            return False, f"{CODE_FENCING_REJECTED}: {reason}", CODE_FENCING_REJECTED
        return True, reason, ""

    async def execute(self, request: CapabilityRequest, *, capability_service: Any | None = None) -> CapabilityResult:
        """Single fail-closed reality exit for provider side effects.

        Every governance stage returns a typed error before provider lookup or
        invocation.  Once a provider has run, fencing and durable projection
        are checked before a result can retain authoritative ``succeeded``
        status.
        """

        registry = self.registry or (getattr(capability_service, "registry", None) if capability_service else None)
        store = self.store or (getattr(capability_service, "store", None) if capability_service else None)
        routing = self.routing
        if capability_service is not None and getattr(capability_service, "routing", None) is not None:
            routing = capability_service.routing

        assessment: AssessmentContext | None = None

        # Resolve the runtime-owned effect contract before any provider can be
        # selected.  Unknown action-critical capabilities never default to a
        # harmless read.
        try:
            contract = self.contract_registry.resolve(request.capability)
        except EffectContractMissing as exc:
            _append_event(store, CODE_EFFECT_CONTRACT_MISSING, request.id, {"capability": request.capability, "reason": str(exc)})
            return self._error_result(request, CODE_EFFECT_CONTRACT_MISSING, str(exc))
        except EffectContractInvalid as exc:
            _append_event(store, CODE_EFFECT_CONTRACT_INVALID, request.id, {"capability": request.capability, "reason": str(exc)})
            return self._error_result(request, CODE_EFFECT_CONTRACT_INVALID, str(exc))
        except Exception as exc:  # contract store is governance state
            _append_event(store, CODE_EFFECT_CONTRACT_INVALID, request.id, {"capability": request.capability, "reason": str(exc)})
            return self._error_result(request, CODE_EFFECT_CONTRACT_INVALID, f"contract resolution failed: {exc}")

        if registry is None:
            return self._error_result(request, CODE_NO_ELIGIBLE_PROVIDER, "provider registry unavailable")
        try:
            descriptors = registry.descriptors_for(request.capability, request.excluded_provider_ids)
        except Exception as exc:
            return self._error_result(request, CODE_ROUTING_UNAVAILABLE, f"provider discovery failed: {exc}")

        # Provider descriptors contribute a minimum real-world effect.  A
        # non-pure descriptor without an authoritative capability rule is an
        # effect-contract gap, not permission to continue.
        has_non_pure = any(getattr(d, "side_effect_class", "pure") != "pure" for d in descriptors)
        if has_non_pure and (self.effect_registry is None or not self.effect_registry.has_rule(request.capability)):
            reason = f"{CODE_EFFECT_CONTRACT_MISSING}: non-pure provider exposes unregistered capability {request.capability!r}"
            _append_event(store, CODE_EFFECT_CONTRACT_MISSING, request.id, {"capability": request.capability, "reason": reason})
            return self._error_result(request, CODE_EFFECT_CONTRACT_MISSING, reason)
        provider_minimum = "read"
        for descriptor in descriptors:
            candidate = self._provider_minimum_impact(descriptor)
            if _IMPACT_ORDER.get(candidate, 0) > _IMPACT_ORDER.get(provider_minimum, 0):
                provider_minimum = candidate
        try:
            # The authoritative rule and caller request define the required
            # effect ceiling.  Provider metadata may not silently inflate or
            # lower that rule; it is used above only to detect an unregistered
            # non-pure capability.
            effective = self._effective_impact(request, contract, None)
        except Exception as exc:
            return self._error_result(request, CODE_EFFECT_CONTRACT_INVALID, f"effect evaluation failed: {exc}")
        metadata = dict(request.metadata or {})
        metadata["effective_impact"] = effective
        metadata.setdefault("effect_semantics", getattr(contract, "effect_semantics", "pure"))
        if _IMPACT_ORDER.get(effective, 0) > _IMPACT_ORDER.get(getattr(request, "effect_class", "read"), 0):
            request = request.model_copy(update={"effect_class": effective, "metadata": metadata})
        else:
            request = request.model_copy(update={"metadata": metadata})

        # Pre-invocation fencing is mandatory whenever a run is named.
        fence_ok, fence_reason, fence_code = self._read_fencing(request, store)
        if not fence_ok:
            _append_event(store, fence_code, request.id, {"reason": fence_reason, "phase": "pre"})
            _append_event(store, "InvocationBlocked", request.id, {"code": fence_code, "reason": fence_reason, "phase": "pre"})
            return self._error_result(request, fence_code, fence_reason)

        # Resolve all qualification facts once, after fencing but before any
        # gate is evaluated. Metadata is an untrusted transport: proof objects
        # are rejected and only references are dereferenced from the
        # authoritative store.
        if store is not None:
            try:
                assessment = AssessmentContext.resolve(store, request)
            except QualificationResolutionError as exc:
                _append_event(store, CODE_QUALIFICATION_UNAVAILABLE, request.id, {"reason": str(exc)})
                return self._error_result(request, CODE_QUALIFICATION_UNAVAILABLE, str(exc))
            except Exception as exc:  # noqa: BLE001
                _append_event(store, CODE_QUALIFICATION_UNAVAILABLE, request.id, {"reason": str(exc)})
                return self._error_result(request, CODE_QUALIFICATION_UNAVAILABLE, f"qualification resolution failed: {exc}")

        # Policy failures and exceptions are always STOP.  ``require`` is not
        # a log-only decision: every mandatory obligation needs explicit proof.
        if self.policy_engine is not None:
            try:
                from portable_runtime.core.policies import PolicyContext

                ctx = PolicyContext(
                    work_id=request.work_id,
                    capability=request.capability,
                    provider_id=None,
                    payload={"capability": request.capability, "parameters": request.parameters, "instruction": request.instruction},
                    metadata=request.metadata,
                )
                decision = await self.policy_engine.evaluate(ctx)
            except Exception as exc:
                _append_event(store, CODE_POLICY_UNAVAILABLE, request.id, {"reason": str(exc)})
                return self._error_result(request, CODE_POLICY_UNAVAILABLE, f"policy evaluation failed: {exc}")
            if not hasattr(decision, "disposition") or not hasattr(decision, "obligations"):
                _append_event(store, "PolicyEvaluated", request.id, {"status": "invalid"})
                return self._error_result(request, CODE_POLICY_UNAVAILABLE, "policy engine returned malformed decision")
            disposition = getattr(decision, "disposition", None)
            status = getattr(decision, "status", None)
            _append_event(
                store,
                "PolicyEvaluated",
                request.id,
                {"disposition": disposition, "status": status, "obligations": len(getattr(decision, "obligations", []) or [])},
            )
            if disposition == "deny" or status == "deny":
                reason = f"policy denied: {getattr(decision, 'reason', '') or 'deny'}"
                _append_event(store, CODE_POLICY_DENIED, request.id, {"reason": reason})
                _append_event(store, "InvocationBlocked", request.id, {"code": CODE_POLICY_DENIED, "reason": reason})
                return self._error_result(request, CODE_POLICY_DENIED, reason)
            if disposition == "defer":
                reason = f"policy deferred: {getattr(decision, 'reason', '') or 'defer'}"
                _append_event(store, CODE_POLICY_DENIED, request.id, {"reason": reason, "disposition": "defer"})
                _append_event(store, "InvocationBlocked", request.id, {"code": CODE_POLICY_DENIED, "reason": reason})
                return self._error_result(request, CODE_POLICY_DENIED, reason)
            if disposition == "require":
                try:
                    obligations_ok, obligations_reason = self._policy_obligations_satisfied(request, decision, assessment)
                except Exception as exc:
                    _append_event(store, CODE_POLICY_UNAVAILABLE, request.id, {"reason": str(exc), "phase": "obligations"})
                    return self._error_result(request, CODE_POLICY_UNAVAILABLE, f"policy obligation evaluation failed: {exc}")
                if not obligations_ok:
                    code = CODE_AUTHORIZATION_UNAVAILABLE if obligations_reason.startswith(CODE_AUTHORIZATION_UNAVAILABLE) else CODE_OBLIGATION_UNSATISFIED
                    _append_event(store, code, request.id, {"reason": obligations_reason})
                    _append_event(store, "InvocationBlocked", request.id, {"code": code, "reason": obligations_reason})
                    return self._error_result(request, code, obligations_reason)

        # Authorization is driven by the capability rule, not by whether the
        # store happens to contain grants.  Missing/invalid state is a typed
        # denial and never a permissive fallback.
        try:
            auth_ok, auth_reason = self.check_authorization(
                request,
                contract=contract,
                provider_minimum=None,
                grants=(assessment.proofs.get("grants") if assessment and assessment.has_authorization_refs else None),
            )
        except Exception as exc:
            _append_event(store, CODE_AUTHORIZATION_UNAVAILABLE, request.id, {"reason": str(exc)})
            return self._error_result(request, CODE_AUTHORIZATION_UNAVAILABLE, f"authorization evaluation failed: {exc}")
        if not auth_ok:
            code = self._authorization_code(auth_reason)
            _append_event(store, code, request.id, {"reason": auth_reason, "actor": self._extract_actor(request)})
            _append_event(store, "AuthorizationEvaluated", request.id, {"allowed": False, "code": code, "reason": auth_reason})
            return self._error_result(request, code, auth_reason)
        _append_event(store, "AuthorizationEvaluated", request.id, {"allowed": True, "actor": self._extract_actor(request)})

        # Procedure assessment is executable only when every gate is
        # satisfied, waived with authority, or demonstrably handed off.
        if request.work_id and request.run_id and not self._procedure_not_applicable(request, effective):
            try:
                if store is None or not hasattr(store, "get_work") or not hasattr(store, "get_run"):
                    raise RuntimeError("procedure store unavailable")
                work = assessment.work if assessment is not None else store.get_work(request.work_id)
                run = assessment.run if assessment is not None else store.get_run(request.run_id)
                if work is None or run is None:
                    raise RuntimeError("work/run not found for procedure assessment")
                from portable_runtime.workflows.procedure import check_procedure

                effect_rule = self.effect_registry.resolve(request.capability) if self.effect_registry is not None else None
                contract_profile = getattr(contract, "minimum_procedure_profile", "minimal")
                if effect_rule is not None and getattr(effect_rule, "authorization_required", False) and contract_profile == "minimal":
                    contract_profile = "standard"
                work_metadata = getattr(work, "metadata", {}) if isinstance(getattr(work, "metadata", {}), dict) else {}
                run_metadata = getattr(run, "metadata", {}) if isinstance(getattr(run, "metadata", {}), dict) else {}
                profile = metadata.get("procedure_profile") or work_metadata.get("procedure_profile") or run_metadata.get("procedure_profile") or contract_profile
                proof_data = assessment.procedure_proofs() if assessment is not None else {}
                procedure_grants = (
                    assessment.proofs.get("grants")
                    if assessment and assessment.has_authorization_refs
                    else (store.list_authorizations() if hasattr(store, "list_authorizations") else None)
                )
                statuses = check_procedure(
                    work,
                    run,
                    profile,
                    proofs=proof_data,
                    grants=procedure_grants,
                )
                blocked, procedure_reason = self._procedure_blocked(statuses)
            except Exception as exc:
                _append_event(store, CODE_PROCEDURE_UNAVAILABLE, request.id, {"reason": str(exc)})
                return self._error_result(request, CODE_PROCEDURE_UNAVAILABLE, f"procedure evaluation failed: {exc}")
            if blocked:
                _append_event(store, CODE_PROCEDURE_INCOMPLETE, request.id, {"reason": procedure_reason})
                _append_event(store, "ProcedureBlocked", request.id, {"reason": procedure_reason})
                _append_event(store, "InvocationBlocked", request.id, {"code": CODE_PROCEDURE_INCOMPLETE, "reason": procedure_reason})
                return self._error_result(request, CODE_PROCEDURE_INCOMPLETE, procedure_reason)

        # Reliability checks are governance state.  Controller exceptions
        # cannot be interpreted as available capacity.
        # The capability rule owns the action classification.  A provider
        # descriptor that is non-pure is not allowed to downgrade an explicit
        # read rule; it only triggers EffectContractMissing when no rule exists.
        side_effect = _IMPACT_ORDER.get(effective, 0) > _IMPACT_ORDER["read"]
        effect_rule = self.effect_registry.resolve(request.capability) if self.effect_registry is not None else None
        procedure_profile = str(
            metadata.get("procedure_profile")
            or getattr(contract, "minimum_procedure_profile", "minimal")
        )
        requested_blast_radius = _int_or_none(metadata.get("blast_radius"))
        if requested_blast_radius is None:
            requested_blast_radius = _int_or_none(getattr(effect_rule, "blast_radius", None))
        if requested_blast_radius is None:
            requested_blast_radius = _int_or_none(getattr(contract, "blast_radius", None))
        high_impact = effective in {"deploy", "admin", "irreversible"}
        if side_effect and high_impact and requested_blast_radius is None:
            reason = "high-impact capability has no declared blast_radius"
            _append_event(store, CODE_RELIABILITY_BLOCKED, request.id, {"side_effect": True, "reason": reason})
            _append_event(store, "InvocationBlocked", request.id, {"code": CODE_RELIABILITY_BLOCKED, "reason": reason})
            return self._error_result(request, CODE_RELIABILITY_BLOCKED, reason)
        requested_blast_radius = requested_blast_radius or 1
        requested_exposure = _int_or_none(metadata.get("exposure"))
        if requested_exposure is None:
            requested_exposure = _int_or_none(getattr(effect_rule, "exposure", None))
        if requested_exposure is None:
            requested_exposure = _int_or_none(getattr(contract, "exposure", None))
        recovery_timing = metadata.get("recovery_timing")
        if not isinstance(recovery_timing, dict):
            recovery_timing = getattr(effect_rule, "recovery_timing", None) or getattr(contract, "recovery_timing", None)
        irreversible = effective in {"admin", "irreversible"}
        reliability_input = ReliabilityStageInput(
            side_effect=side_effect,
            action_blast_radius=requested_blast_radius,
            exposure=requested_exposure,
            irreversible=irreversible,
            procedure_profile=procedure_profile,
            timing=recovery_timing,
        )
        reliability_decision = evaluate_reliability_stage(self.reliability, reliability_input, _call_supported)
        if reliability_decision.error is not None:
            reliability_error = reliability_decision.error
            _append_event(store, CODE_RELIABILITY_UNAVAILABLE, request.id, {"reason": str(reliability_error)})
            return self._error_result(request, CODE_RELIABILITY_UNAVAILABLE, f"reliability evaluation failed: {reliability_error}")
        if not reliability_decision.allowed:
            reason = reliability_decision.reason or "reliability budget exhausted"
            _append_event(store, CODE_RELIABILITY_BLOCKED, request.id, {"side_effect": side_effect, "reason": reason})
            _append_event(store, "InvocationBlocked", request.id, {"code": CODE_RELIABILITY_BLOCKED, "reason": reason})
            return self._error_result(request, CODE_RELIABILITY_BLOCKED, reason)

        # Provider health, circuit state, independence and hard constraints all
        # run before selection.  Any evaluator exception is RoutingUnavailable.
        selection = await select_provider_stage(registry, routing, request, descriptors, _circuit_for)
        if selection.error is not None:
            selection_error = selection.error
            if selection.error_phase == "eligibility":
                return self._error_result(request, CODE_ROUTING_UNAVAILABLE, f"provider eligibility evaluation failed: {selection_error}")
            _append_event(store, CODE_ROUTING_UNAVAILABLE, request.id, {"reason": str(selection_error)})
            return self._error_result(request, CODE_ROUTING_UNAVAILABLE, f"routing evaluation failed: {selection_error}")
        healthy = list(selection.healthy)
        selected = selection.selected
        if selected is None:
            if healthy and isinstance(request.constraints, dict):
                if request.constraints.get("required_failure_domains") or request.constraints.get("independence_constraints"):
                    _append_event(
                        store,
                        "ProviderRejectedByFailureDomain",
                        request.id,
                        {
                            "capability": request.capability,
                            "required_failure_domains": request.constraints.get("required_failure_domains"),
                            "independence_constraints": request.constraints.get("independence_constraints"),
                        },
                    )
            _append_event(store, CODE_NO_ELIGIBLE_PROVIDER, request.id, {"capability": request.capability})
            _append_event(store, "InvocationBlocked", request.id, {"code": CODE_NO_ELIGIBLE_PROVIDER, "capability": request.capability})
            return self._error_result(request, CODE_NO_ELIGIBLE_PROVIDER, f"no eligible provider for {request.capability}")

        provider_id = selected.id
        _append_event(store, "ProviderSelected", request.id, {"provider_id": provider_id, "capability": request.capability})
        invocation_plan = InvocationStagePlan.from_descriptor(selected)
        side_effect_class: _EffectClass = invocation_plan.side_effect_class
        effect_semantics = invocation_plan.effect_semantics
        if _IMPACT_ORDER.get(effective, 0) > _IMPACT_ORDER["read"]:
            side_effect = True

        # Re-read the same authoritative refs immediately before durable
        # precommit/provider selection is consumed.  This closes the gap
        # between qualification assessment and the sole reality exit.
        if assessment is not None and store is not None:
            try:
                if not assessment.refresh_matches(store, request):
                    reason = "authoritative qualification facts changed during assessment"
                    _append_event(store, CODE_QUALIFICATION_CHANGED, request.id, {"reason": reason, "provider_id": provider_id})
                    return self._error_result(request, CODE_QUALIFICATION_CHANGED, reason, provider_id=provider_id)
            except QualificationResolutionError as exc:
                _append_event(store, CODE_QUALIFICATION_CHANGED, request.id, {"reason": str(exc), "provider_id": provider_id})
                return self._error_result(request, CODE_QUALIFICATION_CHANGED, str(exc), provider_id=provider_id)
            except Exception as exc:  # noqa: BLE001
                _append_event(store, CODE_QUALIFICATION_CHANGED, request.id, {"reason": str(exc), "provider_id": provider_id})
                return self._error_result(request, CODE_QUALIFICATION_CHANGED, f"qualification revalidation failed: {exc}", provider_id=provider_id)
        permit = InvocationPermit.issue(
            request,
            provider_id=provider_id,
            qualification_digest=assessment.digest if assessment is not None else "",
            lease_generation=_extract_lease_generation(request) or 0,
        )
        # From this point onward all precommit, fencing and provider-facing
        # work consumes the permit's reconstructed snapshot, never the
        # caller-owned mutable request object.
        execution_request = permit.materialize_request()
        request = execution_request

        # Precommit is mandatory for all action-critical effects.  A missing
        # durable store or identity is itself a STOP, never a bypass.
        step_id: str | None = None
        attempt_id: str | None = None
        action_id: str | None = None
        if side_effect:
            if store is None or not request.work_id or not request.run_id:
                reason = "side-effect invocation requires durable work/run precommit"
                _append_event(store, CODE_PRECOMMIT_FAILED, request.id, {"reason": reason})
                return self._error_result(request, CODE_PRECOMMIT_FAILED, reason, provider_id=provider_id)
            try:
                if not all(hasattr(store, method) for method in ("save_step", "save_attempt", "save_action")):
                    raise RuntimeError("store lacks precommit methods")
                existing_steps = store.list_steps(request.run_id) if hasattr(store, "list_steps") else []
                step_key = request.step_key or f"{request.capability}:{request.idempotency_key or request.id}"
                step = next((candidate for candidate in existing_steps if candidate.step_key == step_key), None)
                lease_gen = _extract_lease_generation(request) or 0
                if step is None:
                        step = Step(id=new_id("step"), run_id=request.run_id, step_key=step_key, kind=request.capability.split(".")[0] if "." in request.capability else "generic", status="running", effect_semantics=effect_semantics, side_effect_class=side_effect_class, reversibility=invocation_plan.reversibility, input_digest=permit.request_digest, lease_generation=lease_gen)
                else:
                    step = step.model_copy(update={"status": "running", "updated_at": utcnow(), "input_digest": permit.request_digest, "effect_semantics": effect_semantics, "side_effect_class": side_effect_class, "lease_generation": lease_gen, "version": (step.version or 0) + 1})
                step_id = step.id
                attempts = store.list_attempts(step_id) if hasattr(store, "list_attempts") else []
                attempt_no = max((a.attempt_no for a in attempts), default=0) + 1
                attempt = StepAttempt(id=new_id("attempt"), step_id=step_id, attempt_no=attempt_no, provider_id=provider_id, request_ref=request.id, idempotency_key=request.idempotency_key or request.id, status="running", lease_generation=lease_gen)
                attempt_id = attempt.id
                action_id = new_id("action")
                action = Action(id=action_id, work_id=request.work_id, run_id=request.run_id, capability=request.capability, provider_id=provider_id, request_ref=request.id, status="running")
                if hasattr(store, "transaction"):
                    with store.transaction():
                        store.save_step(step)
                        step.current_attempt = attempt_no
                        store.save_step(step)
                        store.save_attempt(attempt)
                        store.save_action(action)
                else:
                    store.save_step(step)
                    step.current_attempt = attempt_no
                    store.save_step(step)
                    store.save_attempt(attempt)
                    store.save_action(action)
                _append_event(
                    store,
                    "StepPrecommitted",
                    request.id,
                    {"step_id": step_id, "attempt_id": attempt_id, "action_id": action_id, "provider_id": provider_id},
                )
            except Exception as exc:
                _append_event(store, CODE_PRECOMMIT_FAILED, request.id, {"reason": str(exc)})
                return self._error_result(request, CODE_PRECOMMIT_FAILED, f"precommit failed: {exc}", provider_id=provider_id)
        else:
            # Pure invocations may still retain execution records where the
            # store supports them, but persistence failures must not create a
            # false authorization path before provider execution.
            if store is not None and request.work_id and request.run_id and hasattr(store, "save_step"):
                try:
                    existing_steps = store.list_steps(request.run_id) if hasattr(store, "list_steps") else []
                    step_key = request.step_key or f"{request.capability}:{request.idempotency_key or request.id}"
                    step = next((candidate for candidate in existing_steps if candidate.step_key == step_key), None)
                    if step is None:
                        step = Step(id=new_id("step"), run_id=request.run_id, step_key=step_key, kind=request.capability.split(".")[0] if "." in request.capability else "generic", status="running", effect_semantics=effect_semantics, side_effect_class=side_effect_class, reversibility=invocation_plan.reversibility, input_digest=permit.request_digest, lease_generation=_extract_lease_generation(request) or 0)
                    else:
                        step = step.model_copy(update={"status": "running", "updated_at": utcnow(), "input_digest": permit.request_digest})
                    step_id = step.id
                    store.save_step(step)
                    if hasattr(store, "save_attempt"):
                        attempt = StepAttempt(id=new_id("attempt"), step_id=step_id, attempt_no=1, provider_id=provider_id, request_ref=request.id, idempotency_key=request.idempotency_key or request.id, status="running", lease_generation=_extract_lease_generation(request) or 0)
                        attempt_id = attempt.id
                        store.save_attempt(attempt)
                except Exception:
                    # Pure observation does not get an action-critical
                    # precommit, so preserve historical best-effort records.
                    step_id = None
                    attempt_id = None

        reliability_started = False
        try:
            _call_supported(
                self.reliability.record_action,
                side_effect=side_effect,
                action_blast_radius=requested_blast_radius,
                exposure=requested_exposure,
            )
            reliability_started = side_effect
        except Exception as exc:
            return self._error_result(request, CODE_RELIABILITY_UNAVAILABLE, f"reliability accounting failed: {exc}", provider_id=provider_id)

        try:
            provider = registry.get(provider_id)
        except Exception as exc:
            if reliability_started and hasattr(self.reliability, "complete_action"):
                _call_supported(self.reliability.complete_action, side_effect=True)
            return self._error_result(request, CODE_ROUTING_UNAVAILABLE, f"provider lookup failed: {exc}", provider_id=provider_id)
        context = InvocationContext(runtime_id=self.runtime_id, work_id=execution_request.work_id, run_id=execution_request.run_id, lease_generation=permit.lease_generation, idempotency_key=execution_request.idempotency_key)
        context.metadata.update(execution_request.metadata or {})
        context.metadata.update(
            {
                "qualification_digest": permit.qualification_digest,
                "invocation_permit_provider": permit.provider_id,
                "invocation_permit_request": permit.request_digest,
            }
        )
        breaker = _circuit_for(provider_id)
        _append_event(store, "InvocationStarted", request.id, {"provider_id": provider_id, "capability": request.capability})
        breaker_state_before = breaker.state
        try:
            result = await provider.invoke(execution_request, context)
        except Exception as exc:
            breaker.record_failure()
            result = CapabilityResult(request_id=request.id, provider_id=provider_id, status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        else:
            if result.status == "failed":
                breaker.record_failure()
            elif result.status == "succeeded":
                breaker.record_success()
        finally:
            if reliability_started and hasattr(self.reliability, "complete_action"):
                _call_supported(self.reliability.complete_action, side_effect=True)
        if breaker.state == "open" and breaker_state_before != "open":
            _append_event(store, "CircuitOpened", request.id, {"provider_id": provider_id, "capability": request.capability})
        _append_event(
            store,
            "InvocationCompleted",
            request.id,
            {"provider_id": provider_id, "status": result.status, "capability": request.capability},
        )

        # Fencing is re-read after every run-bound provider call.  A changed
        # generation/owner/expiry demotes the result to unknown, even when the
        # provider reported success.
        if request.run_id:
            post_ok, post_reason, post_code = self._read_fencing(request, store)
            if not post_ok:
                result = result.model_copy(update={"status": "unknown", "error": {"code": CODE_POST_FENCING_REJECTED if post_code == CODE_FENCING_REJECTED else post_code, "reason": post_reason}})
                if step_id and store is not None:
                    try:
                        step = store.get_step(step_id) if hasattr(store, "get_step") else None
                        if step is not None:
                            store.save_step(step.model_copy(update={"status": "unknown", "updated_at": utcnow()}))
                        attempt_record = store.get_attempt(attempt_id) if attempt_id and hasattr(store, "get_attempt") else None
                        if attempt_record is not None:
                            store.save_attempt(attempt_record.model_copy(update={"status": "unknown", "ended_at": utcnow(), "error": result.error}))
                    except Exception:
                        pass
                _append_event(store, CODE_POST_FENCING_REJECTED, request.id, {"reason": post_reason, "provider_id": provider_id})
                return result

        # Durable projection is part of the authoritative outcome.  A commit
        # failure after provider success is recoverable/unknown, never success.
        if store is not None and step_id is not None:
            try:
                step = store.get_step(step_id) if hasattr(store, "get_step") else None
                attempt_record = store.get_attempt(attempt_id) if attempt_id and hasattr(store, "get_attempt") else None
                projected_status = result.status if result.status in ("succeeded", "failed", "cancelled", "unknown") else "failed"
                if step is None or attempt_record is None:
                    raise RuntimeError("execution projection missing precommitted records")
                step_update = step.model_copy(update={"status": projected_status, "updated_at": utcnow()})
                attempt_update = attempt_record.model_copy(update={"status": projected_status, "ended_at": utcnow(), "result_ref": result.request_id, "error": result.error})
                action = Action(id=action_id or new_id("action"), work_id=request.work_id or "", run_id=request.run_id or "", capability=request.capability, provider_id=provider_id, request_ref=request.id, status=projected_status)
                outcome = Outcome(id=new_id("outcome"), action_id=action.id, artifact_refs=result.output_artifact_refs, evidence_refs=result.evidence_refs, status=projected_status)
                if hasattr(store, "transaction"):
                    with store.transaction():
                        store.save_step(step_update)
                        store.save_attempt(attempt_update)
                        store.save_action(action)
                        store.save_outcome(outcome)
                else:
                    store.save_step(step_update)
                    store.save_attempt(attempt_update)
                    store.save_action(action)
                    store.save_outcome(outcome)
                _append_event(store, "CapabilitySucceeded" if projected_status == "succeeded" else "CapabilityCompleted", request.id, {"provider_id": provider_id, "status": projected_status, "capability": request.capability})
                _append_event(store, "OutcomeRecorded", request.id, {"outcome_id": outcome.id, "status": projected_status, "provider_id": provider_id})
            except Exception as exc:
                # The provider may have changed the world even though the
                # runtime could not persist the projection.  Preserve the
                # uncertainty explicitly.
                reason = f"result commit failed: {exc}"
                _append_event(store, CODE_RESULT_COMMIT_FAILED, request.id, {"reason": reason, "provider_id": provider_id})
                return result.model_copy(update={"status": "unknown", "error": {"code": CODE_RESULT_COMMIT_FAILED, "reason": reason}})
        return result

    async def reconcile(
        self,
        request_id: str,
        provider_id: str,
        *,
        capability_service: Any | None = None,
    ) -> CapabilityResult | None:
        """Perform recovery reconciliation behind the same reality boundary.

        Reconciliation may query an external provider after an ambiguous
        invocation, so callers must not invoke ``provider.reconcile`` directly.
        The method deliberately preserves ``unknown`` when the provider cannot
        establish an authoritative result.
        """

        registry = self.registry or (getattr(capability_service, "registry", None) if capability_service else None)
        if registry is None:
            return self._error_result(
                CapabilityRequest(id=request_id, capability="reconcile"),
                CODE_ROUTING_UNAVAILABLE,
                "provider registry unavailable for reconciliation",
            )
        try:
            provider = registry.get(provider_id)
        except Exception as exc:
            return self._error_result(
                CapabilityRequest(id=request_id, capability="reconcile"),
                CODE_ROUTING_UNAVAILABLE,
                f"provider lookup failed during reconciliation: {exc}",
                provider_id=provider_id,
            )
        reconcile = getattr(provider, "reconcile", None)
        if reconcile is None:
            return None
        try:
            return await reconcile(request_id)
        except Exception as exc:
            return CapabilityResult(
                request_id=request_id,
                provider_id=provider_id,
                status="unknown",
                message=f"reconciliation failed: {exc}",
                error={"code": "ReconciliationUnavailable", "reason": str(exc)},
            )

    async def _execute_legacy(self, request: CapabilityRequest, *, capability_service: Any | None = None) -> CapabilityResult:
        # Kept only as a compatibility shim for callers that reached the old
        # private helper; all execution now uses the strict public path.
        return await self.execute(request, capability_service=capability_service)

        # CapabilityContract resolve + effective impact (never downgrade)
        _contract: Any = None
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
