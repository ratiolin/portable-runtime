# F1-B2 Verified Outcome Authority Closure

## Scope

F1-B2 defines the authority boundary by which persisted, bound objective verification may authorize a canonical `OutcomeRecord` with `lifecycle_status="confirmed"`.

The public entry point is `VerifiedOutcomeAuthority.confirm(...)`. It is intentionally a thin semantic façade. The façade constructs a `VerifiedOutcomeCommitRequest` and delegates to `StateStore.commit_verified_outcome(...)`. It does not independently validate evidence, derive objective results, construct authority identifiers, open transactions, or repair imported history.

## Authority path

```text
caller
  ↓
VerifiedOutcomeAuthority
  ↓
VerifiedOutcomeCommitRequest
  ↓
StateStore.commit_verified_outcome
  ↓
prepare_verified_outcome_commit
  ↓
BoundVerificationEvidenceValidator
  ↓
atomic durable commit
  ├─ OutcomeRecord(confirmed)
  ├─ ObjectiveVerificationAccepted
  └─ OutcomeConfirmed
```

There is one authority implementation. `VerifiedOutcomeAuthority` is an API façade over the store-owned P4 primitive; it is not a second implementation.

## Non-bypassability closure

```text
normal canonical write
    → P2 rejects direct confirmed Outcome writes

live verified authority
    → P4 deterministically derives and atomically commits
      the confirmed Outcome plus both authority events

state / bundle import
    → P5 replays the complete post-merge candidate graph
      against the same deterministic preparation semantics
```

Therefore F1-B2 guarantees:

```text
persisted bound objective verification
    ↓
verification-authorized confirmed Outcome

confirmed Outcome authority is non-bypassable across:
    normal canonical writes
    live authority commits
    state imports
    bundle imports
```

Import validation is validation, not repair. A historical confirmed Outcome without a reconstructible P4 authority graph is incompatible history and fails closed. The runtime does not demote it to `recorded` and does not synthesize missing authority events.

## Responsibility exclusions

```text
confirmed Outcome
    != continued qualification
    != automatic disqualification
    != governance discharge
    != ReviewObligation discharge
    != terminal completion authority
    != recovery closure
```

Provider-attached verification remains non-authoritative by itself. A persisted `OutcomeRecord(recorded)` remains a non-authoritative observation and does not acquire F1-B2 authority.

## Conformance freeze

The F1-B2 conformance set requires:

- FB2-001 / 002: pass/fail bound objective verification confirms through the public façade.
- FB2-004 / 005 / 006 / 008: identity, scope/version, missing-proof, and proof-reuse failures fail closed through the façade.
- FB2-007: façade replay preserves deterministic Outcome identity.
- FB2-009: the façade does not weaken store-owned atomic rollback.
- FB2-A01 / A02 / A03: direct-write bypass, inconsistent multi-proof closure, and forged import closure remain required failures.
- FB2-003 / 010: provider-attached verification and recorded Outcomes remain non-authoritative.
- FB2-011 / 012: confirmed Outcomes do not discharge governance and do not authorize terminal completion.

This document is the semantic freeze between F1-B2 and F1-B3. F1-B3 may define governance consequences of verified Outcomes only after a separate design freeze. No F1-B3 production semantics are part of this closure.
