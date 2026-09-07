"""Portable local deployment factory and Windows profile adapter (§56-§57)."""

from __future__ import annotations

from pathlib import Path

from portable_runtime.core.runtime import Runtime
from portable_runtime.stores.filesystem import FilesystemArtifactStore
from portable_runtime.stores.sqlite import SQLiteStateStore


def create_local_runtime(state_path: Path, artifact_root: Path | None = None) -> Runtime:
    """Create the minimal portable-local runtime (no Codex/Docker required).

    This is the one-click portable deployment used by:

        uv run python -m portable_runtime --state data/portable-runtime.db status
        uv run runtime --state data/portable-runtime.db work submit --title "Echo test" --kind generic-task

    The runtime boots with zero providers ( §4.2 ), stores Work/Run/Artifact/Evidence/Knowledge
    via the Store interface, and supports export/import without any network or model.

    Args:
        state_path: SQLite file for persistent state (e.g. ``Path("data/portable-runtime.db")``).
        artifact_root: Optional filesystem directory for content-addressed artifacts.
            When ``None``, only inline artifacts are used; the runtime still boots.
    """
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if artifact_root is not None:
        artifact_root = Path(artifact_root)
        artifact_root.mkdir(parents=True, exist_ok=True)
    return Runtime(
        store=SQLiteStateStore(state_path),
        artifact_store=FilesystemArtifactStore(artifact_root) if artifact_root else None,
        runtime_id="portable-local",
    )


def create_personal_platform_runtime(state_path: Path, artifact_root: Path | None = None) -> Runtime:
    """Create the legacy personal-platform profile runtime (§57) with external capabilities available.

    In this phase the profile reuses the same SQLite store but documents the
    intended provider set. Actual provider registration is done
    by the deployment entrypoint that loads ``control_plane.toml`` or ``portable_runtime.toml``.

    The deployment layer (``deployments/windows-personal-platform``) is responsible for
    Task Scheduler / PowerShell / VBS / watchdog; Core never imports them.

    Args:
        state_path: SQLite file path.
        artifact_root: Optional artifact directory.
    """
    runtime = create_local_runtime(state_path, artifact_root)
    runtime.runtime_id = "personal-platform"
    return runtime
