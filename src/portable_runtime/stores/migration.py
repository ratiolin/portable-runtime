"""Dual-write and migration helpers for legacy repair rows (B2-A).

Keeps legacy SQLite repair rows untouched while also materialising canonical
Work/Run/Event in the portable store. Provides stable ID mapping and
read-switch helpers.
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from typing import Any

from portable_runtime.compat.legacy_control_plane import import_legacy_repair
from portable_runtime.core.models import Event, Run, Work, new_id, utcnow
from portable_runtime.interfaces.store import StateStore


def stable_work_id(repair_id: str) -> str:
    return f"work_legacy_{repair_id}"


def stable_run_id(repair_id: str) -> str:
    return f"run_legacy_{repair_id}"


def dual_write_repair(row: Mapping[str, object], store: StateStore, *, emit_event: bool = True) -> tuple[Work, Run]:
    """Write-through: legacy row stays, portable Work/Run/Event are upserted idempotently."""
    work, run = import_legacy_repair(row, store)
    if emit_event:
        # Record a portable event for observability; ignore if already present
        with contextlib.suppress(Exception):
            store.append_event(
                Event(
                    id=new_id("evt"),
                    type="legacy.repair.dual_write",
                    subject_ref=work.id,
                    payload={"legacy_repair_id": str(row.get("id", "")), "run_id": run.id},
                    created_at=utcnow(),
                )
            )
    return work, run


def get_work_for_legacy_repair(repair_id: str, store: StateStore) -> Work | None:
    return store.get_work(stable_work_id(repair_id))


def list_legacy_mappings(store: StateStore) -> list[dict[str, Any]]:
    """Return legacy_repair_id -> work/run mapping for all portable works that carry legacy metadata."""
    result: list[dict[str, Any]] = []
    for work in store.list_work():
        legacy_id = work.metadata.get("legacy_repair_id")
        if legacy_id:
            result.append({"legacy_repair_id": legacy_id, "work_id": work.id, "status": work.status})
    return result


def import_legacy_batch(rows: list[Mapping[str, object]], store: StateStore) -> list[tuple[Work, Run]]:
    """Bulk import for offline migration scripts."""
    out: list[tuple[Work, Run]] = []
    for row in rows:
        try:
            out.append(dual_write_repair(row, store))
        except Exception:  # noqa: S112
            continue
    return out
