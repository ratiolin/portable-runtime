# F1-B4 reconciliation substrate production decision freeze

Baseline: `main@034c0cdcb9662574fa78b9fe77fc38b3edf77df2`.

This freeze consolidates the three completed reconciliation substrate audits:

```text
RecoveryObservation ↔ RecoveryApplication binding semantics
= AUDITED

reconciliation repeatability semantics
= AUDITED

configured-provider reconciliation target semantics
= AUDITED
```

It decides which substrate responsibilities are required for a minimal v1 automated reconciliation path. It does **not** implement any substrate production, provider call, Runtime consumer, DIS-015, PVP-007, retry, fresh invocation authority, or P5 authority.

## v1 scope decision

The minimal v1 reconciliation path is intentionally restricted to providers whose reconciliation query has an explicit exact repeat-safe authority.

```text
v1 automated reconciliation
= repeat-safe providers only
```

Providers whose reconciliation repeatability is absent, unknown, non-repeat-safe, or drifted remain unsupported for automatic reconciliation and require fail-closed/manual recovery.

This scope decision avoids introducing an additional durable progress object solely to support non-repeat-safe/unknown reconciliation in v1.

## Substrate decision table

### A. Application-bound RecoveryObservation authority

```text
status = REQUIRED
```

A durable completion fact must bind one exact `RecoveryApplication(kind=reconciliation-request)` to one stable completion observation identity.

Required properties:

```text
exact RecoveryApplication ref only
store-owned source graph reconstruction
one application → one deterministic completion identity
same semantics → replay
changed reported/provenance semantics → rebound/conflict
legacy unbound observations remain valid but are not completion
bound observation remains execution-level only
no Outcome / RecoveryDisposition / new RecoveryApplication authority
P5 import closed
```

This substrate can be implemented locally without provider calls.

### B. Configured-provider execution binding authority

```text
status = REQUIRED
```

Automated reconciliation must resolve the exact configured provider execution identity that owned the historical reality exit.

Required properties:

```text
stronger than provider_id
durable across restart
originates from authoritative provider configuration/selection
captured before reality exit becomes historically ambiguous,
or linearly bound with the durable commitment that authorizes that exit
same-id replacement/drift detectable
no retargeting to current same-id provider
no historical backfill from current registry/config
no provider.reconcile / provider.invoke authority by itself
P5 import closed
```

Legacy dispatches without an original authoritative execution binding remain non-upgradable for automated reconciliation.

### C. Reconciliation repeatability authority

```text
status = REQUIRED FOR v1 AUTOMATED RECONCILIATION
```

Because v1 chooses repeat-safe-only automatic reconciliation, an exact repeatability authority is required before the consumer can re-enter a reconciliation reality query after S1/S2 ambiguity.

Required authority domain:

```text
exact reconciliation subject model
exact configured-provider execution binding
reconciliation protocol identity/version
repeatability contract version/digest
repeatability mode = repeat-safe
```

Required properties:

```text
business effect idempotency != reconciliation repeatability
provider_id != repeatability authority
caller cannot declare repeat-safe ad hoc
contract drift invalidates substitution
proof authorizes at most repeated provider.reconcile for exact subject
proof does not authorize provider.invoke or business retry
P5 import closed
```

Unknown or non-repeat-safe contracts are not automatically consumed in v1.

### D. RecoveryReconciliationAttemptRecorded / equivalent S1-S2 progress fact

```text
status = NOT REQUIRED FOR v1
production = NOT AUTHORIZED
```

Reason:

```text
v1 supports only exact repeat-safe reconciliation
→ after crash with no bound observation, the same exact query may be repeated
→ no extra attempt fact is needed for safety
```

A future design that wants automated support for non-repeat-safe/unknown providers may reopen this question. That would be a new responsibility slice.

No generic `RecoveryApplicationConsumed` fact is introduced.

## v1 crash model after substrate closure

```text
S0  before reconciliation reality exit
S1  reality query may have started
S2  provider returned a result
S3  exact application-bound RecoveryObservation durable
```

For an exact repeat-safe v1 contract:

