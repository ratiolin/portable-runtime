from __future__ import annotations  # noqa: I001
# ruff: noqa: E501, SIM103

from typing import Any, Literal

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


class EffectContractMissing(EffectContractInvalid):  # noqa: N818
    """Raised when a side-effecting capability has no authoritative rule.

    ``EffectContractInvalid`` predates the strict boundary and remains the
    compatibility parent class.  The more specific exception lets the
    runtime distinguish a malformed rule from an absent rule without ever
    treating an unknown side effect as a read.
    """

    def __init__(self, capability: str, message: str | None = None) -> None:
        super().__init__(capability, message or f"EffectContractMissing: no authoritative effect rule for capability {capability!r}")


class CapabilityEffectRule(BaseModel):
    """Minimal runtime-owned effect/authorization rule.

    This is intentionally smaller than the historical capability contract.
    It is the authoritative source used by :class:`RealityBoundary` when it
    decides whether an invocation is action-critical.
    """

    model_config = ConfigDict(extra="allow")

    capability: str
    impact_class: ImpactClass = "read"
    authorization_required: bool = False
    resource_required: bool = False
    version_required: bool = False

    @property
    def subject_version_required(self) -> bool:
        """Compatibility spelling used by ``CapabilityContract``."""

        return self.version_required


class CapabilityEffectRegistry:
    """Small authoritative registry with exact and ``prefix.*`` matching."""

    def __init__(self, rules: list[CapabilityEffectRule] | None = None) -> None:
        self._rules: dict[str, CapabilityEffectRule] = {}
        for rule in rules or _builtin_effect_rules():
            self.register(rule)

    def register(self, rule: CapabilityEffectRule | dict[str, Any]) -> CapabilityEffectRule:
        value = rule if isinstance(rule, CapabilityEffectRule) else CapabilityEffectRule.model_validate(rule)
        self._rules[value.capability] = value
        return value

    def resolve(self, capability: str) -> CapabilityEffectRule | None:
        exact = self._rules.get(capability)
        if exact is not None:
            return exact
        for pattern, rule in self._rules.items():
            if pattern.endswith(".*") and capability.startswith(pattern[:-2] + "."):
                return rule
            if pattern == "*":
                return rule
        return None

    def has_rule(self, capability: str) -> bool:
        return self.resolve(capability) is not None

    def list(self) -> list[CapabilityEffectRule]:
        return list(self._rules.values())


def _builtin_effect_rules() -> list[CapabilityEffectRule]:
    # Keep this registry deliberately small.  More detailed workflow
    # requirements remain in CapabilityContract; these rules only answer the
    # boundary's effect and authorization questions.
    return [
        CapabilityEffectRule(capability="observe.*", impact_class="read"),
        CapabilityEffectRule(capability="verify.*", impact_class="read"),
        CapabilityEffectRule(capability="reason.*", impact_class="read"),
        CapabilityEffectRule(capability="human.*", impact_class="read"),
        CapabilityEffectRule(capability="code.edit", impact_class="write-local", authorization_required=True, resource_required=True, version_required=True),
        CapabilityEffectRule(capability="deploy.*", impact_class="deploy", authorization_required=True, resource_required=True, version_required=True),
        CapabilityEffectRule(capability="test.read", impact_class="read"),
        CapabilityEffectRule(capability="test.side_effect", impact_class="write-remote", authorization_required=True),
        CapabilityEffectRule(capability="test.write_local", impact_class="write-local", authorization_required=True),
        CapabilityEffectRule(capability="test.write_remote", impact_class="write-remote", authorization_required=True),
        CapabilityEffectRule(capability="test.deploy", impact_class="deploy", authorization_required=True, resource_required=True, version_required=True),
        CapabilityEffectRule(capability="test.admin", impact_class="admin", authorization_required=True, resource_required=True),
        CapabilityEffectRule(capability="test.irreversible", impact_class="irreversible", authorization_required=True, resource_required=True, version_required=True),
    ]
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
    def __init__(self, contracts=None, *, effect_registry: CapabilityEffectRegistry | None = None):
        self._contracts = {}
        supplied_effect_rules = effect_registry.list() if effect_registry is not None else []
        self.effect_registry = effect_registry or CapabilityEffectRegistry()
        for c in _builtin_contracts():
            self._contracts[c.capability] = c
            # A contract is also an authoritative effect rule.  Do not let a
            # legacy contract silently disappear from the strict registry.
            self.effect_registry.register(
                CapabilityEffectRule(
                    capability=c.capability,
                    impact_class=c.minimum_impact_class,
                    authorization_required=c.authorization_requirement == "required",
                    resource_required=c.resource_required,
                    version_required=c.subject_version_required,
                )
            )
        if contracts:
            for c in contracts:
                self.register(c)
        # A caller-supplied registry is an explicit runtime authority and
        # therefore wins over compatibility built-ins on exact/pattern match.
        for rule in supplied_effect_rules:
            self.effect_registry.register(rule)
    def register(self, contract):
        self._contracts[contract.capability] = contract
        self.effect_registry.register(
            CapabilityEffectRule(
                capability=contract.capability,
                impact_class=contract.minimum_impact_class,
                authorization_required=contract.authorization_requirement == "required",
                resource_required=contract.resource_required,
                version_required=contract.subject_version_required,
            )
        )

    def register_effect_rule(self, rule: CapabilityEffectRule | dict[str, Any]) -> CapabilityEffectRule:
        """Register the minimal rule without requiring a full contract."""

        value = self.effect_registry.register(rule)
        self._contracts[value.capability] = CapabilityContract(
            capability=value.capability,
            minimum_impact_class=value.impact_class,
            effect_semantics="pure" if value.impact_class == "read" else "reconcilable",
            reversibility="unknown",
            authorization_requirement="required" if value.authorization_required else "none",
            minimum_procedure_profile="standard" if value.authorization_required else "minimal",
            resource_required=value.resource_required,
            subject_version_required=value.version_required,
        )
        return value

    def effect_rule(self, capability: str) -> CapabilityEffectRule | None:
        return self.effect_registry.resolve(capability)

    def has_explicit_rule(self, capability: str) -> bool:
        return self.effect_registry.has_rule(capability)
    def resolve(self, capability: str):
        if capability in self._contracts:
            return self._contracts[capability]
        for pattern, contract in self._contracts.items():
            if pattern.endswith(".*") and capability.startswith(pattern[:-2] + "."):
                return contract
            if pattern == "*":
                return contract
        if _is_side_effect_capability(None, capability):
            raise EffectContractMissing(capability)
        return CapabilityContract(capability=capability, minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[])
    def get_or_none(self, capability: str):
        try:
            return self.resolve(capability)
        except EffectContractInvalid:
            return None
    def list(self):
        return list(self._contracts.values())
