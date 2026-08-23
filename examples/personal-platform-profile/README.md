# Profile: personal-platform (legacy Windows)

This directory is documentation-only.  It records the legacy personal-platform
deployment shape (Codex / Feishu / Prometheus / Alertmanager / Docker); the
deployment-specific scripts, credentials, and host configuration are not part
of this repository.

The profile is a historical reference for how a portable Runtime can load the
same Work/Run/Artifact/Evidence/Knowledge graph with a different provider set.
There is no `profiles/personal-platform/` alias or runnable deployment tree in
this repository.

The historical provider/trigger set was:

- AlertmanagerTrigger -> Work(kind="incident") -> IncidentRepairWorkflow
- CodexProvider (codex exec)
- PrometheusProvider / DockerProvider (verifiers)
- FeishuTrigger + FeishuHumanProvider + FeishuNotificationProvider
- SQLiteStateStore + FilesystemArtifactStore
- DailyScanWorkflow + KnowledgeConsolidationWorkflow
- legacy policies

For the runnable cross-platform counterpart with no Windows/Docker dependency,
see [docs/deployment-local.md](../../docs/deployment-local.md) and the provider
example in [examples/echo-provider](../echo-provider/).  Those are the current
repository paths; the old `deployments/portable-local/` tree is not present.

Task Scheduler / PowerShell / VBS / watchdog scripts belonged to the historical
host deployment and are intentionally not claimed as files in this example.
The profile never leaks into `portable_runtime/core`.

