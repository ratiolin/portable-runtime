"""Policy, knowledge and store conformance for B1-C — extended for workflow hardening.
R1.4 implementation milestone: obligation algebra, disposition, waivable hard
boundaries and explicit backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ObligationKind = Literal[
    "approval",
    "independent_verification",
    "rollback_required",
    "scope_limit",
    "expiration",
    "evidence_required",
    "human_review",
    "revalidation_before_execution",
]

Disposition = Literal["allow", "deny", "defer", "require"]


class Obligation(BaseModel):
    """Single policy obligation. waivable=false is hard boundary (cannot be waived)."""

    model_config = ConfigDict(extra="allow")

    kind: ObligationKind | str
    params: dict[str, Any] = Field(default_factory=dict)
    waivable: bool = True
    description: str | None = None
    reason_refs: list[str] = Field(default_factory=list)
    policy_refs: list[str] = Field(default_factory=list)

    def __hash__(self) -> int:  # type: ignore[override]
        # for set operations; params dict frozen via frozenset
        try:
            return hash((self.kind, tuple(sorted(self.params.items())), self.waivable))
        except Exception:
            return hash(self.kind)


# Convenience constructors
def approval_obligation(required_role: str = "owner", waivable: bool = True) -> Obligation:
    return Obligation(kind="approval", params={"required_role": required_role}, waivable=waivable)


def independent_verification_obligation(
    independent_on: list[str] | None = None, waivable: bool = True
) -> Obligation:
    return Obligation(
        kind="independent_verification",
        params={"independent_on": independent_on or ["provider_family", "credential_domain"]},
        waivable=waivable,
    )


def rollback_required_obligation(waivable: bool = False) -> Obligation:
    return Obligation(kind="rollback_required", waivable=waivable)


def scope_limit_obligation(max_targets: int = 2, waivable: bool = True) -> Obligation:
    return Obligation(kind="scope_limit", params={"max_targets": max_targets}, waivable=waivable)


def expiration_obligation(required: bool = True, waivable: bool = False) -> Obligation:
    return Obligation(kind="expiration", params={"required": required}, waivable=waivable)


def evidence_required_obligation(kind: str = "generic", waivable: bool = True) -> Obligation:
    return Obligation(kind="evidence_required", params={"kind": kind}, waivable=waivable)


def human_review_obligation(waivable: bool = True) -> Obligation:
    return Obligation(kind="human_review", waivable=waivable)


def revalidation_before_execution_obligation(waivable: bool = False) -> Obligation:
    return Obligation(kind="revalidation_before_execution", waivable=waivable)


class PolicyDecision(BaseModel):
    """R1.4 policy decision with disposition + obligations.

    Backward compatibility with status/reason remains explicit.

    New code should use disposition/obligations/reason_refs/policy_refs.
    Old code constructing PolicyDecision(status=...) continues to work via validator.
    """

    model_config = ConfigDict(extra="allow")

    # New R1.4 fields
    disposition: Disposition | None = None
    obligations: list[Obligation] = Field(default_factory=list)
    reason_refs: list[str] = Field(default_factory=list)
    policy_refs: list[str] = Field(default_factory=list)

    # Legacy fields (compat)
    status: Literal["allow", "deny", "require-approval", "require-verification"] | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _sync(self) -> PolicyDecision:
        # If disposition not set but status is, derive disposition
        if self.disposition is None and self.status is not None:
            mapping: dict[str, Disposition] = {
                "allow": "allow",
                "deny": "deny",
                "require-approval": "require",
                "require-verification": "require",
            }
            self.disposition = mapping.get(self.status, "allow")  # type: ignore
            # If require and no obligations, synthesize one for compat
            if self.disposition == "require" and not self.obligations and self.status:
                if self.status == "require-approval":
                    self.obligations = [approval_obligation()]
                elif self.status == "require-verification":
                    self.obligations = [revalidation_before_execution_obligation(waivable=True)]
                if self.reason:
                    self.reason_refs = [self.reason]
                # keep policy_refs empty compat
        # If status not set but disposition is, derive status
        if self.status is None and self.disposition is not None:
            rev: dict[str, Literal["allow", "deny", "require-approval", "require-verification"]] = {
                "allow": "allow",
                "deny": "deny",
                "defer": "require-approval",
                "require": "require-approval",
            }
            # For require with approval vs verification, inspect obligations
            if self.disposition == "require":
                has_approval = any(o.kind == "approval" for o in self.obligations)
                has_verif = any(
                    o.kind in ("revalidation_before_execution", "independent_verification")
                    for o in self.obligations
                )
                if (
                    has_verif
                    and not has_approval
                    and any(o.kind == "revalidation_before_execution" for o in self.obligations)
                ):
                    self.status = "require-verification"
                else:
                    self.status = rev.get(self.disposition, "require-approval")
            else:
                self.status = rev.get(self.disposition, "allow")  # type: ignore
            if not self.reason and self.reason_refs:
                self.reason = ";".join(self.reason_refs)
            elif not self.reason and self.obligations:
                self.reason = f"requires {','.join(o.kind for o in self.obligations)}"
        # Ensure both set
        if self.disposition is None:
            self.disposition = "allow"
        if self.status is None:
            self.status = "allow"
        if self.reason is None and self.reason_refs:
            self.reason = ";".join(self.reason_refs)
        return self

    def is_allow(self) -> bool:
        return self.disposition == "allow"

    def is_deny(self) -> bool:
        return self.disposition == "deny"


@dataclass
class PolicyContext:
    work_id: str | None = None
    capability: str | None = None
    provider_id: str | None = None
    action: str | None = None
    payload: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class Policy:
    id: str

    async def evaluate(self, context: PolicyContext) -> PolicyDecision:
        raise NotImplementedError


class AllowAllPolicy:
    id = "allow-all"

    async def evaluate(self, context: PolicyContext) -> PolicyDecision:
        return PolicyDecision(status="allow", reason="allow-all")


class SensitivePathPolicy:
    id = "sensitive-path"

    def __init__(self, blocked_paths: tuple[str, ...] | None = None) -> None:
        self.blocked_paths = blocked_paths or (
            ".env",
            ".ssh",
            "credentials",
            "secrets",
            "id_rsa",
            ".pem",
            ".key",
            "token",
            "password",
        )

    async def evaluate(self, context: PolicyContext) -> PolicyDecision:
        payload = context.payload or {}
        target = str(payload.get("path", "") or payload.get("target", "") or payload.get("file", "") or "").lower()
        for blocked in self.blocked_paths:
            if blocked.lower() in target:
                return PolicyDecision(
                    disposition="deny",
                    status="deny",
                    reason=f"blocked sensitive path pattern: {blocked}",
                    reason_refs=[f"blocked sensitive path pattern: {blocked}"],
                    policy_refs=[self.id],
                    obligations=[Obligation(kind="scope_limit", params={"blocked": blocked},
                    waivable=False,
                    description="hard boundary: sensitive path",
                )],
                )
        return PolicyDecision(status="allow")


class ExternalSideEffectPolicy:
    id = "external-side-effect"

    def __init__(self, require_approval: bool = False) -> None:
        self.require_approval = require_approval

    async def evaluate(self, context: PolicyContext) -> PolicyDecision:
        if not self.require_approval:
            return PolicyDecision(status="allow")
        if context.capability and context.capability.startswith("verify."):
            return PolicyDecision(status="allow")
        return PolicyDecision(
            disposition="require",
            status="require-approval",
            reason="external side effect requires approval",
            reason_refs=["external side effect requires approval"],
            policy_refs=[self.id],
            obligations=[approval_obligation(required_role="owner")],
        )


class CandidateMergePolicy:
    id = "candidate-merge"

    async def evaluate(self, context: PolicyContext) -> PolicyDecision:
        action = (context.action or context.capability or "").lower()
        if "merge" in action or "push" in action:
            return PolicyDecision(
                disposition="require",
                status="require-verification",
                reason="merge requires independent verification",
                reason_refs=["merge requires independent verification"],
                policy_refs=[self.id],
                obligations=[independent_verification_obligation(independent_on=["provider_family"])],
            )
        return PolicyDecision(status="allow")


LegacyPermissionPolicy = SensitivePathPolicy


class WorkflowPolicyConfig(BaseModel):
    requires_approval: bool = False
    strict_verify: bool = False
    sensitive_keywords: tuple[str, ...] = ("sensitive", "secret", "credentials", "production")
    policy_metadata_key: str = "policy"


def _extract_policy_config(metadata: dict[str, Any] | None) -> WorkflowPolicyConfig:
    if not metadata:
        return WorkflowPolicyConfig()
    policy_block = metadata.get("policy") if isinstance(metadata.get("policy"), dict) else {}
    if not isinstance(policy_block, dict):
        policy_block = {}
    requires_approval = bool(metadata.get("requires_approval", False) or policy_block.get("requires_approval", False))
    strict_verify = bool(metadata.get("strict_verify", False) or policy_block.get("strict_verify", False))
    return WorkflowPolicyConfig(requires_approval=requires_approval, strict_verify=strict_verify)


def _work_title_lower(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    return str(payload.get("title", "")).lower()


class ApprovalGatePolicy:
    id = "approval-gate"

    def __init__(self, config: WorkflowPolicyConfig | None = None) -> None:
        self.config = config or WorkflowPolicyConfig()

    async def evaluate(self, context: PolicyContext) -> PolicyDecision:
        payload = context.payload or {}
        work_metadata = payload.get("_work_metadata") if isinstance(payload.get("_work_metadata"), dict) else None
        if isinstance(work_metadata, dict):
            merged = _extract_policy_config(work_metadata)
            effective_requires_approval = merged.requires_approval or self.config.requires_approval
        else:
            merged = _extract_policy_config(payload)
            effective_requires_approval = merged.requires_approval or self.config.requires_approval
        title_lower = _work_title_lower(payload)
        sensitive = any(kw.lower() in title_lower for kw in self.config.sensitive_keywords)
        if effective_requires_approval or sensitive:
            reason = (
                "explicit requires_approval flag" if effective_requires_approval else "title contains sensitive keyword"
            )
            return PolicyDecision(
                disposition="require",
                status="require-approval",
                reason=reason,
                reason_refs=[reason],
                policy_refs=[self.id],
                obligations=[approval_obligation(required_role="owner")],
            )
        return PolicyDecision(status="allow", reason="no approval required")


class StrictVerificationPolicy:
    id = "strict-verification"

    def __init__(self, config: WorkflowPolicyConfig | None = None) -> None:
        self.config = config or WorkflowPolicyConfig()

    async def evaluate(self, context: PolicyContext) -> PolicyDecision:
        payload = context.payload or {}
        work_metadata = payload.get("_work_metadata") if isinstance(payload.get("_work_metadata"), dict) else None
        if isinstance(work_metadata, dict):
            merged = _extract_policy_config(work_metadata)
            effective = merged.strict_verify or self.config.strict_verify
        else:
            merged = _extract_policy_config(payload)
            effective = merged.strict_verify or self.config.strict_verify
        if effective:
            return PolicyDecision(
                disposition="require",
                status="require-verification",
                reason="strict_verify enabled",
                reason_refs=["strict_verify enabled"],
                policy_refs=[self.id],
                obligations=[revalidation_before_execution_obligation(waivable=True)],
            )
        return PolicyDecision(status="allow", reason="strict_verify disabled")


def _detect_obligation_conflict(obligations: list[Obligation]) -> bool:
    """Detect conflicting requirements: same kind with incompatible params."""
    by_kind: dict[str, list[Obligation]] = {}
    for o in obligations:
        by_kind.setdefault(str(o.kind), []).append(o)
    for _kind, lst in by_kind.items():
        if len(lst) <= 1:
            continue
        # If any two have differing params, treat as conflict (conservative)
        seen: set[str] = set()
        for o in lst:
            # hashable representation
            try:
                key = str(tuple(sorted(o.params.items())))
            except Exception:
                key = str(o.params)
            seen.add(key)
        if len(seen) > 1:
            return True
    return False


@dataclass
class PolicyEngine:
    policies: list[Any] = field(default_factory=list)

    async def evaluate(self, context: PolicyContext) -> PolicyDecision:
        """R1.4 algebra: deny > defer > requirements-union > allow."""
        decisions: list[PolicyDecision] = []
        for policy in self.policies:
            dec = await policy.evaluate(context)  # type: ignore
            # Normalize via validator (ensure disposition)
            if isinstance(dec, PolicyDecision):
                # trigger validator sync if needed
                dec = PolicyDecision.model_validate(dec.model_dump())
            decisions.append(dec)

        # deny takes precedence
        for dec in decisions:
            if dec.disposition == "deny" or dec.status == "deny":
                return dec

        # defer takes next
        for dec in decisions:
            if dec.disposition == "defer":
                return dec

        # collect require obligations
        required: list[Obligation] = []
        reason_refs: list[str] = []
        policy_refs: list[str] = []
        for dec in decisions:
            if dec.disposition == "require":
                required.extend(dec.obligations)
                reason_refs.extend(dec.reason_refs or ([dec.reason] if dec.reason else []))
                policy_refs.extend(dec.policy_refs or [getattr(dec, "id", "")])

        if required:
            # dedup obligations by kind+params
            uniq: list[Obligation] = []
            seen_keys: set[str] = set()
            for o in required:
                key = f"{o.kind}:{sorted(o.params.items())}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    uniq.append(o)
                else:
                    # duplicate same obligation, keep one
                    pass
            # conflict detection
            if _detect_obligation_conflict(uniq):
                return PolicyDecision(
                    disposition="deny",
                    status="deny",
                    reason="policy-conflict: conflicting obligations",
                    reason_refs=["policy-conflict"] + reason_refs,
                    policy_refs=policy_refs,
                    obligations=uniq,
                    metadata={"conflict": True, "blocked": True},
                )
            return PolicyDecision(
                disposition="require",
                status="require-approval" if any(o.kind == "approval" for o in uniq) else "require-verification",
                reason=";".join(reason_refs) if reason_refs else "requires obligations",
                reason_refs=reason_refs,
                policy_refs=policy_refs,
                obligations=uniq,
            )

        # legacy fallback: check old status require strings (for policies that bypass disposition)
        require_decision: PolicyDecision | None = None
        for dec in decisions:
            if dec.status in ("require-approval", "require-verification") and require_decision is None:
                require_decision = dec
        if require_decision is not None:
            return require_decision
        return PolicyDecision(disposition="allow", status="allow", reason="all policies allow")

    async def requires_approval(self, context: PolicyContext) -> bool:
        decision = await self.evaluate(context)
        return decision.status == "require-approval" or (decision.disposition == "require" and any(o.kind == "approval" for o in decision.obligations))

    async def requires_verification(self, context: PolicyContext) -> bool:
        decision = await self.evaluate(context)
        return decision.status == "require-verification" or (decision.disposition == "require" and any(o.kind in ("revalidation_before_execution", "independent_verification") for o in decision.obligations))

    def with_policy(self, policy: Any) -> PolicyEngine:
        return PolicyEngine(policies=[*self.policies, policy])


def build_incident_policy_context(
    work_id: str | None = None,
    work_title: str | None = None,
    work_metadata: dict[str, Any] | None = None,
    capability: str | None = None,
) -> PolicyContext:
    payload: dict[str, Any] = {}
    if work_title is not None:
        payload["title"] = work_title
    if work_metadata is not None:
        payload["_work_metadata"] = work_metadata
        for key in ("requires_approval", "strict_verify", "policy"):
            if key in work_metadata:
                payload[key] = work_metadata[key]
    return PolicyContext(work_id=work_id, capability=capability, payload=payload, metadata=work_metadata)


def create_default_incident_policy_engine(config: WorkflowPolicyConfig | None = None) -> PolicyEngine:
    cfg = config or WorkflowPolicyConfig()
    return PolicyEngine(policies=[ApprovalGatePolicy(cfg), StrictVerificationPolicy(cfg)])

