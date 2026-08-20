# Legacy control plane

The control_plane package from the original repository is retained as an
example personal-platform profile. In this standalone portable-runtime
library, only the portable_runtime package is included.

- The original Windows Task Scheduler / PowerShell wrappers lived under
  scripts/ until the deployments/windows-personal-platform cut-over path.
- The legacy HTTP surface (/healthz, /live, /ready, /v1/...) and
  provider bridges were exposed via compat/legacy_control_plane.py.
- Core never imports control_plane; the only allowed bridge is
  compat (data-only, import_legacy_repair).

Migration is additive:

```
legacy repair row (writes) -> dual_write_repair -> Work/Run/Event (reads switch before writes stop)
```

Do not delete the legacy profile in downstream deployments before replacement
tests pass.

> Origin: This document was originally legacy-control-plane.md in
> portable-runtime describing a generic personal-platform profile.
> It is retained here as a generic reference.

