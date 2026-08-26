# API Problem — `api-problem-v1`

Public contract errors use a stable machine code plus a human-readable message.

```json
{
  "schema": "api-problem-v1",
  "code": "ExperienceUseBlocked",
  "message": "current experience use is blocked",
  "details": {},
  "retryable": false
}
```

`message` is descriptive and not a stable parsing surface. Consumers branch on `code` and contract version.

Recommended v1 Experience codes include:

- `InvalidContractInput`
- `ExperienceUseUnavailable`
- `ExperienceUseBlocked`
- `ExperienceUseStale`
- `HistoricalUseIdentityRebound`
- `HistoricalUseSelfQualificationForbidden`
- `HistoricalUseDigestMismatch`
- `HistoricalUseNotFound`

An error response never grants authorization or execution permission.