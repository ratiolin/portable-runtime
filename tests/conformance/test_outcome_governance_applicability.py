"""F1-B3 P1b: applicability is explicit, bound, and non-authorizing."""

from __future__ import annotations

from portable_runtime.governance.outcome_impact import (
    OutcomeGovernanceDependency,
    resolve_outcome_applicability,
)
from portable_runtime.records.models import OutcomeRecord

_SCOPE = frozenset({"repo/app", "repo/shared"})
_VERSIONS = ("subject:v1",)


def _outcome() -> OutcomeRecord:
    return OutcomeRecord(
        id="outcome_b3_applicability",
        action_ref="action_b3_applicability",
        evidence_refs=["evidence:b3"],
        lifecycle_status="confirmed",
        metadata={
            "objective_result": "fail",
            "work_id": "work:b3",
            "run_id": "run:b3",
            "request_id": "request:b3",
            "attempt_ref": "attempt:b3",
            "verification_scope": {"resource": "repo/app", "operation": "effect"},
            "subject_version_refs": list(_VERSIONS),
            "verification_binding_digest": "digest:b3",
        },
    )


def _dependency(**overrides: object) -> OutcomeGovernanceDependency:
    values: dict[str, object] = {
        "outcome_ref": "outcome_b3_applicability",
        "action_ref": "action_b3_applicability",
        "scheme_id": "scheme:b3",
        "context": "use:deploy",
        "scope": _SCOPE,
        "subject_version_refs": _VERSIONS,
        "basis_refs": ("dependency:b3",),
    }
    values.update(overrides)
    return OutcomeGovernanceDependency(**values)  # type: ignore[arg-type]


def test_b3_p1b_no_explicit_dependency_is_not_declared_not_no_impact() -> None:
    result = resolve_outcome_applicability(
        outcome=_outcome(),
        dependency=None,
        context="use:deploy",
        requested_scope=frozenset({"repo/app"}),
        subject_version_refs=_VERSIONS,
    )
    assert result.status == "not-declared"
    assert not result.applicable
    assert result.reason == "explicit-dependency-absent"


def test_b3_p1b_exact_dependency_binding_is_applicable() -> None:
    result = resolve_outcome_applicability(
        outcome=_outcome(),
        dependency=_dependency(),
        context="use:deploy",
        requested_scope=frozenset({"repo/app"}),
        subject_version_refs=_VERSIONS,
    )
    assert result.status == "applicable"
    assert result.applicable
    assert result.scheme_id == "scheme:b3"
    assert result.basis_refs == ("dependency:b3",)


def test_b3_p1b_context_scope_or_version_mismatch_fails_closed() -> None:
    cases = (
        {"context": "use:other", "requested_scope": frozenset({"repo/app"}), "versions": _VERSIONS},
        {"context": "use:deploy", "requested_scope": frozenset({"repo/other"}), "versions": _VERSIONS},
        {"context": "use:deploy", "requested_scope": frozenset({"repo/app"}), "versions": ("subject:v2",)},
    )
    for case in cases:
        result = resolve_outcome_applicability(
            outcome=_outcome(),
            dependency=_dependency(),
            context=case["context"],  # type: ignore[arg-type]
            requested_scope=case["requested_scope"],  # type: ignore[arg-type]
            subject_version_refs=case["versions"],  # type: ignore[arg-type]
        )
        assert result.status == "mismatch"
        assert not result.applicable


def test_b3_p1b_wrong_outcome_or_action_binding_fails_closed() -> None:
    for dependency in (
        _dependency(outcome_ref="outcome:other"),
        _dependency(action_ref="action:other"),
    ):
        result = resolve_outcome_applicability(
            outcome=_outcome(),
            dependency=dependency,
            context="use:deploy",
            requested_scope=frozenset({"repo/app"}),
            subject_version_refs=_VERSIONS,
        )
        assert result.status == "mismatch"


def test_b3_p1b_incomplete_declared_binding_is_unavailable() -> None:
    result = resolve_outcome_applicability(
        outcome=_outcome(),
        dependency=_dependency(basis_refs=()),
        context="use:deploy",
        requested_scope=frozenset({"repo/app"}),
        subject_version_refs=_VERSIONS,
    )
    assert result.status == "unavailable"
    assert not result.applicable
    assert result.reason == "dependency-or-outcome-binding-incomplete"
