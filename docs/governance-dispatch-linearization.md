# Governance-bound durable dispatch linearization (E2b)

E2b defines one runtime-local linearization point between governance mutation and effect dispatch authorization. It does not change the provider protocol and it does not claim to linearize against the physical socket write, subprocess spawn, or remote queue enqueue performed inside a provider.

## Responsibility chain

```text
canonical governance truth
        ↓
GovernanceUseAdmission
        ↓
InvocationPermit
        ↓
GovernanceDispatchCommitter
        ↓
InvocationDispatchCommitted
        ↓
RealityBoundary
        ↓
CapabilityProvider.invoke(...)
```

Ownership is intentionally non-substitutable:

- `GovernanceUseAdmission` owns the usability judgment.
- `InvocationPermit` owns the immutable binding to the admitted governance judgment.
- `GovernanceDispatchCommitter` owns only the linearized durable dispatch-authorization fact.
- `RealityBoundary` remains the sole owner of reality exit and provider invocation.
- `CapabilityProvider` owns external execution.

`GovernanceDispatchCommitter` never receives or calls a provider capability.

## Linearization contract

For governed use, the runtime performs:

```text
final governance recheck
        ↓
BEGIN LINEARIZED WRITE
        ↓
reconstruct canonical governance truth
compare InvocationPermit governance binding
        ↓
atomic write:
  InvocationDispatchCommitted
  + StepAttempt dispatch metadata, when an attempt exists
        ↓
COMMIT  ← runtime dispatch linearization point
        ↓
provider.invoke(...)
```

The ordering invariant is:

```text
blocking governance mutation COMMIT
    <
InvocationDispatchCommitted COMMIT

⇒ dispatch commitment must fail
⇒ provider.invoke == 0
```

Conversely:

```text
InvocationDispatchCommitted COMMIT
    <
blocking governance mutation COMMIT

⇒ the existing attempt already owns a legal dispatch commitment
⇒ the later blocker does not retroactively revoke that attempt
⇒ the blocker constrains later dispatch and recovery decisions
```

This is a total-order rule, not a rule that governance always wins.

## Serialization domain

The E2b linearizability domain is one authoritative `StateStore` serialization domain.

- Memory: one `InMemoryStateStore` instance and its `RLock` transaction domain.
- SQLite: all writers to the same SQLite database. Dispatch commitment uses `BEGIN IMMEDIATE`, so it competes with canonical governance mutation for SQLite writer serialization before reading governance truth.

The guarantee does not extend across independently replicated databases. E2b is a portable-local guarantee, not distributed consensus.

## Durable commitment payload

`InvocationDispatchCommitted` uses schema `governance-dispatch-commit-v1` and binds:

```text
request_id
provider_id
attempt_ref
invocation_permit_digest
qualification_digest
governance_requirement_digest
governance_snapshot_digest
lease_generation
linearization_domain
```

When a `StepAttempt` exists, its metadata is updated in the same transaction with:

```text
dispatch_commit_ref
governance_requirement_digest
governance_snapshot_digest
invocation_permit_digest
```

No new `StepAttempt.status` is introduced. The attempt remains `running` until ordinary execution projection terminalizes it.

A standalone governed invocation can have no pre-existing `StepAttempt`; in that case the canonical `InvocationDispatchCommitted` Event is still the durable commitment fact and `attempt_ref` is null. Existing execution-state protocol is not expanded merely to manufacture an attempt.

## Crash semantics

A durable dispatch commitment means recovery may never reinterpret the attempt as never dispatched.

```text
InvocationDispatchCommitted
        ↓
process crash before provider result
        ↓
external effect state is not assumed absent
```

Recovery classification is conservative:

- `pure`, `idempotent`, `deduplicatable`: retry is only admissible under the same idempotency identity; recovery surfaces the committed attempt instead of creating a fresh semantic invocation.
- `reconcilable`: use provider reconciliation.
- `irreversible-opaque`: mark/return `unknown` and require explicit recovery.

The commitment is therefore an execution fact, not a transient lock.

## Non-governed invocation

An explicitly non-governed `InvocationPermit` returns `not-applicable` from the dispatch committer. It does not acquire distinction-governance dispatch semantics and it does not write `InvocationDispatchCommitted`. Existing non-governed execution behavior is preserved.

## Explicit limit

E2b proves:

```text
governance mutation
↔
runtime dispatch commitment
```

It does **not** prove:

```text
governance mutation
↔
actual external socket write / subprocess spawn / queue enqueue
```

The current provider protocol exposes only opaque `async invoke(request, context)`. A future guarantee at the physical effect boundary would require provider/transport participation in fencing or an equivalent dispatch protocol; a runtime-only generation counter cannot prove that stronger property.
