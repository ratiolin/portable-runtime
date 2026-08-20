"""KnowledgeItem helpers and lifecycle — V1.8 strict (P0-3).

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
    return not _promotion_errors(item)


def promote(item: KnowledgeItem) -> KnowledgeItem:
    """Fail-closed promotion: evidence existence alone does NOT allow official."""
    if item.status != "candidate":
        return item
    errs = _promotion_errors(item)
    if errs:
        raise ValueError("cannot promote KnowledgeItem to official: " + "; ".join(errs))
    return item.model_copy(update={"status": "official"})


def deprecate(item: KnowledgeItem) -> KnowledgeItem:
    return item.model_copy(update={"status": "deprecated"})


def archive(item: KnowledgeItem) -> KnowledgeItem:
    return item.model_copy(update={"status": "archived"})


def candidate_to_official(item: KnowledgeItem) -> KnowledgeItem:
    """Alias used by legacy compat (promote)."""
    return promote(item)
