# Deployment: Windows personal platform

The original Windows deployment is preserved as `deployments/windows-personal-platform/` and `profiles/personal-platform` equivalent.

Components preserved:

```
AlertmanagerTrigger -> Work(kind="incident") -> IncidentRepairWorkflow
CodexProvider (codex exec --model from [[providers]] / [agent] model)
Prometheus / Docker verifiers (verify.promql / verify.container / verify.http)
FeishuTrigger + FeishuHumanProvider + FeishuNotificationProvider
SQLiteStateStore + FilesystemArtifactStore
Legacy policies: SensitivePathPolicy, ExternalSideEffectPolicy, CandidateMergePolicy
```

Scripts still under `scripts/`:

- `install-control-plane.ps1` – registers the Scheduled Task
- `Run-ControlPlane.ps1` – supervisor (single-instance guard, PID file, restart recovery)
- `check_coverage.py` / `check_portable_core_imports.py` – CI gates

Cut-over plan (§56-§57): move `Task Scheduler / PowerShell / VBS / watchdog` into this profile, keep `portable_runtime` import-free. The portable-local profile (`uv run python -m portable_runtime`) must never require Windows-only code.

See `docs/architecture.md` for the overall structure and `docs/state-migration.md` for export/import across Windows -> Linux.

