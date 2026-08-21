# Portable Runtime RealityBoundary Authoritative Plan

## Current status

The P0 RealityBoundary/SQLite kernel plus the P1 semantic and P2 protocol hardening are closed on 2026-08-21. The freeze-candidate blocker set is now closed: compatibility non-reentrancy, typed SQLite record restoration, Derivation epistemic whitelist, three-layer revalidation risk semantics, canonical write extra-field rejection, and authority-sensitive invocation snapshots. Fresh local evidence is `ruff` clean, `mypy src` clean, `uv run pytest -q` → `250 passed`, and the CI-equivalent strict-conformance selection → `53 passed`. The [main CI run](https://github.com/ratiolin/portable-runtime/actions/runs/32440264051) for commit `63bac6d9f31eb10235879a531d62f788303ebf37` is green, including SonarCloud; the [SonarCloud quality gate](https://sonarcloud.io/project/overview?id=portable-runtime) is `OK` with `80.4%` new-code coverage.

The P0 enforcement kernel is implemented and has executable evidence in:

- `tests/conformance/test_authoritative.py` — E001–E023
- `tests/conformance/test_sqlite_atomicity.py` — S001–S006
- `tests/conformance/test_p1_semantic.py` and `tests/conformance/test_p2_protocol.py`
- `.github/workflows/ci.yml` — independent `strict-conformance` job covering all focused gates

| Claim | Code path | Negative test | Provider invoke asserted? |
|---|---|---|---|
| missing authorization blocks side effect | `RealityBoundary.execute` authorization stage | E001–E003, E008 | yes, count remains 0 |
| governance failures fail closed | policy/procedure/reliability stages | E004–E007, E013–E014 | yes, count remains 0 |
| stale fencing cannot become authoritative | pre/post fencing in `RealityBoundary.execute` | E009–E011, E019 | yes; E019 count is 1 and result is rejected |
| SQLite CAS/Lease are atomic | `SQLiteStateStore` CAS/lease transactions | S001–S006 | n/a |

The strict-conformance command and the repository-wide suite both pass. The
latest local verification is `250 passed` with the two existing collection/
deprecation warnings only. The fresh coverage run reports 76% overall coverage.
Legacy workflow fixtures now carry explicit typed
authorization, resource/version, and procedure evidence; the runtime boundary
itself remains fail-closed when those proofs are absent.

SonarCloud is configured as a hard CI gate (`sonar.qualitygate.wait=true`) and
the workflow waits for both the full suite and strict-conformance before
analysis. The broader P1/P2 semantic hardening is now represented by the
canonical qualification, projection, reopen, revalidation and graph-validation
paths described in `docs/portable-runtime-strict-enforcement-plan.md`.

The authoritative boundary remains the only runtime `provider.invoke` exit;
recovery reconciliation and plugin probes route through the same boundary.
