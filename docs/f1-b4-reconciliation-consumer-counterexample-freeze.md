# F1-B4 reconciliation consumer counterexample freeze

Baseline: `main@3bacf684894b0ef37642a0ae4983a35dd46be4a8`.

This is an **audit-only** freeze. It authorizes no production consumer, no provider call, no runtime integration, no reality-boundary API change, no new durable responsibility object, no retry, no P5 authority import, and no Experience Governance work.

Production source changes in this audit are required to remain **zero**.

## Design verdicts

The audit freezes exactly three verdicts:

```text
Reconciliation consumer architecture
= JUSTIFIED

new durable reconciliation-attempt fact
= NOT REQUIRED for repeat-safe-only v1

RecoveryApplicationConsumed
= NOT REQUIRED
```

Production remains **NOT AUTHORIZED** by this audit.

## Current-state finding

The current compatibility surfaces cannot be promoted directly into an authoritative reconciliation consumer.

`Runtime.reconcile(step_id)` currently begins from a Step, selects the latest StepAttempt, reads its `request_ref` and `provider_id`, calls `self.capabilities.reconcile(last.request_ref, last.provider_id)`, and writes a generic `RecoveryObservationCommitRequest`. It does not begin from one exact durable `RecoveryApplication(kind=reconciliation-request)` and does not require A, B, or C.

`RealityBoundary.reconcile(request_id, provider_id)` currently calls `registry.get(provider_id)` and then invokes that currently registered provider's `reconcile(request_id)`. This is incompatible with the historical-target semantics already frozen by B: exact historical target proof cannot be discarded at the last reality-exit step and replaced by a fresh same-name registry lookup.

Therefore:

```text
Runtime.reconcile(step_id)
!= authoritative reconciliation consumer

RealityBoundary.reconcile(request_id, provider_id)
!= authoritative exact-target reconciliation seam
```

Both may remain legacy compatibility surfaces until a later production slice explicitly closes or redirects them, but neither may remain an automated authority bypass once the authoritative consumer is introduced.

## Required consumer topology

The authoritative consumer must begin from one opaque application identity only:

```text
exact RecoveryApplication ref
→ reconstruct exact RecoveryApplicationRecorded
→ require application_kind = reconciliation-request
→ reconstruct exact RecoveryDisposition
→ reconstruct exact source InvocationDispatchCommitted
→ reconstruct exact Attempt / Step / Action / request

→ A check:
   exact application-bound RecoveryObservation already exists?
      yes
      → replay existing completion
      → provider calls = 0
      → STOP

→ B check:
   decode exact historical ProviderExecutionBinding
   resolve exact current configured execution identity
   reject same-id retargeting or unavailable exact target

→ C check:
   decode exact historical ReconciliationRepeatabilityAuthority
   require exact request-id subject
   require exact historical/current B match
   require exact protocol/version/contract equivalence
   require eligible = true

→ exact-target reconciliation reality exit
→ returned reconciliation fact
→ store-owned A application-bound RecoveryObservation commit
→ STOP
```

No stage in this topology grants fresh invocation authority.

## A-first ordering is semantic, not an optimization

The A completion check must occur **before** B resolution, C evaluation, or any current-registry dependency.

Once one exact application-bound RecoveryObservation is durable, that application responsibility is already completed as a historical fact. Later provider removal, configured-target drift, protocol drift, or repeatability-contract drift cannot reopen it.

Required behavior:

```text
A exists
→ same RecoveryApplication provider calls = 0
→ replay existing completion
→ STOP
```

Forbidden behavior:

```text
A exists
+ current B unavailable
→ error

A exists
+ current C drifted
→ error
```

Those paths would make current configuration state stronger than durable responsibility completion and would resurrect a discharged responsibility.

## Consumer request surface

The future caller-facing authority request should be minimal in semantic content:

```text
RecoveryReconciliationRequest(
    recovery_application_ref
)
```

The exact production type or API name is **not frozen** by this audit. The frozen property is that the caller supplies only the opaque exact RecoveryApplication reference.

The caller must not supply or override:

```text
dispatch_commit_ref
request_id
provider_id
provider_execution_binding_ref
repeatability_authority_ref
observation_ref
reported_status
```

Those values must be reconstructed from the exact durable RecoveryApplication authority graph or obtained from the provider result after the single authorized reconciliation reality exit.

A consumer that accepts caller-assembled A/B/C references is not authoritative even when each individual reference is valid.

## Exact-target reality-exit seam

The future consumer must not reuse the current low-level behavior that performs a naked provider-id lookup at the reality exit.

A future seam may conceptually resemble either:

```text
reconcile_exact_target(
    exact_resolved_provider_execution_target,
    exact_historical_request_id,
)
```

or:

```text
reconcile_bound(
    exact_historical_request_id,
    historical_provider_execution_binding,
)
```

The concrete name and signature are intentionally not frozen here.

The frozen property is:

