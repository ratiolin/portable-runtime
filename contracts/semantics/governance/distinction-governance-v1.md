# Distinction Governance — `distinction-governance-1.0`

Status: stable
Canonical owner: `portable-runtime/contracts`

This contract defines the runtime product semantics for governed distinctions. It is self-contained and does not depend on an upstream semantic source.

## Runtime projection

For a scheme identifier, the runtime projection consists of:

```text
qualification ∈ {candidate, qualified, disqualified}
activation    ∈ {active, suspended}
scope         = finite set of governed items
partition     = disjoint, exhaustive adopted cells over scope
version       = operational sequencing metadata
```

`version` is not an additional semantic axis.

A state is admissible only if its partition exactly covers scope without overlap; active requires qualified and non-empty scope; disqualified requires suspended.

## Governance runtime

The governance runtime keeps three responsibility classes separate:

```text
ReviewObligation (Q)
GovernanceDecision (Decision)
GovernedApplication / ApplicationReceipt (Application)
```

`Decision != Application`. Reaching a decision endpoint does not establish that the transition was committed.

## State vs transition admissibility

An admissible endpoint does not make every transition to that endpoint admissible. Application requires:

- a recorded compatible decision;
- decision/application identity linkage;
- matching state/scope/partition snapshots;
- current basis freshness;
- no invalidating review;
- operation-specific authority;
- a legal candidate state;
- atomic provenance of pre/post anchors.

Review discharge is independent from state mutation and requires its own application and authority.

## Existing adopted assignment use

The compatibility token `resolve_assignment` and historical API name `resolve_allowed` mean only:

> use an assignment already registered in the current adopted partition.

They do not classify reality, infer ontic truth, or mutate partition membership. `existing_assignment_use_allowed` is the preferred semantic name.

Changing partition membership is a governed state-model change and cannot occur through assignment resolution.

## Authority boundaries

Decision authority, application/mutation authority, review-discharge authority, and action/execution authority are distinct. A policy result, supported assertion, qualified scheme, or successful state application does not mint another authority class.

## Semantic ingress

The kernel validates identity, provenance, freshness, required material and authority supplied by runtime-owned adapters. It does not prove external source truth. Missing, ambiguous or stale required material fails closed for new positive use.

## Compatibility

This local contract preserves the existing `distinction-governance-1.0` serialized tokens, Q/Decision/Application linkage, persisted events and transition behavior. Any future legal-state or legal-transition expansion requires a new contract version and vectors.