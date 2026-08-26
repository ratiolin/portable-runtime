# F1-B4 retry exact-source-provider pin / idempotency-domain audit

Baseline: `main@a7707aac5c612a5c2b0277fccb926e47d9187392`.

This audit is design/counterexample work only. It introduces no retry materializer, no provider pin production API, no idempotency-domain protocol, no DurableInvocationSpecification, no Runtime consumption, and no provider execution.

Its purpose is deliberately narrow:

```text
For the first automated retry version,
can cross-provider idempotency-domain design be avoided
by requiring retry to target the exact source provider?
```

## Executive conclusion

Yes, with an important qualification.

For a first safe automated retry implementation, a generic cross-provider idempotency/deduplication-domain abstraction is **NOT REQUIRED** if retry is restricted to the exact durable source-provider execution identity.

But:

```text
same provider_id string
!= same provider execution identity
!= same idempotency/deduplication authority
```

The current durable graph is insufficient to prove that exact identity.

`RecoveryApplication(retry-request)` durably retains:

```text
source_provider_id
source idempotency_key
source dispatch / Attempt / Step / Action / request / Run / Work refs
```

The original dispatch also durably binds `provider_id` to request/Attempt and authority digests.

However, it does **not** durably bind a stable provider execution identity such as a provider instance/contract identity, provider descriptor version, semantic-contract digest, or idempotency-domain identity.

The live `ProviderRegistry` explicitly permits unregistering one provider and later registering another provider object under the same `provider_id`. Therefore a future retry cannot use current registry lookup plus string equality as proof that it is targeting the same external idempotency authority.

## Existing recovery eligibility

Current recovery classification already makes a useful distinction:

```text
pure / idempotent / deduplicatable
→ idempotent-retry

reconcilable
→ reconcile

irreversible-opaque / unsupported
→ unknown
```

A committed attempt is never treated as a fresh invocation. Retry classification also requires preservation of the same idempotency identity.

This audit preserves that split. It does not broaden retry eligibility.

## Why exact provider pin helps

A cross-provider retry has two distinct proof obligations:

```text
1. same operation meaning
2. same external idempotency/deduplication domain
```

The second obligation is difficult to prove generically. Two providers may accept the same textual idempotency key while applying it to unrelated stores, tenants, credentials, accounts, gateways, or external APIs.

Therefore this rule is unsafe:

```text
provider A + key K
→ provider B + key K
→ assume same external effect identity
```

A first version can remove this entire cross-provider proof obligation by requiring:

```text
retry target execution identity
== exact source provider execution identity
```

This is a deliberate capability restriction, not a claim that provider migration is impossible forever.

## Provider id is not enough

`ProviderDescriptor` currently has:

```text
id
name
version
provider_family
operator
execution_domain
credential_domain
...
```

but the durable dispatch/recovery graph currently carries only the provider id for the execution binding.

The live registry can perform:

```text
unregister("provider:a")
register(new_provider_whose_id_is_also_provider:a)
```

and treats this as a new live registration. It even resets circuit state because the replacement may be unrelated.

Therefore:

```text
current registry provider.id == source_provider_id
```

is necessary for a v1 exact pin but is not sufficient proof.

## Required durable provider execution binding

Before automated retry production, the source invocation/specification must durably bind enough stable provider identity to make exact pin verifiable.

The audit does **not** freeze the final schema, but future design must be able to prove something conceptually equivalent to:

```text
source provider binding
    provider_id
    + stable provider descriptor / implementation identity
    + provider semantic-contract identity/version
    + replay/idempotency scope identity where required
```

The exact representation may be narrower if a provider proves stronger invariants.

Important:

```text
provider version string alone
!= idempotency-domain proof
```

and:

```text
provider semantic contract
!= execution authorization
```

This provider binding is replay/provenance eligibility, not permission to execute.

## Historical dispatches remain non-upgradable

Existing historical `InvocationDispatchCommitted` facts do not carry a stable provider execution binding beyond provider id.

They must not be upgraded after the fact by reading the current registry and saying:

```text
current provider id/version looks compatible
→ therefore old dispatch was bound to this identity
```

That would turn current mutable state into fabricated historical provenance.

Therefore:

```text
historical dispatch without original stable provider binding
→ automated exact retry ineligible
```

unless an independently authoritative historical fact already proves the missing binding.

No automatic backfill is authorized.

## Hard pin, not routing preference

Current routing supports `preferred_provider_ids`, but preference is not a hard retry pin.

A preferred source provider can be unavailable or ineligible and routing may then choose another candidate.

For first-version exact retry, the requirement is stronger:

```text
eligible target set = {exact bound source provider}
```

If that exact provider is unavailable, stale, disabled, semantically drifted, or cannot satisfy current qualification/policy/authorization constraints:

```text
STOP / hold / new recovery decision
```

not:

```text
fallback to another provider
```

## Exact pin does not resurrect authority

Even after a future exact-provider binding exists, it proves only replay target eligibility.

It does not prove:

```text
current qualification
current governance admission
current authorization
current policy approval
current provider health
current lease/fencing validity
fresh InvocationPermit
fresh Attempt
fresh dispatch
```

A retry must still re-enter the existing RealityBoundary and obtain all fresh execution authority.

The correct future shape remains:

```text
RecoveryApplication(retry-request)
+ exact DurableInvocationSpecification
+ exact stable source-provider binding
+ same idempotency identity
        ↓
materialize fresh CapabilityRequest
        ↓
current qualification / governance / policy / authorization
        ↓
fresh InvocationPermit
        ↓
fresh Attempt
        ↓
fresh dispatch
        ↓
exact pinned provider
```

