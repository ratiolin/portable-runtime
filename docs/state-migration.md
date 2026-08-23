# State migration

Export and import prove the Runtime is decoupled from the deployment:

```powershell
# A: Windows + SQLite + Codex
.venv\Scripts\python.exe -m portable_runtime --state data/portable-runtime.db state export runtime-state.json

# B: Linux + SQLite (or Postgres test backend) + FakeProvider
.venv\Scripts\python.exe -m portable_runtime --state /tmp/new.db state import runtime-state.json
```

## State export versus Bundle export

`StateStore.export_state()` (and the HTTP `POST /v1/state/export` endpoint)
returns a JSON object whose values are arrays of records.  The current store
schema has these 18 namespaces; an unused namespace is exported as an empty
array:

```
work, run, artifact, evidence, decision, action, outcome, knowledge,
knowledge_projection, event, step, attempt, checkpoint, compensation,
record, relation, authorization, authorization_use
```

`POST /v1/state/import` accepts the same state-object shape.  This is the
low-level state snapshot used by `state export/import`; it contains record
metadata only, not artifact bytes.

`Runtime.export_bundle()` is a separate Bundle v1 format: a tar archive (optionally
compressed) containing `manifest.json`, checksums, portable JSONL files for 17
namespaces, and any content-addressed files under `artifacts/`.  Its JSONL
namespaces are:

```
work, run, artifact, evidence, decision, action, outcome, knowledge,
knowledge_projection, event, step, attempt, checkpoint, compensation,
record, relation, authorization
```

Bundle v1 currently does not include the `authorization_use` namespace.  Use a
state JSON export when that authorization-use proof history must be preserved.
Bundle import additionally re-hydrates artifact bytes under the destination
`artifact_root` and validates checksums and the complete reference/lifecycle
graph before committing.

Both forms contain only portable JSON references; no absolute `D:\` or `C:\`
path is required to resolve an artifact. `FilesystemArtifactStore` URIs are
content-addressed and re-hydrated under the new `artifact_root` during Bundle
import.

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
candidate experience -> legacy KnowledgeItem(status="candidate")
```

`legacy_repair_id` / `legacy_fingerprint` are kept in `metadata` for audit, never as primary keys.

The `KnowledgeItem` mapping is a legacy read/migration representation only. It
must not be used as the write target for a new workflow: canonical workflows
persist `KnowledgeProjection` through `save_knowledge_projection(...)`.  When
an existing legacy item must be brought into the canonical model, use the
legacy adapter (`legacy_knowledge_to_projection`) and then persist the resulting
projection; the reverse adapter is a read-only compatibility view.
