# Cross-language Public Contract Surface Audit

Status: completed for public-contracts v1
Canonical source: `contracts/`

This audit classifies the current Python objects by whether external consumers may construct, receive or rely on them. It is a boundary audit, not permission to expose internal authority objects.

| Object | Classification | Contract decision |
|---|---|---|
| `ExperienceUseRequirement` | PUBLIC INPUT | v1 schema; caller may construct |
| `ExperienceUseAdmission` | PUBLIC RESULT | v1 schema; read-only semantic evaluation result |
| `HistoricalExperienceUse` | PUBLIC HISTORICAL FACT | v1 schema; deterministic historical binding |
| `HistoricalExperienceUseCommitRequest` | PUBLIC COMMAND | exposed through contract DTO, not direct Python Assertion object |
| `PreparedHistoricalExperienceUseCommit` | INTERNAL | store/commit implementation artifact |
| `GovernanceUseRequirement` | INTERNAL | runtime-owned configuration; caller cannot construct |
| `GovernanceUseAdmissionDecision` | PUBLIC VIEW | expose projection only |
| `InvocationPermit` | INTERNAL AUTHORITY | never public DTO |
| `InvocationPermitView` | PUBLIC VIEW | non-authoritative projection only |
| `DispatchCommitDecision` | INTERNAL CONTROL | do not publish transient control result |
| `InvocationDispatchCommitted` | PUBLIC HISTORICAL VIEW | publish durable event projection |
| 13 semantic Record types | PUBLIC READ | structure visible; writes remain gated |
| `AuthorizationGrant` / `AuthorizationUse` | PUBLIC READ | generic SDK cannot mint authority |
| confirmed `Outcome` | PUBLIC READ | durable confirmed view |
| Recovery observation/disposition/application | PUBLIC VIEW | durable projections; no recovery authority minting |

## Public-input rule

A DTO is public-input only when allowing a caller to construct it cannot manufacture a runtime-owned requirement, qualification, policy disposition, authorization, permit, commit decision or provider invocation.

## Public-result rule

A result/view may expose identity, status, digest, timestamps, provenance and historical facts, but it must not become an authority token merely by being serializable.

## Specific freezes

### InvocationPermit

Only `InvocationPermitView` is public. It may contain digest/provider/qualification/governance/timestamp information. It cannot be sent back as execution authority.

### GovernanceUseRequirement

Not public. The server resolves applicability from runtime-owned configuration and returns `GovernanceUseAdmissionView`. There is no public API where a caller supplies arbitrary governance requirement metadata to make governance apply or not apply.

### Dispatch

Public consumers depend on the durable `InvocationDispatchCommitted` projection rather than transient `DispatchCommitDecision` values.

### Historical experience use

The public commit command carries a judgment payload, requirement and exact expected digests. The server re-evaluates and compare-and-binds; the client cannot bypass this with a locally asserted admission.

## Result

The v1 cross-language surface is safe to graduate through `contracts/` with the Python implementation as reference oracle and all non-Python clients remaining non-authoritative.