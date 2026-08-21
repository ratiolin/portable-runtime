from __future__ import annotations  # noqa: I001
# ruff: noqa: E501, SIM102, S110

import hashlib
import json

from portable_runtime.core.capabilities import CapabilityRequest
from portable_runtime.core.capability_contract import (
    CapabilityContractRegistry,
    compute_effective_impact,
    compute_effective_procedure_profile,
)
from portable_runtime.core.models import new_id

_IMPACT_ORDER = {"read": 0, "write-local": 1, "write-remote": 2, "deploy": 3, "admin": 4, "irreversible": 5}
def _hash_params(capability, instruction, parameters):
    payload = json.dumps({"cap": capability, "inst": instruction, "params": parameters}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
class InvocationFactory:
    def __init__(self, store=None, registry=None, contract_registry=None, runtime_id="runtime"):
        self.store = store
        self.registry = registry
        self.contract_registry = contract_registry or CapabilityContractRegistry()
        self.runtime_id = runtime_id
    def _fresh_run(self, run_id):
        if run_id is None or self.store is None or not hasattr(self.store, "get_run"):
            return None
        try:
            return self.store.get_run(run_id)  # type: ignore
        except Exception:
            return None
    def build(self, capability, *, work_id=None, run_id=None, instruction=None, parameters=None, constraints=None, preferred_provider_ids=None, excluded_provider_ids=None, actor_ref=None, resource_ref=None, subject_version_refs=None, idempotency_key=None, step_key=None, effect_class=None, lease_owner=None, lease_generation=None, metadata=None, timeout_seconds=None, input_artifact_refs=None, request_id=None):
        parameters = parameters or {}
        constraints = constraints or {}
        metadata = dict(metadata or {})
        contract = None
        try:
            contract = self.contract_registry.resolve(capability)
        except Exception:
            contract = None
        requested_effect = effect_class or metadata.get("effect_class") or "read"
        if requested_effect not in _IMPACT_ORDER:
            requested_effect = "read"
        contract_min = contract.minimum_impact_class if contract else "read"
        provider_min = None
        if self.registry is not None:
            try:
                descs = self.registry.descriptors_for(capability, [])  # type: ignore
                if descs:
                    mapping = {"pure": "read", "idempotent": "write-local", "deduplicatable": "write-local", "reconcilable": "write-remote", "irreversible-opaque": "irreversible"}
                    prov_effects = [mapping.get(getattr(d, "side_effect_class", "pure"), "read") for d in descs]
                    if prov_effects:
                        provider_min = max(prov_effects, key=lambda x: _IMPACT_ORDER.get(x, 0))
            except Exception:
                provider_min = None
        effective = compute_effective_impact(contract_min, provider_min, requested_effect)  # type: ignore
        fresh_run = self._fresh_run(run_id)
        if fresh_run is not None:
            try:
                gen = getattr(fresh_run, "lease_generation", None)
                owner = getattr(fresh_run, "lease_owner", None)
                if lease_generation is None and isinstance(gen, int):
                    lease_generation = gen
                elif lease_generation is None and isinstance(gen, str) and gen.isdigit():
                    lease_generation = int(gen)
                store_gen = getattr(fresh_run, "lease_generation", 0) or 0
                if isinstance(store_gen, int) and store_gen != lease_generation:
                    lease_generation = store_gen
                if lease_owner is None and isinstance(owner, str):
                    lease_owner = owner
                elif getattr(fresh_run, "lease_owner", None) is not None:
                    if lease_owner != getattr(fresh_run, "lease_owner", None):
                        lease_owner = getattr(fresh_run, "lease_owner", None)
            except Exception:
                pass  # noqa: S110
        if lease_generation is None:
            lease_generation = 0
        if actor_ref is None and isinstance(metadata, dict):
            actor_ref = metadata.get("actor_ref")  # type: ignore
        if resource_ref is None and isinstance(metadata, dict):
            resource_ref = metadata.get("resource_ref") or metadata.get("resource")  # type: ignore
        if subject_version_refs is None and isinstance(metadata, dict):
            sv = metadata.get("subject_version_refs") or metadata.get("subject_refs")
            if isinstance(sv, list):
                subject_version_refs = [str(x) for x in sv]
            elif isinstance(sv, str):
                subject_version_refs = [sv]
        if subject_version_refs is None:
            subject_version_refs = []
        independence_context = {}
        if contract and contract.default_independence_requirements:
            independence_context["independent_on"] = list(contract.default_independence_requirements)
        if "independence_constraints" in metadata and isinstance(metadata["independence_constraints"], dict):
            independence_context.update(metadata["independence_constraints"])
        procedure_profile = compute_effective_procedure_profile(
            contract.minimum_procedure_profile if contract else "minimal",
            metadata.get("procedure_profile"),
        )
        param_hash = _hash_params(capability, instruction, parameters)
        if not idempotency_key:
            idempotency_key = f"{run_id}:{capability}:{param_hash}" if run_id else f"{capability}:{param_hash}:{new_id('idem')}"
        if not step_key:
            step_key = f"{capability}:{param_hash}"
        metadata["requested_effect_class"] = requested_effect
        metadata["effective_impact"] = effective
        metadata["effect_semantics"] = contract.effect_semantics if contract else "pure"
        metadata["procedure_profile"] = procedure_profile
        # A pure/read capability may explicitly prove that the procedure
        # profile is not applicable.  This is a typed applicability record,
        # not a permissive default: callers that set a profile or
        # ``procedure_required`` still go through the procedure checker.
        if (
            effective == "read"
            and "procedure_applicability" not in metadata
            and not metadata.get("procedure_required")
            and contract is not None
        ):
            metadata["procedure_applicability"] = {
                "status": "not-applicable",
                "authority": "capability-effect-rule",
                "capability": capability,
                "impact_class": "read",
            }
        if independence_context:
            metadata["independence_context"] = independence_context
            if "independence_constraints" not in metadata:
                metadata["independence_constraints"] = independence_context
        req = CapabilityRequest(id=request_id or new_id("request"), capability=capability, work_id=work_id, run_id=run_id, instruction=instruction, parameters=dict(parameters), constraints=dict(constraints), preferred_provider_ids=list(preferred_provider_ids or []), excluded_provider_ids=list(excluded_provider_ids or []), timeout_seconds=timeout_seconds, metadata=metadata, idempotency_key=idempotency_key, step_key=step_key, actor_ref=actor_ref, resource_ref=resource_ref, subject_version_refs=list(subject_version_refs), effect_class=effective, lease_generation=int(lease_generation) if isinstance(lease_generation, int) else 0, lease_owner=lease_owner)  # type: ignore
        if input_artifact_refs:
            req.input_artifact_refs = list(input_artifact_refs)
        return req
    def normalize(self, request, contract=None):
        if contract is not None:
            requested = request.metadata.get("requested_effect_class", request.effect_class) if isinstance(request.metadata, dict) else request.effect_class
            effective = compute_effective_impact(contract.minimum_impact_class, None, requested)  # type: ignore
            if _IMPACT_ORDER.get(effective, 0) > _IMPACT_ORDER.get(request.effect_class, 0):
                request = request.model_copy(update={"effect_class": effective})
                if isinstance(request.metadata, dict):
                    request.metadata["effective_impact"] = effective
        if request.run_id:
            fresh = self._fresh_run(request.run_id)
            if fresh is not None:
                try:
                    store_gen = getattr(fresh, "lease_generation", 0) or 0
                    store_owner = getattr(fresh, "lease_owner", None)
                    if store_gen != request.lease_generation:
                        request = request.model_copy(update={"lease_generation": int(store_gen)})
                    if store_owner != request.lease_owner:
                        request = request.model_copy(update={"lease_owner": store_owner})
                except Exception:
                    pass  # noqa: S110
        return request
    @staticmethod
    def build_standalone(*args, **kwargs):
        return InvocationFactory().build(*args, **kwargs)
