# Phase E closure

Phase E is complete at commit `2f47395a41e4e508eca5ad5af167f10bf5442fd3`.

This commit is the long-lived rollback baseline for governance-bound execution admission and dispatch. Later phases MUST NOT silently reinterpret the semantics of `InvocationDispatchCommitted`.

## Completed responsibility chain

```text
E1
canonical governance truth
    -> GovernanceUseAdmission

E2a
GovernanceUseAdmission
    -> InvocationPermit
    -> final enforceable governance recheck

E2b
InvocationPermit
    -> GovernanceDispatchCommitter
    -> InvocationDispatchCommitted
    -> RealityBoundary
    -> provider.invoke(...)
```

The runtime now has a durable, local linearization point for when one governed attempt acquires execution authority.

## Frozen E2b invariant

Within one authoritative `StateStore` serialization domain:

```text
blocking governance mutation COMMIT
    <
InvocationDispatchCommitted COMMIT

=> dispatch claim fails
=> provider.invoke == 0
```

Conversely:

```text
InvocationDispatchCommitted COMMIT
    <
blocking governance mutation COMMIT

=> the existing attempt keeps the execution authority already committed to it
=> the later blocker MUST NOT retroactively revoke that attempt
=> the later blocker constrains later dispatch and recovery decisions
```

This ordering is part of the Phase E contract. A later phase MUST NOT reinterpret `InvocationDispatchCommitted` as a revocable reservation without introducing a new, explicitly different responsibility and state transition.

## Serialization domain

The E2b linearizability domain is exactly one authoritative `StateStore` serialization domain.

For the current portable-local deployment:

- Memory: the store transaction / `RLock` domain.
- SQLite: writers to the same database serialized with `BEGIN IMMEDIATE` for the dispatch commitment transaction.

Phase E does not claim distributed linearizability across independent replicated databases.

## Crash semantics

`InvocationDispatchCommitted` is a durable execution fact. If the process crashes after commitment and before an authoritative provider result is recorded, recovery MUST NOT treat the attempt as a fresh, never-dispatched invocation.

Recovery classification remains effect-semantic:

- pure / idempotent / deduplicatable: preserve the committed attempt and only retry under the same idempotency identity where safe;
- reconcilable: reconcile;
- irreversible-opaque: preserve `unknown` / explicit recovery semantics.

## Explicit non-guarantee

Phase E proves:

```text
governance mutation
<->
runtime durable dispatch commitment
```

It does not prove:

```text
governance mutation
<->
actual socket write / subprocess spawn / remote enqueue
```

The current `CapabilityProvider.invoke()` abstraction does not expose a uniform physical-effect commitment point. Any future requirement to revoke a previously dispatch-committed attempt before physical effect would require a new two-stage semantic contract, for example:

```text
RevocableDispatchReservation
    -> transport final fence
    -> PhysicalEffectCommitted
```

That would be a new responsibility model, not an E2b implementation detail and not a renamed governance generation.

## Phase boundary

No transport-level fencing work is implied by Phase E completion.

The next work streams are deliberately separate:

```text
Persistence determinism repair
    independent maintenance PR

F0
    physical-effect boundary audit
    no production protocol mutation

F1-A
    transport commitment protocol
    only if F0 proves the stronger revocation guarantee is required

or

F1-B
    effect verification / recovery closure
    default next semantic phase
```

Until an explicit F0 decision changes the product requirement, the default Phase E interpretation is:

```text
InvocationDispatchCommitted
=> this attempt has acquired non-retroactively-revocable runtime execution authority
```
