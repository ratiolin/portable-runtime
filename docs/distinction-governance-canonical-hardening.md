# Distinction governance canonical hardening (Phase D.5)

This document fixes the integration boundary between the pinned `distinction-governance-1.0` semantics and the runtime's existing durable/security substrate. It does not add a RealityBoundary stage and does not redefine the upstream governance contract.

## Runtime projection

The runtime operational object is formally:

```text
RuntimeDistinctionProjection = (S, A, Ω, Π, operational_anchor)
```

where `S` is qualification, `A` is activation, `Ω` is scope, and `Π` is the partition. `DistinctionState` remains the implementation/compatibility name for this projection.

```text
RuntimeDistinctionProjection != canonical D_t
version ∉ distinction semantic axes
```

`version` is runtime sequencing metadata. It contributes to `operational_anchor` so stale decisions/applications can be rejected, but changing only `version` does not add a distinction-semantic axis.

## Authority and policy remain independent

Governance authority uses a structured `GovernanceAuthorityTarget`. A projection-bound target contains the scheme identity, resource identity, scope, partition, and operational anchor. Therefore authority over one projection does not automatically authorize a different `(Ω, Π)` projection of the same scheme.

Production integration adapts this request to the existing canonical authorization substrate:

```text
Governance AuthorityRequest
        ↓
CanonicalAuthorizationRequest
        ↓
AuthorizationGrant / AuthorizationUse
```

Policy is intentionally absent from this adapter.

```text
PolicyDecision.allow != AuthorityGrant
```

Admission may require both a policy constraint and valid authority, but one never substitutes for the other.

Legacy string targets remain only as an internal compatibility path for pre-D.5 pure conformance fixtures. Product integration must use structured authority requests or the canonical authorization adapter.

## ScopeMatch and blocking

Use admission accepts a deterministic `UseContext` with a requested scope. The initial scope rule is:

```text
ScopeMatch(Ω, κ) := κ.requested_scope ⊆ Ω
```

An empty requested scope preserves the legacy whole-context behavior.

Review blocking remains serializable. `BlockingCondition` currently supports:

```text
context_names
scope_any
scope_all
```

No arbitrary callback predicate is persisted. This keeps blocking portable, deterministic, inspectable, and suitable for future `why` explanations.

## Processed EventInstance identity

Replay ownership belongs to the canonical event journal, not to a derived Q identifier.

For each processed material-change event, the runtime appends a deterministic canonical marker:

```text
governance.distinction.event.processed
```

The marker is keyed by `EventInstanceKey` (`event_ref`) and records the Q identities opened by that event. Replaying the same event instance returns the existing responsibility set before policy/profile interpretation runs again. Therefore:

```text
same EventInstanceKey
→ no new review from replay
```

This remains true if a later policy/profile would choose a different disposition. A new event identity with identical content remains a new event and may create a new obligation.

If projection is unavailable for a non-blocking disposition, the event is not marked processed, so a later replay can retry after representation becomes available. A blocking projection-unavailable result fails closed.

## Canonical durable history and the sidecar

`runtime_governance_records` is a materialized projection/index, not an independent source of truth.

Canonical governance history is stored in the existing append-only runtime `Event` journal with these event types:

```text
governance.distinction.state.seeded
governance.distinction.review.opened
governance.distinction.decision.recorded
governance.distinction.application.committed
governance.distinction.event.processed
```

Every canonical governance event carries the executable compatibility header:

```text
schema_version   = distinction-governance-history-v1
contract_version = distinction-governance-1.0
```

Reconstruction rejects missing, unknown, or future history/contract versions rather than interpreting them under the current semantics.

The journal contains enough information to reconstruct:

```text
RuntimeDistinctionProjection
Q = open review obligations
Dec = immutable governance decisions
App = committed governed applications
processed EventInstance identities
```

The required invariant is:

```text
clear runtime_governance_records
        ↓
replay canonical Event history
        ↓
equivalent GovernanceConfiguration
```

