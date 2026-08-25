from __future__ import annotations

import hashlib
import json
from typing import Any

from portable_runtime.governance.distinction import AuthorityRequest, FreshnessAnchorLookup
from portable_runtime.records.authorization import (
    AuthorizationGrant,
    AuthorizationUse,
    CanonicalAuthorizationRequest,
    EffectClass,
    create_authorization_use,
    is_authorized_for,
)


def governance_capability(operation: str) -> str:
    return f"governance.{operation}"


def governance_effect_class(operation: str) -> EffectClass:
    if operation in {
        "apply_qualification_transition",
        "apply_activation_transition",
        "apply_review_discharge",
    }:
        return "write-local"
    return "read"


def canonical_authorization_request(request: AuthorityRequest) -> CanonicalAuthorizationRequest:
    versions = (
        [request.target.operational_anchor]
        if request.target.operational_anchor is not None
        else []
    )
    return CanonicalAuthorizationRequest(
        capability=governance_capability(request.operation),
        actor_ref=request.actor,
        resource_ref=request.target.resource_ref,
        subject_version_refs=versions,
        effect_class=governance_effect_class(request.operation),
    )


class CanonicalGovernanceAuthorizationAdapter:
    """Adapt governance authority requests to the existing authorization substrate.

    Policy is intentionally absent from this adapter. A policy allow does not
    create authority; authorization grants remain an independent admission
    requirement.
    """

    def __init__(self, store: Any) -> None:
        self.store = store

    def _grants(self) -> list[AuthorizationGrant]:
        values = self.store.list_authorizations()
        return [value for value in values if isinstance(value, AuthorizationGrant)]

    def __call__(self, request: AuthorityRequest) -> bool:
        canonical = canonical_authorization_request(request)
        return any(is_authorized_for(canonical, grant) for grant in self._grants())

    def materialize_use(self, request: AuthorityRequest) -> AuthorizationUse:
        canonical = canonical_authorization_request(request)
        for grant in self._grants():
            if not is_authorized_for(canonical, grant):
                continue
            use = create_authorization_use(grant, canonical)
            self.store.save_authorization_use(use)
            return use
        raise ValueError("governance authority request is not authorized")


def _canonical_payload_anchor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()}"


class CanonicalFreshnessAdapter:
    """Resolve basis anchors from the canonical runtime state graph.

    The adapter intentionally reads the store on every call. When invoked from
    a SQLite governance commit it reads through the same connection while the
    governance transaction is held, closing the semantic-check/commit gap for
    canonical runtime basis records. Ambiguous IDs fail closed rather than
    selecting a store bucket by iteration order.
    """

    def __init__(self, store: Any) -> None:
        self.store = store

    def __call__(self, basis_ref: str) -> str | None:
        state = self.store.export_state()
        matches = [
            value
            for values in state.values()
            for value in values
            if isinstance(value, dict) and str(value.get("id", "")) == basis_ref
        ]
        if len(matches) != 1:
            return None
        return _canonical_payload_anchor(matches[0])

    def capture(self, basis_refs: list[str] | tuple[str, ...]) -> tuple[tuple[str, str], ...] | None:
        captured: list[tuple[str, str]] = []
        for basis_ref in basis_refs:
            anchor = self(basis_ref)
            if anchor is None:
                return None
            captured.append((basis_ref, anchor))
        return tuple(captured)


def freshness_lookup(store: Any) -> FreshnessAnchorLookup:
    return CanonicalFreshnessAdapter(store)
