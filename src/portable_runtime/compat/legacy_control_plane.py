from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Literal

from portable_runtime.core.models import Run, Work
from portable_runtime.interfaces.store import StateStore


def import_legacy_repair(row: Mapping[str, object], store: StateStore) -> tuple[Work, Run]:
    """Create stable Work/Run IDs for a legacy repair row."""

    repair_id = str(row.get("id", ""))
    if not repair_id:
        raise ValueError("legacy repair row has no id")
    payload_kind = ""
    payload_raw = str(row.get("payload_json", "") or "")
    try:
        payload = json.loads(payload_raw)
    except (TypeError, ValueError):
        payload = {}
    if isinstance(payload, Mapping):
        payload_kind = str(payload.get("kind", "") or "").strip().lower()

    # Explicit personal task rows must retain their task workflow identity
    # when projected from the legacy repair namespace.  Historical alert rows
    # continue to use the incident compatibility projection.
    is_personal_task = payload_kind == "task"
    work_kind = "generic-task" if is_personal_task else "incident"
    workflow_id = "personal-task" if is_personal_task else "incident-repair"
    metadata = {
        "legacy_repair_id": repair_id,
        "legacy_fingerprint": str(row.get("fingerprint", "")),
    }
    if is_personal_task:
        metadata.update(
            {
                "canonical_workflow": "personal-task",
                "task_prompt": str(payload.get("prompt", "") or ""),
                "task_repo": str(payload.get("repo", "") or ""),
            }
        )

    legacy_terminal = str(row.get("status", "")) in {"closed", "rolled_back"}
    # A legacy closed flag is not a typed completion proof.  Preserve it as
    # provenance and keep the canonical graph non-terminal until a verifier
    # re-establishes the actual outcome.
    if legacy_terminal:
        metadata["legacy_terminal_status"] = str(row.get("status", ""))
    canonical_work_status: Literal["open", "waiting", "completed"] = (
        "waiting" if (is_personal_task or legacy_terminal) else "open"
    )
    work = Work(
        id=f"work_legacy_{repair_id}",
        kind=work_kind,
        title=f"Legacy repair {repair_id}",
        description=(str(payload.get("prompt", "")) if is_personal_task else payload_raw),
        status=canonical_work_status,
        metadata=metadata,
    )
    run = Run(
        id=f"run_legacy_{repair_id}",
        work_id=work.id,
        status=("waiting" if (is_personal_task or legacy_terminal) else "interrupted"),
        workflow_id=workflow_id,
        metadata={"legacy_repair_id": repair_id, "canonical_workflow": workflow_id},
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
