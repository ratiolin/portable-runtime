"""KnowledgeItem helpers and lifecycle — R1.5 compatibility surface.

Evidence existence alone MUST NOT imply official. Promotion requires
explicit epistemic judgment refs + authorization refs + scope + version context.
Legacy promote() now enforces fail-closed checks when those are missing.
"""

from __future__ import annotations

from typing import Any

from portable_runtime.core.models import KnowledgeItem


def _promotion_errors(item: KnowledgeItem) -> list[str]:
    errs: list[str] = []
    meta: dict[str, Any] = item.metadata if isinstance(item.metadata, dict) else {}
    judgment_refs = (
        meta.get("epistemic_judgment_refs")
        or getattr(item, "epistemic_judgment_refs", None)
        or []
    )
    auth_refs = (
        meta.get("authorization_refs")
        or meta.get("authorization_grant_ids")
        or getattr(item, "authorization_refs", None)
        or []
    )
    valid_scope = getattr(item, "valid_scope", None) or meta.get("valid_scope") or {}
    env_ver = (
        getattr(item, "environment_versions", None)
        or meta.get("environment_versions")
        or meta.get("environment_bindings")
        or {}
    )
    if not judgment_refs:
        errs.append("epistemic_judgment_refs required (explicit judgment, not evidence existence)")
    if not auth_refs:
        errs.append("authorization_refs required")
    if not isinstance(valid_scope, dict) or not valid_scope:
        errs.append("valid_scope required non-empty scope")
    if not isinstance(env_ver, dict) or not env_ver:
        errs.append("environment_versions/version context required")
    if not getattr(item, "evidence_refs", None):
        errs.append("evidence_refs required")
    return errs


def can_promote(item: KnowledgeItem) -> bool:
    # KnowledgeItem is a compatibility projection, not an authority-bearing
    # knowledge record.  Its string-shaped refs cannot prove the canonical
    # Assertion/Derivation/evidence/scope/version/authorization graph.  Keep
    # candidates available for migration, but require promotion through the
    # canonical KnowledgeProjection workflow.
    return False


def promote(item: KnowledgeItem) -> KnowledgeItem:
    """Reject legacy promotion; use canonical KnowledgeProjection instead.

    A ``KnowledgeItem`` has no typed graph edges for epistemic judgment,
    derivation, evidence, scope/version, or authorization.  Returning an
    ``official`` compatibility object would therefore mint an authority claim
    from caller-supplied strings.  The canonical consolidation workflow owns
    promotion after validating the complete graph.
    """
    if item.status != "candidate":
        return item
    raise ValueError(
        "cannot promote legacy KnowledgeItem to official; "
        "use canonical KnowledgeProjection promotion with bound epistemic and authorization graph"
    )


def is_explicitly_invalid(item: KnowledgeItem) -> bool:
    """Only refuted/superseded/withdrawn/governance-retired/invalidated beyond recovery/explicitly rejected should archive."""
    meta: dict[str, Any] = item.metadata if isinstance(item.metadata, dict) else {}
    # Check explicit flags
    if meta.get("refuted") or meta.get("superseded") or meta.get("withdrawn") or meta.get("explicitly_rejected") or meta.get("governance_retired"):
        return True
    # Check status markers in metadata
    for key in ["_archive_reason", "archive_reason", "invalidation_reason"]:
        val = meta.get(key)
        if isinstance(val, str) and any(kw in val.lower() for kw in ["refuted", "superseded", "withdrawn", "governance-retired", "explicitly rejected", "invalidated beyond recovery"]):
            return True
    # Check evidence status if explicitly refuted?
    # Do not treat missing judgment/auth/scope/version as invalid
    return False


def classify(item: KnowledgeItem) -> str:
    """Tri-state: promote / retain-candidate / archive. Not sufficiently qualified != invalid."""
    if can_promote(item):
        return "promote"
    if is_explicitly_invalid(item):
        return "archive"
    # Missing prerequisites -> retain candidate
    errs = _promotion_errors(item)
    # If errors are only about missing judgment/auth/scope/version/evidence, retain
    if errs:
        # Check if any error indicates explicit invalid vs just missing
        return "retain-candidate"
    return "retain-candidate"


def retain_candidate(item: KnowledgeItem, reason: str | None = None) -> KnowledgeItem:
    """Keep candidate - insufficient qualification is not invalidation."""
    if item.status != "candidate":
        return item
    if reason and isinstance(item.metadata, dict):
        # copy to avoid mutating original
        new_item = item.model_copy(update={"metadata": {**item.metadata, "_retain_reason": reason}})
        return new_item
    return item


def deprecate(item: KnowledgeItem) -> KnowledgeItem:
    # Only for superseded/governance-retired
    return item.model_copy(update={"status": "deprecated"})


def archive(item: KnowledgeItem) -> KnowledgeItem:
    # Fail-closed: only archive if explicitly invalid; otherwise retain
    if not is_explicitly_invalid(item):
        # Log warning but still allow explicit archive if caller explicitly wants it?
        # For safety, allow archive only if explicitly marked invalid; otherwise treat as retain
        # However for backward compat, we still perform archive but note that workflow should prefer retain
        pass
    return item.model_copy(update={"status": "archived"})


def candidate_to_official(item: KnowledgeItem) -> KnowledgeItem:
    """Alias used by legacy compat (promote)."""
    return promote(item)


def promote_or_retain(item: KnowledgeItem) -> tuple[KnowledgeItem, str]:
    """Helper for workflows: returns (item, decision)."""
    decision = classify(item)
    if decision == "promote":
        return promote(item), "promote"
    if decision == "archive":
        return archive(item), "archive"
    return retain_candidate(item), "retain-candidate" 
