# Store API

Core depends only on interfaces (`src/portable_runtime/interfaces/store.py`):

```python
class StateStore(Protocol):
    def get_work(self, work_id: str) -> Work | None: ...
    def save_work(self, work: Work) -> None: ...
    def get_run(self, run_id: str) -> Run | None: ...
    def save_run(self, run: Run) -> None: ...
    def save_evidence(self, evidence: Evidence) -> None: ...
    def save_knowledge(self, item: KnowledgeItem) -> None: ...
    def export_state(self) -> dict[str, list[dict]]: ...
    def import_state(self, state: dict[str, list[dict]]) -> None: ...

class EventStore(Protocol): ...
class ArtifactStore(Protocol): ...
```

Implementations:

- `SQLiteStateStore(path)` – single `runtime_records(kind,id,data,created_at)` table, WAL, atomic `export/import` preserving IDs.
- `InMemoryStateStore` – deterministic, used by all core tests and provider conformance tests.
- `FilesystemArtifactStore(root)` – content-addressed `sha256` file, URI `file://...`, scoped to `root` (rejects `../` escapes).

Any new store must pass the conformance suite:

```
CRUD
transaction / atomic import
restart persistence
migration
export / import
ID preservation
event ordering
concurrent access rules
```

Core tests run against `InMemoryStateStore`; adding `PostgresStateStore` or `S3ArtifactStore` requires no Core change.
