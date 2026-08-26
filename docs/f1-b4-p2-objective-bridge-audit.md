# F1-B4 P2 objective-bridge design audit

## Baseline and scope

Audit baseline / B4-P1 rollback point:

`800157f687639b1d4b1ebe4121f8283fb0dd6b74`

This branch is design-audit only. It introduces no production semantics, no new record type, no new authority object, no RecoveryDisposition/Application, no import portability, no CompletionAuthority change, and no B3-P4 work.

The audit question is intentionally narrow:

```text
RecoveryObservation
how may it legally participate in F1-B2 objective verification
without creating a second Outcome authority?
```

## Existing F1-B2 authority boundary

F1-B2 already owns the objective authority chain:

```text
typed EvidenceArtifact
→ BoundVerificationEvidenceValidator
→ store-owned commit_verified_outcome()
→ confirmed Outcome
```

The validator requires typed closed-verification evidence and rechecks the exact execution graph, including Action / Attempt / Work / Run / request / provider / verification scope / subject-version binding and verifier provenance.

A RecoveryObservation is an Event-level durable execution report. It is not an EvidenceArtifact and therefore cannot be supplied directly as objective evidence.

## Audit findings

### 1. No recovery-specific Outcome authority is required

The existing `EvidenceArtifact` schema already has generic provenance surfaces (`source_refs`, metadata) capable of carrying RecoveryObservation references as verifier input provenance.

That does **not** make those references objective authority.

```text
RecoveryObservation(reported-succeeded)
!= EvidenceArtifact(pass)

RecoveryObservation ref present
!= objective verification passed
```

`VerifiedOutcomeAuthority` continues to trust only the typed EvidenceArtifact closure and its existing execution/scope/version/verifier bindings.

### 2. Generic RecoveryObservation citations are opaque to F1-B2

Current F1-B2 does not semantically interpret arbitrary extra `source_refs` or `recovery_observation_refs` as a recovery support edge. In particular, it does not re-read a cited RecoveryObservation and compare its dispatch/action/attempt identity.

This is an important boundary, not an implicit feature:

```text
EvidenceArtifact.source_refs += RecoveryObservation ref
!= runtime-validated observation provenance
```

Therefore a cross-action or stale RecoveryObservation citation must **not** be described as having supported the Outcome. If the EvidenceArtifact is otherwise valid, the authority source is the explicit verifier result in that EvidenceArtifact, not the opaque RecoveryObservation citation.

If a future product requirement demands runtime-attested RecoveryObservation provenance, that would justify a thin verifier-input validation seam. Such a seam would validate exact observation/dispatch/action/attempt bindings before an external verifier emits the ordinary EvidenceArtifact. It still would not own Outcome authority.

### 3. Existing F1-B2 bindings remain mandatory

Merely citing a RecoveryObservation cannot replace any existing F1-B2 requirement. Audit tests freeze failures for missing exact Action source binding and stale/wrong subject-version or attempt binding.

Thus:

```text
EvidenceArtifact merely cites RecoveryObservation
!= sufficient authority

existing Action/Attempt/Work/Run/scope/version checks
remain mandatory
```

### 4. Conflicting observations belong to verifier responsibility

P1 permits multiple valid execution facts for the same committed dispatch, including:

```text
obs-1 = reported-succeeded
obs-2 = reported-failed
```

F1-B2 does not implement `latest observation wins`, `any succeeded wins`, or any other RecoveryObservation aggregation rule. A later `reported-failed` observation does not rewrite an explicit verifier `pass`, and a reported success cannot masquerade as the closed-verification result itself.

The correct responsibility boundary remains:

```text
RecoveryObservation set
        ↓
external / independent verifier responsibility
        ↓
explicit typed EvidenceArtifact(pass|fail)
        ↓
existing F1-B2 authority
```

Conflict interpretation, freshness judgment, and selection of observation inputs therefore remain verifier responsibility unless a future explicit provenance contract says otherwise.

## Verdict

```text
RecoveryOutcomeAuthority
PROHIBITED / NOT REQUIRED

new recovery-specific confirmed-Outcome machinery
NOT REQUIRED

B4-P2 production objective-authority machinery
NOT REQUIRED BY CURRENT EVIDENCE
```

The safe bridge is already architectural rather than a new authority primitive:

```text
RecoveryObservation
        ↓ optional verifier input / opaque provenance at runtime
existing external verification responsibility
        ↓
typed EvidenceArtifact
        ↓
BoundVerificationEvidenceValidator
        ↓
existing VerifiedOutcomeAuthority
        ↓
confirmed Outcome
```

The phrase `opaque provenance at runtime` is deliberate. Current runtime code does not attest that an arbitrary RecoveryObservation citation was fresh, conflict-resolved, or bound to the target dispatch. Such claims remain outside the F1-B2 authority graph.

## Future seam, only if separately justified

If runtime-attested recovery provenance becomes a real requirement, the narrowest acceptable production shape is a pure/verifier-input adaptation contract such as:

```text
exact RecoveryObservation refs
+ expected dispatch/action/attempt identity
→ validated verification-input descriptor
→ external verifier
→ ordinary EvidenceArtifact
```

It must not create any of the following:

```text
confirm_recovery_outcome()
RecoveryOutcomeAuthority
direct RecoveryObservation → Outcome
latest-observation-wins policy
retry or provider invocation authority
terminal completion authority
```

No such production seam is implemented by this audit.

## Stage gate after audit

```text
B4-P1
FROZEN at 800157f687639b1d4b1ebe4121f8283fb0dd6b74

B4-P2 objective-authority machinery
NOT REQUIRED BY CURRENT EVIDENCE

optional future recovery-provenance validation seam
DEFERRED until a concrete runtime-attestation requirement exists

B4-P3 RecoveryDisposition
NOT STARTED

B4-P4 RecoveryApplication
NOT STARTED

B4-P5 import/bundle authority
NOT STARTED

CompletionAuthority redesign
DEFERRED

B3-P4
DEFERRED
```
