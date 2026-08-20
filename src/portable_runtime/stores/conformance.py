"""Store conformance tests - ensures any StateStore can pass core tests."""

import tempfile
from pathlib import Path

from portable_runtime.core.models import Work
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


def _run_crud(store) -> None:  # noqa: S101
    w = Work(id="work_test", title="t", description="d", kind="generic-task")
    store.save_work(w)
    assert store.get_work("work_test") is not None  # noqa: S101
    store.save_work(w.model_copy(update={"title": "t2"}))
    assert store.get_work("work_test").title == "t2"  # noqa: S101
    state = store.export_state()
    if isinstance(store, SQLiteStateStore):
        fd, tmp_path = tempfile.mkstemp(suffix=".db")  # noqa: S306,S5445
        import os as _os

        _os.close(fd)
        tmp = Path(tmp_path)
        fresh: SQLiteStateStore = SQLiteStateStore(tmp)
        try:
            fresh.import_state(state)
            assert fresh.get_work("work_test") is not None  # noqa: S101
        finally:
            fresh.close()
            tmp.unlink(missing_ok=True)
    else:
        fresh2: InMemoryStateStore = InMemoryStateStore()
        fresh2.import_state(state)
        assert fresh2.get_work("work_test") is not None  # noqa: S101
