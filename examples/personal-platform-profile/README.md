# Profile: personal-platform (legacy Windows)

This profile is the legacy personal-platform deployment that preserves the
pre-portable behavior (Codex / Feishu / Prometheus / Alertmanager / Docker).

It is the reference deployment that proves the portable Runtime can load the
same Work/Run/Artifact/Evidence/Knowledge with a different provider set.

Canonical location: `examples/personal-platform-profile/ (reference)` (physical files).
This `profiles/personal-platform/` directory is the portable alias per §57;
both refer to the same set:

- AlertmanagerTrigger -> Work(kind="incident") -> IncidentRepairWorkflow
- CodexProvider (codex exec)
- PrometheusProvider / DockerProvider (verifiers)
- FeishuTrigger + FeishuHumanProvider + FeishuNotificationProvider
- SQLiteStateStore + FilesystemArtifactStore
- DailyScanWorkflow + KnowledgeConsolidationWorkflow
- legacy policies

For the cross-platform counterpart with no Windows/Docker dependency, see
`deployments/portable-local/` and `docs/deployment-local.md`.

Task Scheduler / PowerShell / VBS / watchdog scripts live in
`examples/personal-platform-profile/ (reference)` (copied from `scripts/` per §56).
This profile never leaks into `portable_runtime/core`.

