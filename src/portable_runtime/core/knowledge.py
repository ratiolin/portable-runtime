"""KnowledgeItem helpers and lifecycle."""

from __future__ import annotations

from portable_runtime.core.models import KnowledgeItem


def promote(item: KnowledgeItem) -> KnowledgeItem:
    if item.status == "candidate":
        return item.model_copy(update={"status": "official"})
    return item


def deprecate(item: KnowledgeItem) -> KnowledgeItem:
    return item.model_copy(update={"status": "deprecated"})


def archive(item: KnowledgeItem) -> KnowledgeItem:
    return item.model_copy(update={"status": "archived"})


def candidate_to_official(item: KnowledgeItem) -> KnowledgeItem:
    """Alias used by legacy compat (promote)."""
    return promote(item)
