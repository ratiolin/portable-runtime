from __future__ import annotations

import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from portable_runtime.core.models import Action
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


@contextmanager
def _store(backend: str, tmp_path: Path) -> Iterator[InMemoryStateStore | SQLiteStateStore]:
    if backend == "memory":
        yield InMemoryStateStore()
        return
    store = SQLiteStateStore(tmp_path / "action-read.db")
    try:
        yield store
    finally:
        store.close()


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_fb2_p1_get_action_returns_typed_durable_action(backend: str, tmp_path: Path) -> None:
    with _store(backend, tmp_path) as store:
        action = Action(
            id="action_fb2_p1",
            work_id="work:external",
            run_id="run:external",
            capability="code.edit",
            provider_id="provider-executor",
            request_ref="request_fb2_p1",
            status="succeeded",
        )
        store.save_action(action)
        loaded = store.get_action(action.id)
        assert loaded == action
        assert store.get_action("missing-action") is None


@pytest.mark.parametrize("store_type", [InMemoryStateStore, SQLiteStateStore])
def test_fb2_p1_action_read_seam_does_not_scrape_export_or_private_storage(store_type: type[object]) -> None:
    source = inspect.getsource(store_type.get_action)
    assert "export_state" not in source
    assert "_records" not in source
    assert "runtime_records" not in source
    assert "_get(" in source
