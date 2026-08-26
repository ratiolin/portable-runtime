# F1-B4 reconciliation repeatability audit

Baseline: `main@d593ee2c587291ca4234968aaf767a0e577bc23c`.

This audit opens only the reconciliation repeatability question. It does not authorize production repeatability schema, provider protocol changes, application-binding production, configured-provider reconciliation target binding, reconciliation consumption, Runtime integration, provider calls, retry, DIS-015, PVP-007, historical backfill, or P5 import authority.

## Question

The accepted reconciliation topology is:

```text
RecoveryApplication(reconciliation-request)
→ one reconciliation responsibility
→ RealityBoundary.reconcile
→ durable application-bound RecoveryObservation
→ STOP
```

The unresolved crash seam is:

```text
provider.reconcile may have been entered
→ process crashes
→ no durable bound RecoveryObservation
```

The question is not whether the underlying business operation is idempotent. The question is whether repeating the **reconciliation reality query** for the exact same historical subject is safe under an exact reconciliation contract.

## Current-state findings

Current provider protocol exposes only:

```text
reconcile(request_id) -> CapabilityResult | None
```

There is no first-class reconciliation repeatability authority.

Current `ProviderDescriptor` contains execution effect semantics such as:

```text
pure
idempotent
deduplicatable
reconcilable
irreversible-opaque
```

These classify the business/execution effect and recovery mode. They do not prove that repeated `provider.reconcile(...)` calls are observationally pure, side-effect-free, or repeat-safe.

Likewise, the existence of a method named `reconcile` proves only an interface shape. It is not semantic authority.

Current `RealityBoundary.reconcile` accepts `request_id` and `provider_id`, resolves the current registry provider, and calls `provider.reconcile(request_id)`. It does not evaluate a repeatability contract.

Current `CapabilityResult` may contain `external_operation_ref` and `reconciled`, but result shape is not repeatability proof.

## Required responsibility domain

A future repeatability proof must answer all of the following as one exact responsibility object or equivalent durable authority.

### Subject model

What exact subject may be queried repeatedly?

Examples that are **not interchangeable**:

```text
same request_id
same historical dispatch
same external operation subject
same configured provider execution identity
```

A contract that is safe only for one subject model cannot be silently applied to another.

### Provider/protocol identity

Repeatability must be bound to the actual reconciliation semantics, not just a provider string.

A future contract must at least distinguish:

```text
provider execution identity
reconciliation protocol identity/version
contract version/digest
reconciliation subject model
```

Provider-id equality alone is insufficient authority, as already frozen by the prior reconciliation-consumption audit in RC-006…008.

### Permitted effect

Repeatability proof authorizes only repetition of the reconciliation query itself.

```text
repeat-safe reconciliation proof
→ may permit provider.reconcile for the same exact subject
```

It does **not** authorize:

```text
provider.invoke
business-operation retry
fresh CapabilityRequest
InvocationPermit
StepAttempt
InvocationDispatchCommitted
Outcome
RecoveryDisposition
```

### Contract drift

Historical repeatability authority cannot be substituted by a current contract that merely looks similar.

```text
old provider/protocol/contract identity
!= current provider/protocol/contract identity
```

A changed contract version or digest is new evidence, not retroactive proof that the old reality query was repeat-safe.

## Crash-state matrix

The audit freezes four reconciliation progress states.

```text
S0  before reconciliation reality exit
S1  reconciliation reality call may have started
S2  provider returned a reconciliation result
S3  exact application-bound RecoveryObservation durably committed
```

### S0

No external reconciliation call has crossed the reality boundary.

```text
S0
→ same reconciliation responsibility may be attempted
```

This is ordinary pre-call replay and requires no repeatability proof.

### S1 / S2 with exact repeat-safe proof

If an exact reconciliation repeatability contract proves the same subject may be queried again safely:

```text
S1 or S2
+ exact repeat-safe proof
+ no bound observation
→ same application responsibility may re-enter provider.reconcile
```

This permission is narrow: it applies only to the exact reconciliation query covered by the contract.

### S1 / S2 without exact repeat-safe proof

```text
S1 or S2
+ repeatability absent / unknown / drifted
+ no bound observation
→ ambiguous
→ automatic repeat forbidden
```

This is fail-closed. The system must not infer repeatability from provider method naming, business idempotency, provider id, current registry state, or current contract state.

If a later design needs durable reality-crossing evidence for this model, it may justify a dedicated pre-call/attempt fact such as `RecoveryReconciliationAttemptRecorded`. This audit does not authorize such a fact.

### S3

Once the exact application-bound observation is durable:

```text
same RecoveryApplication
+ exact bound RecoveryObservation exists
→ provider calls = 0
```

Repeat-safe proof does not override completion. A further reconciliation requires a new observation → disposition → application cycle.

## Candidate semantic shape only

A future authority may have semantics equivalent to:

```text
ReconciliationRepeatabilityContract
    subject_model
    repeatability_mode
    provider_execution_identity
    reconciliation_protocol_identity
    contract_version
    contract_digest
```

This is **not** a production schema authorization.

The exact identity must be content-addressed by the complete contract semantics. Same identity with changed meaning is rebound and must fail closed.

The contract must be obtained from an authoritative provider/protocol configuration or execution-time binding path. A caller must not be able to manufacture repeat-safe authority by setting a boolean or arbitrary digest in a consumption request.

## Counterexample freeze

```text
RR-001  absence of contract != repeat-safe
RR-002  method name reconcile != observational purity/repeat safety
RR-003  business-operation idempotency != reconciliation repeatability
RR-004  same provider_id != repeatability authority
RR-005  provider/protocol/contract drift invalidates current-proof substitution
RR-006  post-call/pre-observation repetition requires exact repeat-safe proof
RR-007  unknown repeatability defaults fail closed
RR-008  repeatability proof does not authorize provider.invoke
RR-009  repeatability proof does not authorize retry
RR-010  exact bound observation terminates same application responsibility
RR-011  caller cannot declare repeat-safe authority ad hoc
RR-012  legacy history cannot be backfilled with current repeatability contract
```

## Production implications

This audit deliberately does not decide whether a dedicated durable repeatability contract object is required. It only freezes the semantics any production mechanism must prove.

A later production slice may be authorized only after deciding:

```text
1. authoritative source of provider/protocol repeatability semantics
2. stable subject identity for reconciliation repeatability
3. deterministic contract identity / drift semantics
4. S1/S2 crash behavior under repeat-safe and unknown modes
5. relationship to application-bound RecoveryObservation completion
```

No generic `RecoveryApplicationConsumed` fact is introduced.

## Explicitly unchanged

```text
RecoveryObservation ↔ RecoveryApplication binding semantics
= AUDITED

minimal local binding production
= NOT AUTHORIZED

configured-provider reconciliation target binding
= UNPROVEN

reconciliation repeatability production
= NOT AUTHORIZED

automated reconciliation production
= BLOCKED / NOT AUTHORIZED

DIS-015
= UNPROVEN

PVP-007
= UNPROVEN

retry execution chain
= CLOSED

P5
= CLOSED / UNSUPPORTED
```

## Audit conclusion

The valid responsibility rule is:

```text
repeatability proof
= authority about re-entering the same reconciliation reality query
```

It is independent from:

```text
business effect idempotency
provider invocation authority
retry authorization
configured-provider target identity
application completion identity
```

Until an exact repeatability proof exists, S1/S2 is ambiguous and automatic reconciliation repetition must fail closed.
