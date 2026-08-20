"""Policy, knowledge and store conformance for B1-C."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel


class PolicyDecision(BaseModel):
    status: Literal["allow", "deny", "require-approval", "require-verification"]
    reason: str | None = None
    metadata: dict[str, Any] = {}


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
    """Blocks writes to blocked_paths (mirrors ControlPlaneConfig.blocked_paths)."""

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
        target = str(
            payload.get("path", "") or payload.get("target", "") or payload.get("file", "") or ""
        ).lower()
        for blocked in self.blocked_paths:
            if blocked.lower() in target:
                return PolicyDecision(
                    status="deny", reason=f"blocked sensitive path pattern: {blocked}"
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
            status="require-approval", reason="external side effect requires approval"
        )


class CandidateMergePolicy:
    id = "candidate-merge"

    async def evaluate(self, context: PolicyContext) -> PolicyDecision:
        action = (context.action or context.capability or "").lower()
        if "merge" in action or "push" in action:
            return PolicyDecision(
                status="require-verification", reason="merge requires independent verification"
            )
        return PolicyDecision(status="allow")


LegacyPermissionPolicy = SensitivePathPolicy
