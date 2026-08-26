# Responsibility Record Plane — `responsibility-record-plane-1.0`

Status: stable
Canonical owner: `portable-runtime/contracts`
Control Plane compatibility: `official-1.0.0`

The record plane is an append-oriented semantic interface. A record is evidence that the runtime recorded a typed object; recording alone does not make its contents true, verified, official or authorized.

## Record types

The fixed v1 record types are:

```text
EvidenceArtifact
Observation
Assertion
Goal
Constraint
Experiment
Decision
Action
Outcome
Revision
ChangeObject
Policy
Derivation
```

## Orthogonal dimensions

```text
record_type ⟂ epistemic_status ⟂ lifecycle_status
```

Only proposition/observation records may carry the shared epistemic vocabulary:

```text
unverified
supported
contested
refuted
unknown
revalidation-required
```

Action, Outcome, Decision, Revision, Policy and other non-proposition records use type-specific lifecycle/status semantics instead of borrowing epistemic tokens.

## Non-equivalences

- recorded != true;
- supported != verified;
- verified != official;
- official != authorized;
- Decision record != AuthorizationGrant;
- Action record != provider success;
- Outcome record != causal proof;
- `produces` != `causes`;
- historical record retention != current qualification.

## History and revision

Facts that an action, decision, admission or reliance occurred remain addressable after later revision. Revision creates new history and relations; it does not rewrite an old event into non-occurrence.

## Relation discipline

Relations are typed provenance/semantic links such as `records`, `supports`, `contradicts`, `derived-from`, `tests`, `authorizes`, `produces`, `revises`, `supersedes`, and `requires-revalidation`. The canonical relation surface does not infer a generic `causes` edge.

## Public boundary

The 13 record types are public-read contracts. Generic public clients may not mint authorization or bypass record-specific write gates merely because the structural schema is visible.