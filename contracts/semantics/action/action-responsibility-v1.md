# Action Responsibility — `action-responsibility-1.0`

Status: stable
Canonical owner: `portable-runtime/contracts`

This contract governs the path from a qualified/authorized runtime intention to an effectful reality-boundary invocation.

## Core separation

```text
judgment
!= policy disposition
!= authorization
!= execution
!= verification
!= confirmed outcome
```

No earlier stage may silently substitute for a later stage.

## Reality boundary

Provider invocation is the unique effectful reality exit. Pre-boundary stages may generate, qualify, route, evaluate policy, authorize, prepare procedure and assess reliability, but they do not themselves establish that the external effect occurred.

## Minimum action responsibilities

Effectful execution must preserve enough information to answer:

- what purpose/context was in force;
- what exact actor/capability/resource/version was authorized;
- what provider/request crossed the boundary;
- which procedure and reliability gates applied;
- what was observed after execution;
- what verification, recovery, compensation or reopen responsibilities remain.

## Procedure and irreversibility

Procedure profiles may be minimal, standard or enhanced, but hard boundaries cannot be waived by profile convenience. If correction/recovery cannot outrun irreversible exposure, the runtime must narrow, defer, block, or require stronger authority rather than treating observability as reversibility.

## Historical integrity

A rollback, compensation or later revision does not erase the fact that an Action occurred. Corrective work is additional history.

## Authority ceiling

A `GovernedApplication` commits governance state; it is not an Action. A successful provider response records execution facts; it is not confirmed objective completion. Only the appropriate verification/completion authority may establish the corresponding terminal product fact.