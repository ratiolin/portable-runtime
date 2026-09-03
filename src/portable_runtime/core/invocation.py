from __future__ import annotations  # noqa: I001
# ruff: noqa: E501

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
_SIDE_EFFECT_IMPACT = {"pure": "read", "idempotent": "write-local", "deduplicatable": "write-local", "reconcilable": "write-remote", "irreversible-opaque": "irreversible"}


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
        if run_id is None or self.store is None:
            return None
        return self.store.get_run(run_id)

    def build(self, capability, *, work_id=None, run_id=None, instruction=None, parameters=None, constraints=None, preferred_provider_ids=None, excluded_provider_ids=None, actor_ref=None, resource_ref=None, subject_version_refs=None, idempotency_key=None, step_key=None, effect_class=None, lease_owner=None, lease_generation=None, metadata=None, timeout_seconds=None, input_artifact_refs=None, request_id=None):
        parameters = parameters or {}
        constraints = constraints or {}
        metadata = dict(metadata or {})
        contract = self.contract_registry.resolve(capability)
        requested_effect = effect_class or metadata.get("effect_class") or "read"
        if requested_effect not in _IMPACT_ORDER:
            requested_effect = "read"
        provider_min = None
        if self.registry is not None:
            effects = [_SIDE_EFFECT_IMPACT.get(d.side_effect_class, "read") for d in self.registry.descriptors_for(capability, [])]
            if effects:
                provider_min = max(effects, key=lambda value: _IMPACT_ORDER[value])
        effective = compute_effective_impact(contract.minimum_impact_class, provider_min, requested_effect)
        fresh_run = self._fresh_run(run_id)
        if fresh_run is not None:
            store_gen = fresh_run.lease_generation or 0
            if isinstance(store_gen, str) and store_gen.isdigit():
                store_gen = int(store_gen)
            if isinstance(store_gen, int):
                lease_generation = store_gen
            if fresh_run.lease_owner is not None:
                lease_owner = fresh_run.lease_owner
        if lease_generation is None:
            lease_generation = 0
        actor_ref = actor_ref or metadata.get("actor_ref")
        resource_ref = resource_ref or metadata.get("resource_ref") or metadata.get("resource")
        if subject_version_refs is None:
            sv = metadata.get("subject_version_refs") or metadata.get("subject_refs")
            if isinstance(sv, list):
                subject_version_refs = [str(x) for x in sv]
            elif isinstance(sv, str):
                subject_version_refs = [sv]
        subject_version_refs = subject_version_refs or []
        independence_context = {}
        if contract.default_independence_requirements:
            independence_context["independent_on"] = list(contract.default_independence_requirements)
        if isinstance(metadata.get("independence_constraints"), dict):
            independence_context.update(metadata["independence_constraints"])
        procedure_profile = compute_effective_procedure_profile(contract.minimum_procedure_profile, metadata.get("procedure_profile"))
        param_hash = _hash_params(capability, instruction, parameters)
        idempotency_key = idempotency_key or (f"{run_id}:{capability}:{param_hash}" if run_id else f"{capability}:{param_hash}:{new_id('idem')}")
        step_key = step_key or f"{capability}:{param_hash}"
        metadata.update(requested_effect_class=requested_effect, effective_impact=effective, effect_semantics=contract.effect_semantics, procedure_profile=procedure_profile)
        if effective == "read" and "procedure_applicability" not in metadata and not metadata.get("procedure_required"):
            metadata["procedure_applicability"] = {"status": "not-applicable", "authority": "capability-effect-rule", "capability": capability, "impact_class": "read"}
        if independence_context:
            metadata["independence_context"] = independence_context
            metadata.setdefault("independence_constraints", independence_context)
        req = CapabilityRequest(id=request_id or new_id("request"), capability=capability, work_id=work_id, run_id=run_id, instruction=instruction, parameters=dict(parameters), constraints=dict(constraints), preferred_provider_ids=list(preferred_provider_ids or []), excluded_provider_ids=list(excluded_provider_ids or []), timeout_seconds=timeout_seconds, metadata=metadata, idempotency_key=idempotency_key, step_key=step_key, actor_ref=actor_ref, resource_ref=resource_ref, subject_version_refs=list(subject_version_refs), effect_class=effective, lease_generation=lease_generation if isinstance(lease_generation, int) else 0, lease_owner=lease_owner)
        if input_artifact_refs:
            req.input_artifact_refs = list(input_artifact_refs)
        return req

    def normalize(self, request, contract=None):
        if contract is not None:
            requested = request.metadata.get("requested_effect_class", request.effect_class)
            effective = compute_effective_impact(contract.minimum_impact_class, None, requested)
            if _IMPACT_ORDER.get(effective, 0) > _IMPACT_ORDER.get(request.effect_class, 0):
                request = request.model_copy(update={"effect_class": effective})
                request.metadata["effective_impact"] = effective
        if request.run_id:
            fresh = self._fresh_run(request.run_id)
            if fresh is not None:
                store_gen = fresh.lease_generation or 0
                if store_gen != request.lease_generation:
                    request = request.model_copy(update={"lease_generation": int(store_gen)})
                if fresh.lease_owner != request.lease_owner:
                    request = request.model_copy(update={"lease_owner": fresh.lease_owner})
        return request

    @staticmethod
    def build_standalone(*args, **kwargs):
        return InvocationFactory().build(*args, **kwargs)
