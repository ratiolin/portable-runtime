# F1-B4 RecoveryObservation ↔ RecoveryApplication binding audit

Baseline: `main@d195debed4179c6695e76fcc496567f30144a13f`.

This audit opens only the local authority question:

```text
RecoveryApplicationRecorded(kind=reconciliation-request)
→ exact durable application/source reconstruction
→ one durable application-bound RecoveryObservation
→ STOP
```

It does not authorize reconciliation provider calls, provider repeatability production, configured-provider target binding, Runtime consumption, `DIS-015`, `PVP-007`, retry, fresh request/permit/Attempt/dispatch creation, `provider.invoke`, Outcome authority, RecoveryDisposition creation, historical backfill, or P5 import authority.

## Current-state finding

Current `RecoveryApplication` already retains exact durable provenance to one disposition and its source dispatch / Attempt / Step / Action / request / provider id.

Current `RecoveryObservation` is intentionally more general. Its commit request accepts:

```text
observation_instance_ref
dispatch_commit_ref
observation_source
reported_status
provenance_refs
```

and reconstructs the exact dispatch graph before recording one execution-level observation.

It does **not** carry a first-class `recovery_application_ref`.

Current observation identity is derived from caller-supplied `observation_instance_ref`, so multiple observations for one dispatch are legitimate P1 facts. Current legacy `Runtime.reconcile(step_id)` also allocates a new observation instance for every reconciliation call.

Therefore historical facts such as:

```text
RecoveryObservationRecorded
observation_source = provider-reconcile
provenance_refs = [provider-id]
```

must never be reinterpreted as proof that a particular `RecoveryApplication` responsibility was consumed.

## Compatibility rule

The new authority must be additive, not retroactive.

```text
legacy RecoveryObservation
recovery_application_ref = absent
→ remains a valid execution-level observation
→ NOT reconciliation-consumption completion
```

A future application-bound observation may carry:

```text
recovery_application_ref = exact RecoveryApplicationRecorded id
```

but only after store-owned reconstruction proves the application/dispatch graph.

The string `observation_source = "provider-reconcile"` and opaque `provenance_refs` are citations only. They do not establish application authority.

## Required store-owned derivation

The caller must not be allowed to assert an arbitrary application↔dispatch relation.

The narrow future request surface should be equivalent to:

```text
RecoveryApplicationObservationCommitRequest
    recovery_application_ref
    observation_source
    reported_status
    provenance_refs
```

The caller does **not** provide:

```text
dispatch_commit_ref
observation_instance_ref
attempt_ref
action_ref
step_ref
request_ref
provider_id
```

The store must reconstruct:

```text
exact RecoveryApplicationRecorded
        ↓
application_kind == reconciliation-request
        ↓
exact RecoveryDisposition
        ↓
exact source InvocationDispatchCommitted
        ↓
exact Attempt / Step / Action / request/provider graph
        ↓
verify application source refs still match that graph
        ↓
derive application-bound observation identity
```

A stale, forged, cross-dispatch, or wrong-kind application fails closed.

## One application → one durable completion identity

Generic RecoveryObservation semantics intentionally permit many observations per dispatch. Application-consumption completion needs a narrower identity rule.

For one exact application `A`:

```text
ApplicationObservationKey(A)
= H(
    schema,
    semantic-role = reconciliation-application-observation,
    recovery_application_ref = A
  )
```

The reported result, provenance, timestamps, and current provider state are **not** part of this identity.

Consequences:

```text
same application + same observation semantics
→ one durable observation identity
→ replay
```

```text
same application + different reported/provenance semantics
→ same identity + different semantics
→ rebound/conflict
→ fail closed
```

This is deliberately stricter than allocating a new observation instance after every provider query. A single RecoveryApplication cannot accumulate arbitrary competing completion facts.

The stable identity may be implemented by deriving a canonical observation instance from the application identity or by an equivalent dedicated key. The audit freezes the semantic property, not a particular helper name.

## Completion meaning

A bound observation proves only that one application responsibility obtained one durable execution-level observation.

```text
RecoveryObservation(recovery_application_ref=A)
!= Outcome
!= RecoveryDisposition
!= new RecoveryApplication
!= terminal completion
!= provider execution authorization
```

The binding does not decide whether an external reconciliation call is safe to repeat. That remains the independent repeatability blocker.

The binding also does not prove the historical provider target identity. That remains the independent configured-provider binding blocker.

## Replay implication for later consumption

Once a valid application-bound observation exists:

```text
same RecoveryApplication A
+ exact bound RecoveryObservation O
→ A already has durable completion observation
→ future reconciliation consumer must perform provider calls = 0
```

A second reconciliation responsibility requires a new cycle:

```text
O
→ new RecoveryDisposition
→ new RecoveryApplication A2
→ new application-bound observation identity
```

Thus:

```text
same RecoveryApplication
!= unlimited implicit reconcile loop
```

## Counterexample freeze

This audit freezes the following obligations.

```text
AB-001 opaque provenance/application-looking strings != application authority
AB-002 caller cannot supply dispatch/instance identity for application-bound observation
AB-003 exact durable RecoveryApplication is required
AB-004 application kind must be reconciliation-request
AB-005 application source dispatch/Attempt/Step/Action graph is reconstructed and must match
AB-006 legacy unbound RecoveryObservation remains valid but is not application completion
AB-007 one exact application derives one stable bound observation identity
AB-008 same application + same semantics replays one durable fact
AB-009 same application + changed reported semantics is rebound/conflict
AB-010 same application cannot accumulate arbitrary second completion observations
AB-011 bound observation remains execution-level only: not Outcome/Disposition/Application authority
AB-012 bound observation commit creates no new disposition/application/execution authority
AB-013 direct RecoveryObservation event append remains closed
AB-014 serialized/P5 application-bound observation authority remains closed
```

## Identity and schema compatibility

No historical observation is auto-upgraded.

A future decoder must distinguish:

```text
unbound legacy observation
→ valid P1 execution fact

application-bound observation
→ valid only when exact application binding is present and internally coherent
```

Historical `provider-reconcile` source values are not enough to select the second interpretation.

Whether the production implementation uses an additive optional field within the current observation schema or a compatible schema revision is intentionally left open. The invariant is that legacy events remain decodable and non-authoritative for application completion.

## Production gate

This audit does **not** authorize production.

A later minimal local binding slice may be considered only if it can prove all of the following without invoking a provider:

```text
1. store-owned exact RecoveryApplication reconstruction
2. reconciliation-request kind check
3. exact application ↔ source dispatch graph validation
4. deterministic one-application/one-observation identity
5. replay before any future external action
6. rebound detection for changed semantics
7. legacy unbound observation compatibility
8. direct-event bypass remains closed
9. P5 remains closed
10. no Outcome / RecoveryDisposition / new RecoveryApplication side effects
```

## Explicitly unchanged

```text
reconciliation topology
= AUDITED / VALID

automated reconciliation production
= BLOCKED / NOT AUTHORIZED

provider reconciliation repeatability
= UNPROVEN

configured-provider reconciliation target binding
= UNPROVEN

PVP-007
= UNPROVEN

DIS-015
= UNPROVEN

retry execution chain
= CLOSED

P5
= CLOSED / UNSUPPORTED
```