```text
B exact target proof
→ exact B resolution
→ same resolved configured execution target crosses reality boundary
```

The following is forbidden:

```text
B exact target proof
→ discard B
→ registry.get(provider_id)
→ reconcile
```

That would reopen the same-id retargeting counterexamples already closed by B.

## A store capability seam

Application-bound RecoveryObservation is intentionally available through opt-in authority stores rather than the baseline `portable_runtime.stores` surface.

The future consumer must depend on an exact capability/protocol equivalent to:

```text
get_recovery_application_observation(recovery_application_ref)
commit_recovery_application_observation(request)
```

The concrete protocol type is not frozen.

If the supplied StateStore does not expose both exact A authority capabilities:

```text
consumer unavailable
→ provider calls = 0
```

The consumer must not fallback to generic `commit_recovery_observation()` and must not import A authority subclasses into the baseline stores namespace merely for convenience.

This preserves the existing opt-in authority boundary and avoids recreating the previous store/workflow circular-dependency seam.

## Crash model

For one exact RecoveryApplication `A_r`, define:

```text
S0 = before reconciliation reality exit
S1 = reconciliation query may have started; previous query may still be in flight
S2 = provider returned reconciliation result; A completion not durable
S3 = application-bound RecoveryObservation is durable
```

The repeat-safe-only v1 rules are:

```text
S0
→ safe to enter the exact authorized reconciliation query

S1 or S2
+ exact B
+ exact eligible C
+ no durable A completion
→ same application may re-enter the exact reconciliation query

S3
→ same application provider calls = 0
```

### Repeat-safe includes overlap with an earlier possibly in-flight query

The S1 model is meaningful only if C's positive `repeat-safe` authority permits issuing the same exact reconciliation query while an earlier identical query may still be executing externally.

The consumer does **not** have to prove that the previous query terminated before re-entry.

Otherwise the post-crash S1 ambiguity would require an additional external-liveness fact that the current substrate does not possess, defeating the purpose of the repeat-safe authority.

This audit therefore freezes:

```text
C repeat-safe
= safe repetition of the exact reconciliation query
  even when an earlier identical query may still be in flight
```

It remains unrelated to business-operation idempotency and grants no `provider.invoke` or retry authority.

## Competing results and A linearization

Overlapping repeat-safe reconciliation queries may return different reported results.

That does not justify multiple application-completion observations or latest-wins semantics.

A already supplies one deterministic completion identity per RecoveryApplication:

```text
first durable A semantics
→ durable completion fact

same application
+ same semantics
→ replay

same application
+ incompatible later semantics
→ identity/semantics rebound
→ fail closed
```

The consumer must not create two application-bound observations and must not select the latest provider response as authority.

## Provider-return / A-commit seam

A provider result is only a returned execution-level reconciliation fact until the store-owned application-bound observation commit succeeds.

If the provider returns but A commit fails:

```text
no durable completion
→ consumer may report unknown/unavailable
→ must not report durable completion
→ no Outcome
→ no RecoveryDisposition
→ no new RecoveryApplication
```

Because C v1 is repeat-safe, a later call for the same application may re-enter the exact reconciliation query if A is still absent and B/C remain exact and eligible.

No `RecoveryReconciliationAttemptRecorded` is required to bridge this seam for v1.

## Why no new durable attempt fact is required

A new durable attempt fact would be justified only if the consumer needed to remember a reality-exit crossing that could not safely be repeated.

The current v1 intentionally authorizes only exact repeat-safe reconciliation queries:

```text
pre-A ambiguity
→ C permits exact repetition

post-A state
→ A terminates repetition
```

This pair already closes the crash seam.

Therefore:

```text
RecoveryReconciliationAttemptRecorded
= NOT REQUIRED for v1
= NOT AUTHORIZED by this audit
```

If a future non-repeat-safe reconciliation mode is introduced, that is a new architecture problem and must be audited independently rather than silently broadening this consumer.

## Why RecoveryApplicationConsumed is not required

The application-bound RecoveryObservation is the durable completion marker for this responsibility.

A generic consumed marker would duplicate responsibility state without solving an unresolved counterexample:

```text
RecoveryApplication
→ application-bound RecoveryObservation
→ responsibility completed
```

Therefore:

```text
RecoveryApplicationConsumed
= NOT REQUIRED
= NOT AUTHORIZED
```

## RCX counterexamples

### RCX-001 — Step/latest Attempt is not application authority

```text
step_id / latest Attempt
!= RecoveryApplication authority
```

The authoritative consumer must not begin from `Runtime.reconcile(step_id)` semantics.

### RCX-002 — Application absent

```text
RecoveryApplication absent
→ provider calls = 0
```

### RCX-003 — Wrong application kind

Only `application_kind = reconciliation-request` is eligible.

Any other RecoveryApplication kind results in zero provider calls.

### RCX-004 — Application source graph rebound

Any mismatch in application → disposition → dispatch → Attempt/Step/Action/request reconstruction fails closed before the reality boundary.