```text
S0
→ may enter exact reconciliation query

S1/S2
+ exact target binding
+ exact repeat-safe authority
+ no bound observation
→ may repeat exact reconciliation query

S3
→ same RecoveryApplication provider calls = 0
```

For absent/unknown/non-repeat-safe/drifted repeatability:

```text
automatic reconciliation
= unsupported / fail closed
```

This freeze does not add an attempt fact to change that result.

## Dependency order

The production substrates are not one combined object. They remain independent responsibilities.

Recommended implementation order:

```text
A. application-bound RecoveryObservation local authority
↓
B. configured-provider execution binding authority
↓
C. reconciliation repeatability authority bound to exact B
↓
reconciliation-only consumer counterexample freeze
↓
consumer production
```

A can be implemented without execution integration.

B necessarily touches the authoritative provider-selection/reality-exit provenance chain and therefore must remain a separate production slice.

C must not exist as a free-floating caller assertion; it must bind the exact configured-provider execution identity/protocol subject established by B.

## Consumer preconditions after future substrate production

A future reconciliation consumer may proceed only if all of the following are proven:

```text
exact RecoveryApplication(kind=reconciliation-request)
exact source dispatch/Attempt/Step/Action graph
no existing application-bound RecoveryObservation
exact historical configured-provider execution binding
current resolver proves same exact configured-provider identity
exact repeat-safe reconciliation authority for that identity/subject/protocol
```

Then and only then:

```text
RealityBoundary.reconcile
→ store-owned application-bound RecoveryObservation
→ STOP
```

Still forbidden:

```text
fresh CapabilityRequest
InvocationPermit
fresh StepAttempt
InvocationDispatchCommitted
provider.invoke
Outcome
new RecoveryDisposition
new RecoveryApplication
business retry
```

## Production counterexample freeze

The following obligations must remain strict until their specific production slices are authorized and implemented:

```text
RSF-001 application-bound observation requires exact RecoveryApplication authority
RSF-002 one application derives one deterministic completion observation identity
RSF-003 bound observation direct append/import remains closed
RSF-004 configured-provider execution binding originates from authoritative provider path
RSF-005 execution binding capture precedes or linearizes with reality-exit authorization
RSF-006 same-id provider replacement cannot satisfy historical binding
RSF-007 legacy execution binding backfill remains closed
RSF-008 repeatability authority binds exact subject/provider execution/protocol/version
RSF-009 repeatability authority binds the exact configured-provider execution binding
RSF-010 absent/unknown/drifted repeatability fails closed
RSF-011 v1 automatic reconciliation rejects non-repeat-safe/unknown contracts
RSF-012 all three substrate authorities remain non-executing by themselves
```

Permanent negative v1 decision:

```text
RecoveryReconciliationAttemptRecorded
= NOT REQUIRED / NOT AUTHORIZED

RecoveryApplicationConsumed
= NOT REQUIRED / NOT AUTHORIZED
```

## Authorization boundary after this freeze

Merging this freeze means only:

```text
A application-bound observation substrate
= REQUIRED BY DESIGN

B configured-provider execution binding substrate
= REQUIRED BY DESIGN

C exact repeatability authority substrate
= REQUIRED BY DESIGN FOR v1 AUTOMATED RECONCILIATION

D reconciliation attempt/progress fact
= NOT REQUIRED FOR v1 / NOT AUTHORIZED
```

It does **not** by itself authorize production code for A/B/C.

Each production slice must still have an independent implementation branch, counterexample graduation, exact-head CI, PR review, merge-context gate, and separate rollback point.

## Explicitly unchanged

```text
automated reconciliation consumer
= NOT AUTHORIZED

DIS-015
= UNPROVEN

PVP-007
= UNPROVEN

retry execution chain
= CLOSED

P5
= CLOSED / UNSUPPORTED
```

## Freeze conclusion

The minimum safe v1 substrate set is exactly three independent authorities:

```text
1. application-bound completion observation
2. configured-provider historical execution identity
3. exact repeat-safe reconciliation contract
```

No fourth generic consumption/attempt authority is justified for the repeat-safe-only v1 path.