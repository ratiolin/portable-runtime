"""AuthorizationGrant — V1.4 Authorization isolated from Decision.

Invariant: patch v1 approved MUST NOT be reused for patch v2. Checked via subject_version_refs.

This module is Batch4 — does not touch Batch2/3 files.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portable_runtime.core.models import new_id, utcnow


class AuthorizationGrant(BaseModel):
    """Authorization that allows a grantee to make a decision effective.

    Separated from Decision (who chose what) per V1.4 §9.1.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: new_id("authz"))
    created_at: datetime = Field(default_factory=utcnow)
    principal_ref: str = Field(description="who grants, e.g. human owner or policy")
    grantee_ref: str = Field(description="who is allowed to act")
    allowed_capabilities: list[str] = Field(
        default_factory=list,
        description="capabilities allowed, e.g. code.edit, merge",
    )
    resource_scope: list[str] = Field(default_factory=list, description="resource scope, paths or resource ids")
    effect_ceiling: str | None = Field(default=None, description="max effect, e.g. read/write/admin")
    valid_from: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = Field(default=None)
    conditions: list[str] = Field(default_factory=list, description="free-form conditions, e.g. requires verification")
    revocable: bool = True
    revoked_at: datetime | None = None
    source_decision_ref: str | None = Field(default=None, description="Decision that produced this grant")
    subject_version_refs: list[str] = Field(
        default_factory=list,
        description="versions this grant covers; invariant v1 != v2",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_time(self) -> AuthorizationGrant:
        if self.expires_at is not None and self.expires_at < self.valid_from:
            raise ValueError("expires_at must be >= valid_from")
        return self


def _norm_cap(cap: str) -> str:
    return cap.strip().lower()


def _capability_matches(allowed: list[str], requested: str) -> bool:
    """Support wildcard e.g. code.* or * or exact."""
    if not allowed:
        return False
    req = _norm_cap(requested)
    for pat in allowed:
        p = _norm_cap(pat)
        if p == "*" or p == req:
            return True
        if p.endswith(".*"):
            prefix = p[:-2]
            if req == prefix or req.startswith(prefix + "."):
                return True
        # also allow prefix like "code.edit" matches "code.edit"
    return False


def _resource_matches(scope: list[str], resource: str | None) -> bool:
    if not scope:
        return True  # empty means no restriction
    if resource is None or resource == "":
        return True  # if action has no resource, scope does not block
    res = resource.lower()
    for s in scope:
        sl = s.lower()
        if sl == "*" or sl in res or res in sl:
            return True
        # allow exact prefix match
        if res.startswith(sl) or sl.startswith(res):
            return True
    return False


def validate_grant(grant: AuthorizationGrant, *, now: datetime | None = None) -> list[str]:
    """Validate grant invariants, return list of error strings (empty = valid)."""
    errors: list[str] = []
    ts = now or datetime.now(UTC)
    if grant.revoked_at is not None:
        errors.append(f"grant {grant.id} has been revoked at {grant.revoked_at.isoformat()}")
    if grant.expires_at is not None and ts >= grant.expires_at:
        errors.append(f"grant {grant.id} expired at {grant.expires_at.isoformat()}")
    if ts < grant.valid_from:
        errors.append(f"grant {grant.id} not yet valid until {grant.valid_from.isoformat()}")
    if not grant.principal_ref:
        errors.append("principal_ref required")
    if not grant.grantee_ref:
        errors.append("grantee_ref required")
    if not grant.allowed_capabilities:
        errors.append("allowed_capabilities must not be empty")
    # subject_version_refs invariant: grant must declare at least one version if it authorizes versioned subject
    # Not hard error for generic grants, but warn if empty when effect_ceiling suggests patch
    return errors


def is_grant_valid(grant: AuthorizationGrant, *, now: datetime | None = None) -> bool:
    return not validate_grant(grant, now=now)


def _extract_action_fields(action: Any) -> tuple[str, str | None, list[str]]:
    """Extract (capability, resource, subject_versions) from various action shapes."""
    capability = ""
    resource: str | None = None
    subject_versions: list[str] = []
    if isinstance(action, dict):
        capability = str(action.get("capability", "") or action.get("cap", "") or action.get("action", ""))
        resource = action.get("resource") or action.get("resource_scope") or action.get("path") or action.get("target")
        if isinstance(resource, list):
            resource = resource[0] if resource else None
        # version refs
        vs = action.get("subject_version_refs") or action.get("subject_refs") or action.get("version_refs") or action.get("versions")
        if isinstance(vs, str):
            subject_versions = [vs]
        elif isinstance(vs, list):
            subject_versions = [str(x) for x in vs]
        # also try action["metadata"] subject
        if not subject_versions and isinstance(action.get("metadata"), dict):
            md = action["metadata"]
            v2 = md.get("subject_version_refs") or md.get("version")
            if isinstance(v2, str):
                subject_versions = [v2]
            elif isinstance(v2, list):
                subject_versions = [str(x) for x in v2]
    else:
        # pydantic / dataclass object
        capability = str(getattr(action, "capability", "") or getattr(action, "cap", "") or getattr(action, "action", "") or "")
        resource = getattr(action, "resource", None) or getattr(action, "target", None) or getattr(action, "path", None)
        vs = getattr(action, "subject_version_refs", None) or getattr(action, "subject_refs", None) or getattr(action, "version_refs", None)
        if isinstance(vs, str):
            subject_versions = [vs]
        elif isinstance(vs, list):
            subject_versions = [str(x) for x in vs]
        # metadata fallback
        if not subject_versions:
            md = getattr(action, "metadata", None) or getattr(action, "payload", None)
            if isinstance(md, dict):
                v2 = md.get("subject_version_refs") or md.get("version")
                if isinstance(v2, str):
                    subject_versions = [v2]
                elif isinstance(v2, list):
                    subject_versions = [str(x) for x in v2]
    return capability, resource, subject_versions


def is_authorized_for(
    action: Any,
    grant: AuthorizationGrant,
    *,
    now: datetime | None = None,
) -> bool:
    """Check whether grant authorizes action.

    Invariants enforced:
    - revoked / expired / not-yet-valid -> false
    - capability must be in allowed_capabilities (wildcard supported)
    - resource must be within resource_scope if scope non-empty
    - subject_version_refs: if action carries version refs, they must intersect grant.subject_version_refs
      (patch v1 approved cannot carry to patch v2)
    """
    ts = now or datetime.now(UTC)
    if grant.revoked_at is not None:
        return False
    if grant.expires_at is not None and ts >= grant.expires_at:
        return False
    if ts < grant.valid_from:
        return False

    capability, resource, subject_versions = _extract_action_fields(action)
    if not capability:
        # if action has no capability, cannot be authorized
        return False
    if not _capability_matches(grant.allowed_capabilities, capability):
        return False
    if not _resource_matches(grant.resource_scope, resource):
        return False
    # effect_ceiling could be checked against action effect, but if grant has ceiling, treat as metadata constraint
    # For now, enforce that if action requests higher effect than ceiling, deny. Simplified: ceiling string equality not enforced
    # Version binding — the hard invariant
    if subject_versions:
        if not grant.subject_version_refs:
            # grant does not bind to any version -> cannot authorize versioned subject (must be explicit)
            return False
        # must have at least one overlapping version
        if not any(v in grant.subject_version_refs for v in subject_versions):
            return False
    # if grant has subject_version_refs but action has no version (e.g. generic action), allow
    # conditions are not auto-evaluated here; caller may check separately
    return True


def is_authorized_for_any(action: Any, grants: list[AuthorizationGrant], *, now: datetime | None = None) -> bool:
    return any(is_authorized_for(action, g, now=now) for g in grants)


def create_grant_for_approval(
    *,
    principal_ref: str,
    grantee_ref: str,
    allowed_capabilities: list[str],
    subject_version_refs: list[str],
    source_decision_ref: str | None = None,
    resource_scope: list[str] | None = None,
    effect_ceiling: str | None = None,
    ttl_seconds: float | None = 3600,
    conditions: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuthorizationGrant:
    """Helper to create a time-bound grant for a human approval."""
    now = utcnow()
    expires: datetime | None = None
    if ttl_seconds is not None:
        from datetime import timedelta
        expires = now + timedelta(seconds=ttl_seconds)
    return AuthorizationGrant(
        principal_ref=principal_ref,
        grantee_ref=grantee_ref,
        allowed_capabilities=allowed_capabilities,
        resource_scope=resource_scope or [],
        effect_ceiling=effect_ceiling,
        valid_from=now,
        expires_at=expires,
        conditions=conditions or [],
        revocable=True,
        source_decision_ref=source_decision_ref,
        subject_version_refs=subject_version_refs,
        metadata=metadata or {},
    )


def record_human_approval(
    store: Any,
    *,
    decision_id: str | None = None,
    principal_ref: str,
    grantee_ref: str,
    allowed_capabilities: list[str],
    subject_version_refs: list[str],
    work_id: str | None = None,
    source_decision_ref: str | None = None,
    resource_scope: list[str] | None = None,
    ttl_seconds: float | None = 3600,
) -> tuple[Any, AuthorizationGrant]:
    """Create Decision + AuthorizationGrant for human.approve hook.

    Returns (Decision, AuthorizationGrant). Persists both via store if possible.
    The Decision is a lightweight portable_runtime.core.models.Decision.
    """
    from portable_runtime.core.models import Decision

    dec_id = decision_id or new_id("decision")
    decision = Decision(
        id=dec_id,
        work_id=work_id or grantee_ref,
        decision_type="human-approval",
        selected_option="approved",
        authorized_by=[principal_ref],
    )
    # persist decision if store supports it
    try:
        if hasattr(store, "save_decision"):
            store.save_decision(decision)  # type: ignore
        elif hasattr(store, "_save") and hasattr(store, "_records"):
            # fallback to internal
            store._records.setdefault("decision", {})[decision.id] = decision  # type: ignore
    except Exception:
        pass

    grant = create_grant_for_approval(
        principal_ref=principal_ref,
        grantee_ref=grantee_ref,
        allowed_capabilities=allowed_capabilities,
        subject_version_refs=subject_version_refs,
        source_decision_ref=source_decision_ref or decision.id,
        resource_scope=resource_scope,
        ttl_seconds=ttl_seconds,
    )
    # persist grant
    try:
        if hasattr(store, "save_authorization"):
            store.save_authorization(grant)  # type: ignore
        elif hasattr(store, "save_record"):
            # also save as generic record for traceability if needed
            pass
        # always stash in _records for in-memory inspection
        if hasattr(store, "_records"):
            store._records.setdefault("authorization", {})[grant.id] = grant  # type: ignore
    except Exception:
        pass
    # also stash in Decision metadata for audit
    try:
        decision.metadata["authorization_grant_id"] = grant.id  # type: ignore
        decision.metadata["subject_version_refs"] = subject_version_refs  # type: ignore
    except Exception:
        pass
    return decision, grant

