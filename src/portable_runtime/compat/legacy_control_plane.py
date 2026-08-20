from __future__ import annotations

from collections.abc import Mapping

from portable_runtime.core.models import Run, Work
from portable_runtime.interfaces.store import StateStore


def import_legacy_repair(row: Mapping[str, object], store: StateStore) -> tuple[Work, Run]:
    """Create stable Work/Run IDs for a legacy repair row."""

    repair_id = str(row.get("id", ""))
    if not repair_id:
        raise ValueError("legacy repair row has no id")
    work = Work(
        id=f"work_legacy_{repair_id}",
        kind="incident",
        title=f"Legacy repair {repair_id}",
        description=str(row.get("payload_json", "")),
        status="completed" if str(row.get("status", "")) in {"closed", "rolled_back"} else "open",
        metadata={"legacy_repair_id": repair_id, "legacy_fingerprint": str(row.get("fingerprint", ""))},
    )
    run = Run(
        id=f"run_legacy_{repair_id}",
        work_id=work.id,
        status="succeeded" if work.status == "completed" else "interrupted",
        workflow_id="incident-repair",
        metadata={"legacy_repair_id": repair_id},
    )
    store.save_work(work)
    store.save_run(run)
    return work, run


def legacy_work_id(repair_id: str) -> str:
    return f"work_legacy_{repair_id}"


def legacy_run_id(repair_id: str) -> str:
    return f"run_legacy_{repair_id}"


def get_legacy_mapping(work: Work) -> dict[str, str] | None:
    rid = work.metadata.get("legacy_repair_id")
    if not rid:
        return None
    return {"legacy_repair_id": str(rid), "work_id": work.id}
