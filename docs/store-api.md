# Store API

Core depends on the interfaces in `src/portable_runtime/interfaces/store.py`.
The small `KnowledgeItem`-oriented surface shown in older versions of this
document is a legacy compatibility subset, not the canonical write API.

## Canonical state and semantic records

Representative methods on `StateStore` are:

```python
class StateStore(Protocol):
    # Work/run and portable evidence/artifact objects
    def get_work(self, work_id: str) -> Work | None: ...
    def save_work(self, work: Work) -> None: ...
    def get_run(self, run_id: str) -> Run | None: ...
    def save_run(self, run: Run) -> None: ...
    def save_artifact(self, artifact: Artifact) -> None: ...
    def save_evidence(self, evidence: Evidence) -> None: ...

    # Canonical knowledge (new workflow writes)
    def save_knowledge_projection(self, value: KnowledgeProjection) -> None: ...
    def get_knowledge_projection(self, projection_id: str) -> KnowledgeProjection | None: ...
    def list_knowledge_projections(self, status: str | None = None) -> list[KnowledgeProjection]: ...

    # Semantic records, typed relations, authorization grants and use proofs
    def save_record(self, value: BaseRecord) -> None: ...
    def save_relation(self, value: RecordRelation) -> None: ...
    def save_authorization(self, value: AuthorizationGrant) -> None: ...
    def get_authorization(self, authorization_id: str) -> AuthorizationGrant | None: ...
    def save_authorization_use(self, value: AuthorizationUse) -> None: ...

    # Portable state snapshot
    def export_state(self) -> dict[str, list[dict[str, object]]]: ...
    def import_state(self, state: dict[str, list[dict[str, object]]]) -> None: ...
```

Authorization grants are also persisted by the concrete stores through
`save_authorization(...)` / `get_authorization(...)` / `list_authorizations()`.
The `authorization_use` record is immutable proof that a particular grant was
used for a particular request; it is distinct from the grant itself.

## Execution-integrity primitives

The R1.1 extensions are part of the current concrete stores and are required
by workflows that need crash recovery:

```python
save_step(...)                 # Step lifecycle
save_attempt(...)              # provider attempt and outcome boundary
save_checkpoint(...)           # resumable progress
save_compensation(...)         # compensating action state
compare_and_swap(...)          # versioned write
transaction()                  # atomic multi-object work
commit_terminal(...)           # validated Work/Run terminal pair
acquire_lease(...) / renew_lease(...) / release_lease(...)
```

Conformance treats these as optional extensions for minimal third-party stores;
the built-in SQLite and in-memory stores implement them.  A store that omits an
extension must fail closed or provide the documented fallback rather than
silently weakening execution-integrity guarantees.

## Legacy compatibility subset

`save_knowledge(KnowledgeItem)`, `get_knowledge(...)`, `list_knowledge(...)`,
and the legacy evidence views remain for old callers and migration adapters.
They are read-compatible views and migration inputs; they are not the canonical
ingestion path for new workflows.  Persist canonical knowledge with
`save_knowledge_projection(...)` and persist semantic facts with
`save_record(...)` / `save_relation(...)`.

`EventStore` and `ArtifactStore` remain separate interfaces; state export carries
artifact metadata and the Bundle exporter may include the corresponding bytes.

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
