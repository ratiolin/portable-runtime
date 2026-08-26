# F1-B4 configured-provider reconciliation target audit

Baseline: `main@ed8f2f65598e4405afdff13904d6c9e858d69880`.

This audit opens only the historical reconciliation-target identity question. It does not authorize provider-target production/schema, dispatch changes, registry authority changes, reconciliation provider calls, repeatability production, RecoveryObservation application-binding production, Runtime consumption, DIS-015, PVP-007, retry, fresh invocation authority, historical backfill, or P5 import authority.

## Question

The accepted reconciliation topology requires a later reality query to address the same historical provider execution subject that owned the original reality exit:

```text
historical InvocationDispatchCommitted
→ exact configured-provider execution identity that owned reality exit
→ later exact reconciliation target resolution
→ STOP
```

The question is not:

```text
which provider currently has the same provider_id?
```

It is:

```text
which durable configured execution identity actually owned the historical reality exit,
and can the current runtime prove that it is resolving that same identity now?
```

## Current-state findings

Current `InvocationDispatchCommitted` identity and payload bind `provider_id`, but no configured-provider execution-binding identity or digest.

Current `ProviderRegistry` is explicitly a live runtime registry. It supports:

```text
unregister(provider_id)
register(new_provider_with_same_id)
get(provider_id) -> current object
```

Therefore current registry membership answers present routing state only. It is not historical target authority.

Current `ProviderReplayBinding` is also insufficient for this responsibility. Its production contract explicitly says that it is a locally self-validating representation of a caller-declared replay binding and is **not** proof that the binding names the authoritative configured provider instance.

Thus none of the following is sufficient historical reconciliation-target authority:

```text
provider_id
descriptor equality
provider version equality
current registry membership
Python object identity
local ProviderReplayBinding
caller-declared binding string
```

Python object identity is especially ineligible because it is not durable across process boundaries.

## Required identity semantics

A future authority may be conceptually equivalent to `ProviderExecutionBinding` or `ConfiguredProviderExecutionIdentity`, but this audit does not authorize a production schema or final name.

The authority must represent a stable configured execution identity that is stronger than provider id and recoverable across process restart. It must distinguish replacement/drift under the same provider id.

A future semantic domain must be able to answer at least:

```text
provider_id
stable configured execution identity
provider configuration / execution-domain identity
provider/protocol identity needed to resolve the same target
binding version/digest
originating authoritative configuration/selection reference
```

Exact field choices remain deferred.

## Authority source

The execution binding must originate from an authoritative configured-provider selection/configuration path. It cannot be supplied as an arbitrary string by a reconciliation caller, dispatch caller, or invocation-specification capture caller.

Valid direction:

```text
authoritative provider configuration / selection
→ exact configured execution binding
→ durable historical binding
```

Invalid direction:

```text
historical provider_id
+ current registry/configuration
→ infer historical execution identity
```

The second path is permanently fail-closed for history that lacks an original authoritative binding.

## Capture timing

The binding must become durable before a provider reality exit can become historically ambiguous.

The audit freezes the following requirement:

```text
exact configured-provider execution binding
→ durable before reality exit,
  or atomically / linearly bound with the durable commitment that authorizes reality exit
```

A future implementation may choose the exact linearization point, but it must preserve this ordering property.

The invalid crash seam is:

```text
provider reality exit may have occurred
+ no durable exact execution binding
→ historical reconciliation target unknowable
→ automated reconciliation forbidden
```

Persisting the binding after the provider call is not sufficient historical authority, because a crash may occur between reality exit and persistence.

This audit does not modify `InvocationDispatchCommitted` or authorize any new pre-call fact.

## Historical identity vs current resolvability

Historical identity and current availability are distinct responsibilities.

```text
exact historical binding exists
+ current resolver proves same exact identity
→ target resolvable
```

```text
exact historical binding exists
+ no current matching identity
→ target unavailable
→ fail closed / manual recovery
```

```text
same provider_id exists
+ configured execution identity differs
→ target mismatch
→ fail closed
```

The system must never silently retarget reconciliation to a same-name or same-id provider.

## Relationship to repeatability

Execution-target identity is independent from reconciliation repeatability.

```text
exact ProviderExecutionBinding
!= ReconciliationRepeatabilityContract
```

A target binding can prove **who** owned the historical reality exit. It does not prove whether it is safe to ask that target again after an ambiguous crash.

Conversely, a repeatability contract does not identify the historical configured provider target by itself.

## Relationship to local ProviderReplayBinding

The existing local invocation-specification replay binding remains useful only as representation/provenance for invocation meaning and replay identity.

```text
ProviderReplayBinding
= locally deterministic representation
!= authoritative configured-provider execution identity
```

This audit explicitly rejects upgrading that local representation into execution authority without an authoritative execution/registry integration path.

## Counterexample freeze

```text
PT-001  provider_id != historical configured-provider execution identity
PT-002  current registry object != historical target authority
PT-003  same-id provider replacement cannot satisfy historical binding
PT-004  descriptor equality alone != configured execution identity
PT-005  local ProviderReplayBinding representation != execution authority
PT-006  caller cannot manufacture provider execution binding
PT-007  binding must originate from authoritative configured-provider path
PT-008  historical binding cannot be backfilled from current registry/configuration
PT-009  binding drift under same provider_id must be detectable
PT-010  exact historical binding + no current resolver => unavailable, not retargeted
PT-011  exact historical binding + mismatched current provider => fail closed
PT-012  execution binding does not authorize provider.reconcile
PT-013  execution binding does not authorize provider.invoke or business retry
PT-014  execution binding does not imply reconciliation repeatability
PT-015  legacy dispatch without original execution binding remains non-upgradable
PT-016  serialized/import authority remains P5-closed
PT-017  reality exit may have occurred without durable binding => target unknowable and automated reconciliation forbidden
```

## Production implications

This audit deliberately does not decide the production object, capture API, registry resolver shape, or whether the binding should be embedded in or referenced by a dispatch commitment.

A later reconciliation substrate production decision must separately decide:

```text
1. authoritative source of configured execution identity
2. durable identity representation
3. capture linearization relative to provider reality exit
4. current resolution mechanism and mismatch semantics
5. relationship to repeatability authority
6. legacy-history fail-closed posture
```

No historical backfill is authorized.

## Explicitly unchanged

```text
RecoveryObservation ↔ RecoveryApplication binding semantics
= AUDITED

reconciliation repeatability semantics
= AUDITED

configured-provider reconciliation target semantics
= AUDIT OPEN IN THIS SLICE

provider-target production/schema
= NOT AUTHORIZED

application-binding production
= NOT AUTHORIZED

repeatability production/schema
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
historical reality exit
→ must have an exact durable configured-provider execution identity
→ later reconciliation may target only a currently resolved identity proven equal to that historical identity
```

Current `provider_id` and current registry state do not satisfy this responsibility.

For legacy dispatches that lack an original authoritative execution binding:

```text
current registry/configuration
cannot manufacture historical authority
```

Automated reconciliation for such history must remain fail closed.