Because the canonical Event journal already participates in runtime export/import and bundle `events.jsonl`, portable state transfer does not require the private sidecar. A fresh runtime can import canonical state and rebuild the governance projection.

A governance mutation writes its sidecar projection and canonical history event in the same backend transaction. Failure to append the canonical event rolls the materialized projection back as well.

## Governance history epoch detection

Before a runtime may treat the sidecar as a trustworthy projection, it can classify the durable history state:

```text
EMPTY
  no governance sidecar
  no canonical governance history

CANONICAL
  supported-version canonical governance history exists
  sidecar may be discarded and rebuilt

LEGACY_PROVABLE
  pre-D.5 sidecar exists
  no canonical governance history
  surviving provenance deterministically defines the current configuration

LEGACY_INCOMPLETE
  pre-D.5 sidecar exists
  no canonical governance history
  at least one responsibility edge cannot be recovered
```

`LEGACY_PROVABLE` is deliberately narrow: it means the current configuration can be canonicalized, not that the original historical event sequence can be reconstructed. A discharged legacy review, dangling review reference, missing decision linkage, or missing EventInstance provenance makes the state `LEGACY_INCOMPLETE`.

```text
LEGACY_INCOMPLETE
→ do not invent EventInstanceKey
→ do not claim complete canonical migration
→ governed use must fail closed or require an explicit operator migration decision
```

If governance-looking canonical events exist but carry an unsupported schema/contract version, epoch detection and reconstruction reject them instead of reclassifying them as legacy.

## Freshness and commit-boundary TOCTOU

Semantic admission still checks decision freshness before producing an application receipt. Durable commit then rechecks all decision basis anchors while the governance transaction is held:

```text
capture / read basis anchors
        ↓
semantic admission
        ↓
transaction boundary
        ↓
recheck persisted target pre-anchor
recheck relevant basis anchors
        ↓
state effect + App + canonical Event
        ↓
atomic commit
```

For the canonical freshness adapter, each basis anchor is derived from the current canonical runtime record content. SQLite reads occur through the same store/connection while the governance transaction is held. A changed basis between semantic admission and durable commit therefore rejects the commit rather than landing a stale application.

## Coverage matrix

| Property | Required conformance |
| --- | --- |
| Runtime projection is not canonical `D_t`; version is operational | `D5-001` |
| Structured authority distinguishes projection scope/partition/anchor | `D5-002`, `D5-004` |
| `ScopeMatch` is subset based | `D5-003` |
| Blocking is deterministic and serializable | `D5-003` |
| Existing Authorization substrate is used | `D5-004` |
| Existing canonical state supplies freshness anchors | `D5-005` |
| Sidecar can be deleted and rebuilt | `D5-006` |
| Export/import remains portable without sidecar | `D5-007` |
| Freshness changes before durable commit fail closed | `D5-008` |
| Canonical event + projection mutation are atomic | `D5-009` |
| Policy output never grants authority | `D5-010` |
| Bundle round-trip preserves canonical governance truth | `D5-011` |
| History schema/epoch is machine-detectable; incomplete legacy never guesses provenance | `D5-012` |
| Same event replay under changed policy opens no new Q | `RD-003` |

Both Memory and SQLite are exercised for every persistence/security property where backend behavior matters.

## Phase boundary

Phase D.5 does not integrate governance into RealityBoundary. RealityBoundary remains responsible for crossing the execution boundary; governance remains responsible for admissible state/use. Phase E may consume the hardened governance result only after this coverage matrix, full pytest, Ruff, Mypy, and strict-conformance are green.

Phase E must not treat `runtime_governance_records` itself as admission authority. The required direction is:

```text
canonical history
      ↓
validated / reconciled projection
      ↓
governance admission snapshot
      ↓
RealityBoundary
```

If canonical governance history exists while the materialized projection is absent or unhydrated, the runtime must rebuild/reconcile or fail closed. An empty sidecar must never be interpreted as proof that no blocker exists.
