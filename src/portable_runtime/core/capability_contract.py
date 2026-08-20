from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
ImpactClass = Literal["read", "write-local", "write-remote", "deploy", "admin", "irreversible"]
EffectSemantics = Literal["pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"]
AuthorizationRequirement = Literal["none", "optional", "required"]
ProcedureProfileLiteral = Literal["minimal", "standard", "enhanced"]
Reversibility = Literal["reversible", "compensatable", "irreversible", "unknown"]
_IMPACT_ORDER = {"read": 0, "write-local": 1, "write-remote": 2, "deploy": 3, "admin": 4, "irreversible": 5}
class EffectContractInvalid(Exception):  # noqa: N818
    def __init__(self, capability: str, message: str | None = None) -> None:
        self.capability = capability
        super().__init__(message or f"EffectContractInvalid: no contract for capability {capability!r}")
class CapabilityContract(BaseModel):
    model_config = ConfigDict(extra="allow")
    capability: str
    minimum_impact_class: ImpactClass = "read"
    effect_semantics: EffectSemantics = "pure"
    reversibility: Reversibility = "unknown"
    authorization_requirement: AuthorizationRequirement = "required"
    minimum_procedure_profile: ProcedureProfileLiteral = "minimal"
    resource_required: bool = False
    subject_version_required: bool = False
    default_independence_requirements: list[str] = Field(default_factory=list)
    def effective_impact(self, requested: str | None = None, provider_minimum: str | None = None) -> ImpactClass:
        levels = [_IMPACT_ORDER.get(self.minimum_impact_class, 0)]
        if requested and requested in _IMPACT_ORDER:
            levels.append(_IMPACT_ORDER[requested])
        if provider_minimum and provider_minimum in _IMPACT_ORDER:
            levels.append(_IMPACT_ORDER[provider_minimum])
        max_level = max(levels)
        for k, v in _IMPACT_ORDER.items():
            if v == max_level:
                return k  # type: ignore[return-value]
        return self.minimum_impact_class
def _is_side_effect_capability(contract, capability: str) -> bool:
    if contract is not None:
        return contract.minimum_impact_class != "read" or contract.effect_semantics != "pure"
    lower = capability.lower()
    if lower.startswith(("test.read", "observe.", "code.", "verify.", "human.", "reason.")):
        return False
    if lower.endswith(".read"):
        return False
    if any(k in lower for k in ("deploy", "admin", "irreversible", "write", "side_effect")):
        return True
    return False
def compute_effective_impact(contract_minimum, provider_minimum=None, requested=None):
    levels = []
    if contract_minimum in _IMPACT_ORDER:
        levels.append(_IMPACT_ORDER[contract_minimum])
    else:
        levels.append(0)
    if provider_minimum and provider_minimum in _IMPACT_ORDER:
        levels.append(_IMPACT_ORDER[provider_minimum])
    if requested and requested in _IMPACT_ORDER:
        levels.append(_IMPACT_ORDER[requested])
    max_level = max(levels) if levels else 0
    for k, v in _IMPACT_ORDER.items():
        if v == max_level:
            return k  # type: ignore[return-value]
    return contract_minimum  # type: ignore[return-value]
class CapabilityContractRegistry:
    def __init__(self, contracts=None):
        self._contracts = {}
        for c in _builtin_contracts():
            self._contracts[c.capability] = c
        if contracts:
            for c in contracts:
                self._contracts[c.capability] = c
    def register(self, contract):
        self._contracts[contract.capability] = contract
    def resolve(self, capability: str):
        if capability in self._contracts:
            return self._contracts[capability]
        for pattern, contract in self._contracts.items():
            if pattern.endswith(".*") and capability.startswith(pattern[:-2] + "."):
                return contract
            if pattern == "*":
                return contract
        if _is_side_effect_capability(None, capability):
            raise EffectContractInvalid(capability)
        return CapabilityContract(capability=capability, minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[])
    def get_or_none(self, capability: str):
        try:
            return self.resolve(capability)
        except EffectContractInvalid:
            return None
    def list(self):
        return list(self._contracts.values())
def _builtin_contracts():
    return [CapabilityContract(capability="deploy.prod", minimum_impact_class="deploy", effect_semantics="reconcilable", reversibility="compensatable", authorization_requirement="required", minimum_procedure_profile="standard", resource_required=True, subject_version_required=True, default_independence_requirements=["credential_domain", "provider_family"]), CapabilityContract(capability="deploy.*", minimum_impact_class="deploy", effect_semantics="reconcilable", reversibility="compensatable", authorization_requirement="required", minimum_procedure_profile="standard", resource_required=True, subject_version_required=True, default_independence_requirements=["credential_domain", "provider_family"]), CapabilityContract(capability="test.side_effect", minimum_impact_class="write-remote", effect_semantics="reconcilable", reversibility="compensatable", authorization_requirement="required", minimum_procedure_profile="standard", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="test.deploy", minimum_impact_class="deploy", effect_semantics="reconcilable", reversibility="compensatable", authorization_requirement="required", minimum_procedure_profile="standard", resource_required=True, subject_version_required=True, default_independence_requirements=["credential_domain", "provider_family"]), CapabilityContract(capability="test.read", minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="test.write_local", minimum_impact_class="write-local", effect_semantics="idempotent", reversibility="reversible", authorization_requirement="optional", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="test.write_remote", minimum_impact_class="write-remote", effect_semantics="reconcilable", reversibility="compensatable", authorization_requirement="required", minimum_procedure_profile="standard", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="test.admin", minimum_impact_class="admin", effect_semantics="irreversible-opaque", reversibility="irreversible", authorization_requirement="required", minimum_procedure_profile="enhanced", resource_required=True, subject_version_required=False, default_independence_requirements=["credential_domain", "provider_family"]), CapabilityContract(capability="test.irreversible", minimum_impact_class="irreversible", effect_semantics="irreversible-opaque", reversibility="irreversible", authorization_requirement="required", minimum_procedure_profile="enhanced", resource_required=True, subject_version_required=True, default_independence_requirements=["credential_domain", "provider_family"]), CapabilityContract(capability="reason.generate", minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="observe.*", minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="code.*", minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="verify.*", minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="human.*", minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="reason.*", minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[])]
