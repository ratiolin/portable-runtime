# Portable Runtime RealityBoundary Authoritative Plan

## Current status

The P0 enforcement kernel is implemented and has executable evidence in:

- `tests/conformance/test_authoritative.py` — E001–E020 (21 cases)
- `tests/conformance/test_sqlite_atomicity.py` — S001–S006 (6 cases)
- `.github/workflows/ci.yml` — independent `strict-conformance` job

| Claim | Code path | Negative test | Provider invoke asserted? |
|---|---|---|---|
| missing authorization blocks side effect | `RealityBoundary.execute` authorization stage | E001–E003, E008 | yes, count remains 0 |
| governance failures fail closed | policy/procedure/reliability stages | E004–E007, E013–E014 | yes, count remains 0 |
| stale fencing cannot become authoritative | pre/post fencing in `RealityBoundary.execute` | E009–E011, E019 | yes; E019 count is 1 and result is rejected |
| SQLite CAS/Lease are atomic | `SQLiteStateStore` CAS/lease transactions | S001–S006 | n/a |

The strict-conformance command and the repository-wide suite both pass. The
latest local verification is `223 passed` with the two existing collection/
deprecation warnings only. Legacy workflow fixtures now carry explicit typed
authorization, resource/version, and procedure evidence; the runtime boundary
itself remains fail-closed when those proofs are absent.

The fresh coverage run produced `coverage.xml` at 76% overall coverage. Sonar
Cloud is configured as a hard CI gate (`sonar.qualitygate.wait=true`) and the
workflow waits for both the full suite and strict-conformance before analysis.

The authoritative boundary remains the only runtime `provider.invoke` exit;
recovery reconciliation and plugin probes route through the same boundary.
