# F1-B4 A: application-bound RecoveryObservation production

Baseline: `main@3881c31e969b5383e2db439aa9f7fa1f06c683f0`.

This slice implements only substrate A from the reconciliation substrate production freeze.

```text
RecoveryApplicationRecorded
→ store-owned application-bound observation commit
→ durable RecoveryObservation
→ STOP
```

## Supported

```text
application-bound RecoveryObservation local authority = SUPPORTED
exact RecoveryApplication reconstruction = SUPPORTED
exact disposition/dispatch/Attempt/Step/Action reconstruction = SUPPORTED
one application → one deterministic completion observation identity = SUPPORTED
Memory opt-in commit/replay = SUPPORTED
SQLite opt-in commit/replay/close-reopen = SUPPORTED
legacy unbound RecoveryObservation decode = SUPPORTED
bound observation direct append = CLOSED
bound observation P5 serialized import = CLOSED / UNSUPPORTED
```

The dedicated caller surface is:

```text
RecoveryApplicationObservationCommitRequest(
    recovery_application_ref,
    observation_source,
    reported_status,
    provenance_refs,
)
```

The caller cannot supply `dispatch_commit_ref`, `attempt_ref`, `step_ref`, `action_ref`, or `observation_instance_ref`. The store reconstructs the exact durable `RecoveryApplication`, revalidates its source `RecoveryDisposition`, then reuses the existing RecoveryObservation dispatch-graph checks.

Only `RecoveryApplication(application_kind="reconciliation-request")` may produce this completion fact.

## Identity and rebound

The application-bound observation identity is derived only from:

```text
schema
semantic role = reconciliation-application-completion
recovery_application_ref
```

Reported status and provenance are semantics, not identity.

```text
same application + same semantics
→ replay

same application + changed reported status/provenance
→ same identity / changed semantics
→ rebound
→ fail closed
```

This establishes one durable completion identity per exact RecoveryApplication without changing generic P1 observation identity rules.

## Legacy compatibility

Historical observations without `recovery_application_ref` continue to decode as valid execution-level facts.

```text
legacy/unbound RecoveryObservation
→ valid P1 execution fact
→ application completion = false
```

No authority is inferred from `observation_source == "provider-reconcile"` or from application-looking strings in `provenance_refs`.

## Explicitly not supported

```text
configured-provider execution binding = NOT SUPPORTED
reconciliation repeatability authority = NOT SUPPORTED
reconciliation consumer = NOT SUPPORTED
provider.reconcile = NOT AUTHORIZED
provider.invoke = NOT AUTHORIZED
fresh CapabilityRequest / InvocationPermit / StepAttempt / dispatch = NOT AUTHORIZED
retry = NOT AUTHORIZED
RecoveryReconciliationAttemptRecorded = NOT AUTHORIZED
RecoveryApplicationConsumed = NOT AUTHORIZED
DIS-015 / PVP-007 = UNPROVEN
P5 = CLOSED / UNSUPPORTED
```

This slice does not modify Runtime, provider protocol/registry, dispatch, configured-provider identity, repeatability semantics, or recovery disposition/application lifecycle.

## Graduation

This slice graduates AB-001…014 and RSF-001…003 to production behavior. RSF-004…012 remain strict blocked obligations for B/C and the later reconciliation consumer.
