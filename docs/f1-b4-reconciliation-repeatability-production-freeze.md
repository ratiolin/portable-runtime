# F1-B4 reconciliation repeatability production freeze

Baseline: `main@d73fbd53b4d2cd5ffc29e692cef1cce832d52032`.

This production slice opens **C only**. It establishes exact historical reconciliation repeatability authority without implementing a reconciliation consumer or making any provider call.

## Supported responsibility

C answers one question only:

```text
for the exact historical provider execution target
and the exact historical reconciliation subject,
was this reconciliation query explicitly configured repeat-safe
under the exact reconciliation protocol/version and contract state?
```

The supported production chain is:

```text
ProviderRegistry registration/configuration
→ exact ProviderExecutionBinding B
→ B-bound ReconciliationRepeatabilityContract
→ governed dispatch for exact request-id subject
→ durable ReconciliationRepeatabilityAuthority C in InvocationDispatchCommitted
→ read-only eligibility evaluation
→ STOP
```

C does not call `provider.reconcile` and does not implement the reconciliation consumer.

## Responsibility objects

### ReconciliationRepeatabilityConfiguration

This is provider-registry configuration input, not durable historical authority.

It contains:

```text
subject_model = request-id
reconciliation_protocol_identity
reconciliation_protocol_version
repeatability_mode
contract_version
```

It deliberately contains neither a caller-supplied digest nor a subject identity.

`ProviderDescriptor.effect_semantics` and `ProviderDescriptor.side_effect_class` remain business/execution effect classifications. They are not reconciliation repeatability authority.

### ReconciliationRepeatabilityContract

The registry binds configured reconciliation semantics to the exact `ProviderExecutionBinding` established by the same registration.

The contract identity/digest covers:

```text
provider_execution_binding_ref
subject_model
reconciliation_protocol_identity
reconciliation_protocol_version
repeatability_mode
contract_version
```

Therefore:

```text
same provider_id
!= same repeatability contract

same protocol name
!= same repeatability contract

same contract text + different ProviderExecutionBinding
!= same repeatability contract
```

The configured contract is self-validating, but it is not itself an exact historical subject-use fact.

### ReconciliationRepeatabilityAuthority

At governed dispatch, the registry coherently captures the exact live provider target, its exact B binding, and—only for an explicitly `repeat-safe` configured contract—instantiates C for the exact dispatch request id.

The v1 subject model is intentionally narrow:

```text
subject_model = request-id
subject_identity = exact InvocationDispatchCommitted.request_id
```

The authority identity/digest covers:

```text
contract_ref
provider_execution_binding_ref
subject_model
subject_identity
reconciliation_protocol_identity
reconciliation_protocol_version
repeatability_mode = repeat-safe
contract_version
contract_digest
```

The authority is embedded durably in the same `InvocationDispatchCommitted` that already carries B. The C authority ref is also part of the new dispatch deterministic identity. Legacy and B-only dispatch identities remain unchanged when C is absent.

## Positive authority is repeat-safe only

v1 creates positive C authority only for:

```text
repeatability_mode = repeat-safe
```

The following never produce positive authority:

```text
contract absent
repeatability unknown
repeatability non-repeat-safe
business effect idempotent
business effect reconcilable
method named reconcile
caller-provided ad-hoc repeat_safe
```

They remain ineligible and fail closed.

## Historical authority and current drift

C is historical authority captured with the original dispatch. Current registry configuration may verify that the exact historical authority still matches, but current configuration cannot manufacture missing historical C authority.

```text
legacy/B-only historical dispatch
+ current repeat-safe configuration
→ no historical C backfill
→ ineligible
```

Eligibility requires all of:

```text
exact historical ReconciliationRepeatabilityAuthority
exact historical ProviderExecutionBinding
exact required request-id subject
current registry resolves the exact same B
current configured repeat-safe contract re-instantiates the exact same C semantics
```

Any of the following is ineligible:

```text
same provider_id but different B
subject/request-id mismatch
protocol identity/version drift
contract version/digest drift
repeatability mode drift
exact historical provider target unavailable
current configured contract absent
```

Historical authority is never substituted by a merely similar current contract.

## Authority origin and P5

Positive C authority originates only from the `ProviderRegistry` configuration path and governed dispatch capture. A caller cannot obtain authority by passing `repeat_safe=True` or an arbitrary digest to a recovery/consumer request.

Every valid C-bearing dispatch is structurally B-bearing. Therefore the existing B governed-dispatch authority fence also closes direct append and serialized/P5 import of valid C-bearing dispatch authority for Memory and SQLite.

```text
valid B+C dispatch
→ governed local dispatch commit supported
→ direct append rejected
→ serialized/P5 import rejected
```

C is not added to generic state-graph invalidity. A B+C dispatch is a valid historical object; serialized authority import is unsupported as a transition/origin rule.

## Counterexample graduation

This production slice graduates the frozen repeatability counterexamples using real production APIs:

```text
RR-001…012
RSF-008…012
C-INT-01…08
```

The C integration cases establish:

```text
C-INT-01 exact B + exact subject + repeat-safe contract → eligible
C-INT-02 same provider_id + different B → ineligible
C-INT-03 same B + different request_id → ineligible
C-INT-04 protocol/version drift → ineligible
C-INT-05 contract version/digest drift → ineligible
C-INT-06 idempotent/reconcilable effect semantics alone → no C authority
C-INT-07 ad-hoc declaration / serialized authority copy → no authority
C-INT-08 C objects expose no invoke/reconcile/retry capability
```

RSF-012 now freezes the complete A/B/C substrate set as production-supported but individually non-executing.

## Explicit non-authority

C proves only repeat-query eligibility semantics for one exact historical target/subject.

It does **not** authorize:

```text
provider.reconcile
provider.invoke
business retry
fresh CapabilityRequest
InvocationPermit
StepAttempt
InvocationDispatchCommitted
Outcome
RecoveryDisposition
RecoveryApplication
reconciliation consumer execution
```

It also does not override A completion semantics. A durable application-bound `RecoveryObservation` remains a separate responsibility fact; the future consumer must enforce provider calls = 0 when that exact application is already completed.

No `RecoveryReconciliationAttemptRecorded` or generic `RecoveryApplicationConsumed` object is introduced.

## Provider protocol remains unchanged

`CapabilityProvider.reconcile` remains:

```text
reconcile(request_id) -> CapabilityResult | None
```

C adds no provider protocol method and no call site to reconciliation execution.

## Capability state after this slice

```text
A application-bound RecoveryObservation
= SUPPORTED / FROZEN

B ProviderExecutionBinding
= SUPPORTED / FROZEN

C ReconciliationRepeatabilityAuthority
= SUPPORTED locally / FROZEN after merge

reconciliation consumer
= CLOSED

provider.reconcile
= NOT AUTHORIZED

RecoveryReconciliationAttemptRecorded
= NOT REQUIRED / NOT AUTHORIZED

RecoveryApplicationConsumed
= NOT REQUIRED / NOT AUTHORIZED

retry
= CLOSED

DIS-015 / PVP-007
= UNPROVEN

P5 authority import
= CLOSED / UNSUPPORTED

Experience Governance
= NOT STARTED
```

## Next boundary

After C is independently merged, STOP.

The next possible stage is a separate reconciliation-consumer counterexample freeze. That future freeze must require the conjunction of exact RecoveryApplication responsibility, A completion-state check, exact B historical target, and exact C repeatability eligibility before any reconciliation provider call can be considered. It is not part of this production slice.
