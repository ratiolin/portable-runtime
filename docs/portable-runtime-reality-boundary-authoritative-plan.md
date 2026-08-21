# Portable Runtime RealityBoundary Authoritative Plan

## Current status

The P0 RealityBoundary/SQLite kernel plus the P1 semantic and P2 protocol hardening are closed on 2026-08-21. The semantic freeze-candidate blocker set is closed; the four-commit protocol-convergence sequence now tightens semantic contracts, Boundary internal stages, reliability profiles and authorization compatibility. Fresh local evidence is `ruff` clean, `mypy src` clean, `uv run pytest -q` → `261 passed`, and the CI-equivalent strict-conformance selection → `63 passed`; the previous baseline remains green in [main CI run 32442371727](https://github.com/ratiolin/portable-runtime/actions/runs/32442371727), while this new sequence will receive its own CI/SonarCloud result after push.

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
latest local verification is `261 passed` with the two existing collection/
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