### RCX-005 — Existing A completion short-circuits everything

```text
exact bound RecoveryObservation exists
→ replay
→ provider calls = 0
→ STOP
```

This check occurs before B/C/current-registry resolution.

### RCX-006 — Generic observation is not A

A generic or legacy unbound RecoveryObservation remains a valid execution-level historical fact but does not complete a RecoveryApplication responsibility.

### RCX-007 — Historical B absent

A legacy dispatch without the original ProviderExecutionBinding is ineligible for automated reconciliation consumption.

No backfill.

### RCX-008 — Same provider id, different B

A current provider registered under the same `provider_id` but a different B identity is not the historical target.

Zero provider calls.

### RCX-009 — Historical B target unavailable

If exact historical B cannot resolve to the current configured execution identity, consumer is unavailable and provider calls remain zero.

### RCX-010 — Historical C absent

Current repeat-safe configuration cannot manufacture missing historical C authority.

Provider calls remain zero.

### RCX-011 — C subject mismatch

C must bind the exact historical dispatch `request_id` subject reconstructed from the application source graph.

Any other request id is ineligible.

### RCX-012 — C protocol/version/contract drift

Protocol identity/version or repeatability contract version/digest drift makes the application ineligible for a new external query while A is absent.

### RCX-013 — Current-only C is not historical authority

```text
historical C absent
+ current repeat-safe configuration
!= historical C
```

Zero provider calls.

### RCX-014 — A+B+C authorize only reconciliation reality exit

Exact A responsibility plus B target plus eligible C may authorize only the exact reconciliation query.

It never authorizes `provider.invoke`.

### RCX-015 — Exact request and exact target reach reality exit

The reality exit receives the exact historical request id and the exact configured execution target resolved from B.

No provider-id re-resolution is allowed afterward.

### RCX-016 — Returned fact must become A-bound observation

A provider reconciliation result must be persisted through the application-bound A commit surface.

A generic P1 RecoveryObservation is insufficient.

### RCX-017 — A commit failure is not durable completion

Provider result plus failed A commit yields unknown/unavailable, never durable completion or higher authority.

### RCX-018 — Post-call/pre-A crash may repeat under exact C

If an external reconciliation query may have started or returned but A is not durable, exact repeat-safe C permits the same application to re-enter the exact query.

The earlier query may still be in flight.

### RCX-019 — After A durable commit, later calls are zero-call replays

Once A is durable, all later calls for the same RecoveryApplication perform zero provider calls regardless of later B/C drift.

### RCX-020 — No fresh invocation chain

The consumer creates no:

```text
CapabilityRequest
InvocationPermit
StepAttempt
InvocationDispatchCommitted
provider.invoke
```

### RCX-021 — No automatic recovery decision chain

The consumer creates no:

```text
Outcome
RecoveryDisposition
RecoveryApplication
```

A new responsibility requires the existing observation → decision → new application governance chain outside this consumer.

### RCX-022 — No durable reconciliation attempt object for v1

`RecoveryReconciliationAttemptRecorded` remains unnecessary and unauthorized.

### RCX-023 — No generic consumed marker

`RecoveryApplicationConsumed` remains unnecessary and unauthorized.

### RCX-024 — Legacy Runtime.reconcile cannot remain an authority bypass

When the authoritative consumer is later produced, `Runtime.reconcile(step_id)` must not preserve an alternate automated path that reaches the provider without exact RecoveryApplication + A/B/C authority.

The exact compatibility treatment is deferred to production design.

### RCX-025 — P5/import/history cannot manufacture consumer authority

Serialized/imported caller claims, legacy history, provenance strings, current registry state, or assembled references cannot create consumer eligibility.

P5 remains closed.

## Production boundary frozen by this audit

This audit authorizes **no** implementation of the following:

```text
RecoveryReconciliationRequest
reconciliation consumer module/service
exact-target RealityBoundary reconcile API
Runtime consumer integration
legacy Runtime.reconcile closure/redirection
provider.reconcile call from new consumer
A store capability protocol in baseline interfaces
RecoveryReconciliationAttemptRecorded
RecoveryApplicationConsumed
P5 consumer authority import
retry
DIS-015
PVP-007
Experience Governance
```

The conceptual names above are explanatory vocabulary only unless already present in production. Future production may choose different API names while preserving the frozen responsibility boundaries.

## Exit gate

This audit is complete only if all of the following remain true:

```text
consumer architecture = JUSTIFIED
new durable attempt fact = NOT REQUIRED
RecoveryApplicationConsumed = NOT REQUIRED
production consumer = NOT YET AUTHORIZED
production source delta = 0
```

After merge: **STOP**.

The next possible stage, only under separate explicit production authorization, is a minimal reconciliation-only consumer slice:

```text
RecoveryApplication
→ A check
→ B exact resolution
→ C exact eligibility
→ exact reconciliation reality exit
→ A commit
→ STOP
```

Experience Use Authority remains outside this audit and is not opened here.
