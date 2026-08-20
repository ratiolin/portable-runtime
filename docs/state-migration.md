# State migration

Export and import prove the Runtime is decoupled from the deployment:

```powershell
# A: Windows + SQLite + Codex
.venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db state export runtime-state.json

# B: Linux + SQLite (or Postgres test backend) + FakeProvider
.venv\Scripts\python.exe -m portable_runtime --state /tmp/new.db state import runtime-state.json
```

HTTP:

```
POST /v1/state/export -> {work, run, artifact, evidence, decision, action, outcome, knowledge, event}
POST /v1/state/import  <- same JSON
```

The export contains only portable JSON; no absolute `D:\` or `C:\` paths are required to resolve artifacts. `FilesystemArtifactStore` URIs are content-addressed and re-hydrated under the new `artifact_root`.

Legacy migration:

```python
from portable_runtime.stores.migration import dual_write_repair

dual_write_repair({"id": "repair-1", "fingerprint": "fp", "status": "closed"}, store)
```

maps:

```
repair -> Work(kind="incident") + Run
repair action -> Action
verification -> Evidence
candidate patch -> Artifact(kind="patch")
candidate experience -> KnowledgeItem(status="candidate")
```

`legacy_repair_id` / `legacy_fingerprint` are kept in `metadata` for audit, never as primary keys.