def _builtin_contracts():
    return [CapabilityContract(capability="deploy.prod", minimum_impact_class="deploy", effect_semantics="reconcilable", reversibility="compensatable", authorization_requirement="required", minimum_procedure_profile="standard", resource_required=True, subject_version_required=True, default_independence_requirements=["credential_domain", "provider_family"]), CapabilityContract(capability="deploy.*", minimum_impact_class="deploy", effect_semantics="reconcilable", reversibility="compensatable", authorization_requirement="required", minimum_procedure_profile="standard", resource_required=True, subject_version_required=True, default_independence_requirements=["credential_domain", "provider_family"]), CapabilityContract(capability="code.edit", minimum_impact_class="write-local", effect_semantics="idempotent", reversibility="reversible", authorization_requirement="required", minimum_procedure_profile="standard", resource_required=True, subject_version_required=True, default_independence_requirements=[]), CapabilityContract(capability="test.side_effect", minimum_impact_class="write-remote", effect_semantics="reconcilable", reversibility="compensatable", authorization_requirement="required", minimum_procedure_profile="standard", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="test.deploy", minimum_impact_class="deploy", effect_semantics="reconcilable", reversibility="compensatable", authorization_requirement="required", minimum_procedure_profile="standard", resource_required=True, subject_version_required=True, default_independence_requirements=["credential_domain", "provider_family"]), CapabilityContract(capability="test.read", minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="test.write_local", minimum_impact_class="write-local", effect_semantics="idempotent", reversibility="reversible", authorization_requirement="optional", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="test.write_remote", minimum_impact_class="write-remote", effect_semantics="reconcilable", reversibility="compensatable", authorization_requirement="required", minimum_procedure_profile="standard", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="test.admin", minimum_impact_class="admin", effect_semantics="irreversible-opaque", reversibility="irreversible", authorization_requirement="required", minimum_procedure_profile="enhanced", resource_required=True, subject_version_required=False, default_independence_requirements=["credential_domain", "provider_family"]), CapabilityContract(capability="test.irreversible", minimum_impact_class="irreversible", effect_semantics="irreversible-opaque", reversibility="irreversible", authorization_requirement="required", minimum_procedure_profile="enhanced", resource_required=True, subject_version_required=True, default_independence_requirements=["credential_domain", "provider_family"]), CapabilityContract(capability="reason.generate", minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="observe.*", minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="verify.*", minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="human.*", minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[]), CapabilityContract(capability="reason.*", minimum_impact_class="read", effect_semantics="pure", reversibility="unknown", authorization_requirement="none", minimum_procedure_profile="minimal", resource_required=False, subject_version_required=False, default_independence_requirements=[])]
