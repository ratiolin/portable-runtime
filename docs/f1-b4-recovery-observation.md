# F1-B4 P1: durable RecoveryObservation

## Baselines and scope

- F1-B3 implementation baseline: `25d834a174a5e884afcef532d3e5c3bd4f000107`.
- F1-B4 design freeze: `d56f91749e4b8a86093ae07a14ff13ba4b43078e`.
- This implementation closes B4-A02 only: durable observation of an already committed ambiguous dispatch.
- B3-P4, terminal redesign, RecoveryDisposition, RecoveryApplication, compensation, and recovery portability remain out of scope.

## Authority contract

```text
InvocationDispatchCommitted
    -> exact StepAttempt
    -> exact Step
    -> exact Action
    -> store-owned commit_recovery_observation()
    -> RecoveryObservationRecorded
```

The caller supplies only an observation instance identity, dispatch commitment reference, observation source, execution-level report status, and provenance refs. The store re-reads the durable execution graph and derives Action / Attempt / Step / request / provider / idempotency bindings inside its transaction.

`RecoveryObservation.reported_status` is deliberately one of `reported-succeeded`, `reported-failed`, or `reported-unknown`. It is not objective verification.

```text
RecoveryObservation
    != confirmed Outcome
    != RecoveryDisposition
    != RecoveryApplication
    != provider invocation authority
    != terminal completion
```

Observation identity is instance-based, not payload-deduplicated: exact instance replay is idempotent; a new instance with identical content is a new recovery fact; reusing one instance with different semantics is an identity rebound and fails closed.

Live `Runtime.reconcile()` records an observation only for attempts carrying an E2b `dispatch_commit_ref`. Each actual provider reconciliation call receives a fresh observation instance. Observation persistence failure demotes the returned recovery result to `unknown` with `RecoveryObservationCommitFailed`.

## Explicit limits

This phase does not define serialized RecoveryObservation portability. Bulk import/bundle authority closure is reserved for B4-P5. It also does not create any recovery policy, disposition, application, retry, compensation, governance discharge, or terminal authority.