## Idempotency identity preservation

P4a already retains the source `idempotency_key` for `retry-request` and fails preparation if it is missing.

For v1 exact retry:

```text
source idempotency_key
== retry idempotency_key
```

must be exact.

Changing the key creates a different external replay identity and must not be interpreted as retry of the same uncertain effect.

The idempotency key remains replay identity only; it is not authorization.

## Provider semantic-contract drift

The provider-visible request partition audit established that provider operation semantics require an explicit semantic contract/versioning model.

Exact-provider retry therefore also requires compatibility with the exact source provider semantic contract/specification binding.

A live provider with the same provider id but a changed semantic contract cannot silently consume an old durable operation specification.

Conceptually:

```text
same provider id
+ changed provider semantic contract
→ exact retry ineligible / revalidation required
```

This is independent from current authorization freshness.

## Provider version drift

`ProviderDescriptor.version` exists today, but the source dispatch does not durably bind it.

Future production may decide that provider version participates directly in stable provider execution identity, or that another immutable provider-binding digest subsumes it.

This audit freezes only the requirement:

```text
implementation/provider identity drift must be detectable
```

It does not decree that raw `version` is the final canonical field.

## What happens when the exact provider is gone

The safe first-version behavior is intentionally restrictive:

```text
source exact provider unavailable
→ no automated retry
```

Recovery may later produce a different decision, such as manual resolution, reconciliation where applicable, or a future explicitly proven cross-provider replay path.

But the current `retry-request` must not silently widen its target set.

## Cross-provider retry remains a separate future capability

If future product requirements demand:

```text
provider A
→ provider B
```

for the same uncertain external effect, then the runtime needs an explicit proof that both provider bindings share one stable external idempotency/deduplication domain.

That future proof may involve:

```text
external API/account/tenant identity
credential domain
provider gateway identity
provider-declared deduplication contract
stable idempotency namespace/version
```

A declaration such as:

```text
idempotency_domain = "payments"
```

is not automatically sufficient. Domain identity must have actual proof semantics.

Therefore:

```text
cross-provider idempotency-domain abstraction
= DEFERRED / REQUIRED ONLY FOR CROSS-PROVIDER RETRY
```

not required for the first exact-provider-pinned retry capability.

## Frozen counterexamples

### EPP-001 — changed provider id

A retry target whose provider id differs from the source provider must fail closed in v1.

### EPP-002 — same id, replaced provider identity

Unregister/register replacement under the same provider id must not satisfy exact-provider replay binding.

### EPP-003 — missing historical stable provider binding

A source dispatch/specification that never durably bound stable provider execution identity cannot become automated-retry eligible through current registry inspection.

### EPP-004 — missing idempotency identity

A retry application without exact source idempotency identity is ineligible.

### EPP-005 — changed idempotency identity

Changing the idempotency key must fail closed.

### EPP-006 — non-retryable effect semantics

`reconcilable` must stay on reconciliation path; opaque/unknown effects must not enter idempotent retry merely because an idempotency key exists.

### EPP-007 — exact provider unavailable

If the exact bound source provider is unavailable, v1 must STOP rather than fall back to another provider.

### EPP-008 — routing preference is not a pin

`preferred_provider_ids=[source]` must not count as exact replay targeting because current routing may choose a fallback candidate.

### EPP-009 — provider pin is non-authorizing

Exact replay-provider eligibility must create no qualification, authorization, InvocationPermit, Attempt, dispatch, or provider-call authority.

### EPP-010 — semantic-contract/provider identity drift

Same provider id with changed stable semantic/provider binding must invalidate exact retry eligibility or require explicit revalidation/new specification.

### EPP-011 — cross-provider same-looking key

Two different providers presenting the same textual idempotency key remain unsupported without an authoritative shared-domain proof.

### EPP-012 — no production retry authorization

The existence of this audit or a future exact-provider binding object must not itself authorize retry materialization or execution.

## Audit decision

```text
first automated retry target
= exact source-provider execution identity only

cross-provider retry
= unsupported in v1

generic cross-provider idempotency-domain abstraction
= NOT REQUIRED for v1

stable durable source-provider execution binding
= REQUIRED

provider_id string equality alone
= REJECTED as proof

preferred_provider_ids as retry pin
= REJECTED

historical provider binding backfill from current registry
= REJECTED

source idempotency identity preservation
= REQUIRED

fresh execution authority after replay eligibility
= REQUIRED
```

## What remains before DurableInvocationSpecification production

After the provider-visible partition audit and this exact-provider audit, the production preconditions are now narrow enough to freeze as counterexamples:

```text
1. explicit provider semantic projection contract
2. canonical semantic projection identity
3. stable source-provider execution binding
4. exact replay/idempotency identity
5. store-owned durable specification commit/replay
6. dispatch binds exact specification + provider binding
7. historical facts without those bindings remain fail closed
```

The next slice should still be a production-counterexample freeze for `DurableInvocationSpecification`, not implementation.

## Non-scope

This audit does not authorize:

```text
provider binding production schema
ProviderSemanticContract production API
DurableInvocationSpecification production
retry materialization
Runtime recovery consumption
cross-provider retry
cross-provider idempotency-domain protocol
provider fallback
InvocationPermit reuse
Attempt reuse
dispatch reuse
provider execution
P5 import / portability authority
```
