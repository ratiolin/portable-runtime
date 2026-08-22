"""Legacy KnowledgeItem promotion must fail closed at every durable ingress."""

from __future__ import annotations

import pytest

from portable_runtime.core.knowledge import promote
from portable_runtime.core.models import KnowledgeItem
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_legacy_official_knowledge_write_is_rejected(backend: str, tmp_path) -> None:
    store = InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / "legacy-knowledge.db")
    try:
        candidate = KnowledgeItem(
            id=f"legacy_candidate_{backend}",
            kind="doc",
            title="candidate",
            content_ref="external:content",
            status="candidate",
        )
        store.save_knowledge(candidate)

        official = candidate.model_copy(update={"status": "official"})
        with pytest.raises(ValueError, match="canonical KnowledgeProjection"):
            store.save_knowledge(official)
        assert store.get_knowledge(candidate.id).status == "candidate"
    finally:
        if backend == "sqlite":
            store.close()


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_legacy_official_knowledge_import_is_rejected(backend: str, tmp_path) -> None:
    store = InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / "legacy-knowledge-import.db")
    try:
        official = KnowledgeItem(
            id=f"legacy_import_{backend}",
            kind="doc",
            title="official compatibility record",
            content_ref="external:content",
            status="official",
        )
        with pytest.raises(ValueError, match="canonical KnowledgeProjection"):
            store.import_state({"knowledge": [official.model_dump(mode="json")]})
        assert store.get_knowledge(official.id) is None
    finally:
        if backend == "sqlite":
            store.close()


def test_legacy_promote_refuses_to_mint_official_status() -> None:
    item = KnowledgeItem(
        id="legacy_promote",
        kind="doc",
        title="candidate",
        content_ref="external:content",
        status="candidate",
        evidence_refs=["evidence:placeholder"],
        valid_scope={"domain": "test"},
        metadata={
            "epistemic_judgment_refs": ["assertion:placeholder"],
            "authorization_refs": ["grant:placeholder"],
            "environment_versions": {"runtime": "v1"},
        },
    )
    with pytest.raises(ValueError, match="canonical KnowledgeProjection"):
        promote(item)
