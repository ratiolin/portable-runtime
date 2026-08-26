# F1-B4 P3 RecoveryDisposition design audit

## Baselines and scope

- B4-P1 implementation / rollback baseline: `800157f687639b1d4b1ebe4121f8283fb0dd6b74`.
- B4-P2 objective-bridge design-audit freeze: `7dd5c7798b2f937055ba0fcfae6e7c76ad13faac`.
- This audit does not add production RecoveryDisposition or RecoveryApplication semantics.
- B4-P4/P5, B4-A01, CompletionAuthority redesign, and B3-P4 remain out of scope.

## Audit question

What exact durable responsibility is missing between durable RecoveryObservation facts and a later recovery orchestration action?

The audit starts from these non-substitution boundaries:

```text
dispatch_recovery_mode()
    != RecoveryDisposition

RecoveryObservation
    != RecoveryDisposition

confirmed Outcome(pass|fail)
    != RecoveryDisposition

effect semantics / reversibility
    != RecoveryDisposition

blocking ReviewObligation
    != RecoveryDisposition
```

No one input is allowed to become an implicit recovery decision.

## Candidate responsibility object

Current evidence justifies a distinct durable recovery decision fact **in principle**. If production is later authorized, `RecoveryDisposition` must bind one exact basis snapshot rather than represent a mutable "latest recovery state".

Candidate identity inputs:

```text
exact dispatch_commit_ref
+ sorted exact RecoveryObservation basis_refs
+ sorted optional exact confirmed Outcome refs
+ exact effect/recovery classification inputs
+ exact policy/profile identity or digest
```

The disposition action vocabulary is deliberately not frozen by this audit. Each future action requires its own authority analysis.

## Replay and new evidence

```text
same exact basis snapshot
→ same disposition identity / replay

new observation basis
→ new disposition identity

new confirmed Outcome basis
→ new disposition identity

new disposition
!= automatic supersession of older disposition
```

There is no `latest observation wins` or `latest disposition wins` rule.

A future `RecoveryApplication` must consume one exact disposition ref. It must not infer which disposition is current from timestamp, insertion order, or the most recent observation.

## Policy drift

For an exact basis snapshot that already has a durable disposition, replay must return that durable fact without re-running a newer policy.

Decision identity cannot bind only `dispatch_commit_ref`, because one dispatch may acquire additional observations or confirmed Outcomes later. New basis permits a new decision instance; it does not rewrite the old decision.

## Authority boundaries

A future disposition remains non-self-executing:

```text
RecoveryDisposition
    != RecoveryApplication
    != provider.invoke authority
    != provider.reconcile authority
    != InvocationPermit
    != terminal completion
    != governance discharge
```

In particular:

```text
retry-idempotent disposition
    != permission to call provider.invoke
```

Any future retry must obtain a new attempt and new dispatch EventInstance through the existing qualification / governance / policy / authorization / routing / permit / E2b chain. An old `InvocationDispatchCommitted` is never revived.

## Audit verdict

Unlike P2, there is a real missing responsibility here: P1 records durable recovery observations, while no durable policy-owned recovery decision fact currently exists. That gap justifies `RecoveryDisposition` as a responsibility object **in principle**, but not production yet.

A later implementation-counterexample freeze must prove at minimum:

- exact-basis deterministic identity,
- same-basis replay,
- new-basis new decision,
- no implicit supersession,
- policy-drift replay from durable fact,
- no direct execution/reconcile/terminal authority,
- no hidden `latest wins` aggregation.

Therefore:

```text
B4-P3 durable RecoveryDisposition responsibility
= JUSTIFIED IN PRINCIPLE

B4-P3 production implementation
= NOT STARTED / requires counterexample freeze

B4-P4 RecoveryApplication
= CLOSED
```
