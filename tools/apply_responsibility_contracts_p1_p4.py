from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one replacement target, found {count}")
    write(path, content.replace(old, new, 1))


# ---------------------------------------------------------------------------
# P1 — proof-derived product contracts and strict conformance registration.
# ---------------------------------------------------------------------------
write(
    "docs/responsibility-separation-contracts.md",
    '''# Responsibility-separation product contracts

This document records a deliberately narrow product interpretation of the frozen
`responsibility_topology` research artifact.  It does **not** claim that
`portable-runtime` is Lean-verified or that the runtime is a refinement of the
formal model.

The Strict-L6 success path remains:

```text
actual serialized runtime transition
    -> Lean parser
    -> Lean-owned B0 projection
    -> Lean checker
```

`RawWithdrawalTransitionV1` is therefore a frozen runtime-native serialization
surface.  Python must not manufacture B0 coordinates or silently normalize a
known semantic mismatch in order to make the two models look identical.

## Contracts

| ID | Product contract | Evidence class |
|---|---|---|
| RSC-001 | A qualification-state change keeps the subject/provenance addressable and produces an append-only transition audit event. | Strict-L6 consequence + product auditability extension |
| RSC-002 | An Assertion used as positive current-use qualification must be current and supported; stale or revalidation-required assertions cannot issue a new invocation permit. | frozen formal consequence + product admission rule |
| RSC-003 | Dependency impact is not discharge. | formal separation / countermodel |
| RSC-004 | Selecting a repair is not realizing the repair. | formal repair-sufficiency separation |
| RSC-005 | Provider/execution success is not terminal objective completion. | runtime governance invariant |
| RSC-006 | A known semantic mismatch must remain explicit; runtime direct typed impact is not rewritten into formal transitive historical impact. | frozen cross-repository anti-collapse rule |

## Claim boundary

The contracts above are **proof-derived product contracts**, not six Lean
theorems with identical status.  In particular, this repository does not claim:

- full runtime refinement or end-to-end runtime verification;
- complete automatic extraction of a real-world repair graph;
- that declared obligations exhaust reality;
- a universal responsibility ontology;
- that direct runtime dependency impact and formal historical challenge impact
  are semantically identical.

The runtime remains responsible for its own serialization, persistence,
authorization, scope/version binding, and product admission rules.
''',
)

replace_once(
    ".github/workflows/ci.yml",
    "          tests/conformance/test_boundary_architecture.py\n          tests/conformance/test_authoritative.py\n",
    "          tests/conformance/test_boundary_architecture.py\n"
    "          tests/conformance/test_responsibility_separation_contracts.py\n"
    "          tests/conformance/test_qualification_transition.py\n"
    "          tests/conformance/test_terminal_authority.py\n"
    "          tests/conformance/test_authoritative.py\n",
)

write(
    "tests/conformance/test_responsibility_separation_contracts.py",
    '''"""Proof-derived product contracts that must remain fail-closed."""

from __future__ import annotations

import pytest

from portable_runtime.core.models import Run, Work
from portable_runtime.observation.raw_transition import build_raw_withdrawal_transition
from portable_runtime.records.models import Assertion
from portable_runtime.records.relations import RecordRelation
from portable_runtime.records.revalidation import assess_revalidation
from portable_runtime.stores.memory import InMemoryStateStore


def test_rsc001_raw_withdrawal_stays_runtime_native() -> None:
    before = Assertion(
        id="assert_rsc001",
        statement="qualification basis",
        lifecycle_status="current",
        epistemic_status="supported",
        version=1,
    )
    after = before.model_copy(update={"epistemic_status": "revalidation-required", "version": 2})
    artifact = build_raw_withdrawal_transition(before, after, event_ref="event_rsc001")
    payload = artifact.model_dump(mode="json")
    serialized = repr(payload)
    for forbidden in (
        "historicalTrace",
        "qualificationBefore",
        "qualificationAfter",
        "acceptedDischargeEvidenceAfter",
        "B0",
    ):
        assert forbidden not in serialized
    assert payload["before_raw_snapshot"]["epistemic_status"] == "supported"
    assert payload["after_raw_snapshot"]["epistemic_status"] == "revalidation-required"


def test_rsc006_runtime_impact_remains_direct_not_transitive() -> None:
    relations = [
        RecordRelation(
            id="rel_direct",
            relation_type="validated-under",
            subject_ref="assert_direct",
            object_ref="model_changed",
        ),
        RecordRelation(
            id="rel_indirect",
            relation_type="validated-under",
            subject_ref="assert_indirect",
            object_ref="assert_direct",
        ),
    ]
    assessments = assess_revalidation("model_changed", "model", relations)
    assert [item.affected_ref for item in assessments] == ["assert_direct"]


def test_rsc005_provider_success_cannot_write_terminal_state() -> None:
    store = InMemoryStateStore()
    work = Work(id="work_rsc005", title="terminal separation")
    run = Run(id="run_rsc005", work_id=work.id, status="running")
    store.save_work(work)
    store.save_run(run)
    with pytest.raises(ValueError, match="CompletionAuthority"):
        store.save_run(run.model_copy(update={"status": "succeeded"}))
''',
)


# ---------------------------------------------------------------------------
# P2 — qualification status changes become atomic audited transitions.
# ---------------------------------------------------------------------------
write(
    "src/portable_runtime/records/qualification_transition.py",
    '''"""Atomic, append-only audit for in-place Assertion qualification changes.

The event records a runtime-native before/after transition.  It is not a B0
certificate and grants no authority.  The subsequent semantic write still has
to pass the existing Revision/AuthorizationUse mutation authority gate.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from portable_runtime.core.models import Event, new_id
from portable_runtime.records.models import Assertion

QUALIFICATION_TRANSITION_EVENT_TYPE = "qualification.status.changed"
QUALIFICATION_TRANSITION_SCHEMA = "qualification-transition-v1"


def qualification_transition_snapshot(value: Assertion) -> dict[str, Any]:
    return {
        "id": value.id,
        "record_type": value.record_type,
        "lifecycle_status": value.lifecycle_status,
        "epistemic_status": value.epistemic_status,
        "version": value.version,
    }


def _normalize_reason_refs(reason_refs: Iterable[str]) -> list[str]:
    refs = list(dict.fromkeys(str(ref).strip() for ref in reason_refs if str(ref).strip()))
    if not refs:
        raise ValueError("qualification transition requires at least one reason_ref")
    return refs


def build_qualification_transition_event(
    before: Assertion,
    after: Assertion,
    *,
    reason_refs: Iterable[str],
    event_id: str | None = None,
) -> Event:
    if before.id != after.id:
        raise ValueError("qualification transition must preserve Assertion identity")
    if before.record_type != "Assertion" or after.record_type != "Assertion":
        raise ValueError("qualification transition only applies to Assertion records")
    if before.statement != after.statement:
        raise ValueError("qualification transition cannot change the asserted proposition")
    if before.lifecycle_status != after.lifecycle_status:
        raise ValueError("qualification transition cannot bundle a lifecycle transition")
    if before.epistemic_status == after.epistemic_status:
        raise ValueError("qualification transition requires an epistemic_status change")
    if after.version != before.version + 1:
        raise ValueError("qualification transition must advance version by exactly one")
    refs = _normalize_reason_refs(reason_refs)
    return Event(
        id=event_id or new_id("event"),
        type=QUALIFICATION_TRANSITION_EVENT_TYPE,
        subject_ref=after.id,
        payload={
            "schema_version": QUALIFICATION_TRANSITION_SCHEMA,
            "before": qualification_transition_snapshot(before),
            "after": qualification_transition_snapshot(after),
            "reason_refs": refs,
        },
    )


def commit_qualification_transition(
    store: Any,
    after: Assertion,
    *,
    expected_version: int,
    reason_refs: Iterable[str],
    event_id: str | None = None,
) -> Event:
    """Atomically append transition evidence and persist the authorized update."""

    with store.transaction():
        before = store.get_record(after.id)
        if not isinstance(before, Assertion):
            raise ValueError(f"qualification transition subject {after.id!r} is not an Assertion")
        if before.version != expected_version:
            raise ValueError(
                f"qualification transition expected version {expected_version}, current is {before.version}"
            )
        event = build_qualification_transition_event(
            before,
            after,
            reason_refs=reason_refs,
            event_id=event_id,
        )
        store.append_event(event)
        # Existing semantic mutation authorization remains authoritative.  If
        # it rejects the update, the outer store transaction also rolls back
        # the event, so audit and current state cannot diverge.
        store.save_record(after)
    return event


__all__ = [
    "QUALIFICATION_TRANSITION_EVENT_TYPE",
    "QUALIFICATION_TRANSITION_SCHEMA",
    "qualification_transition_snapshot",
    "build_qualification_transition_event",
    "commit_qualification_transition",
]
''',
)

replace_once(
    "src/portable_runtime/records/__init__.py",
    ")\n\n__all__ = [\n",
    ")\nfrom .qualification_transition import (\n"
    "    QUALIFICATION_TRANSITION_EVENT_TYPE,\n"
    "    build_qualification_transition_event,\n"
    "    commit_qualification_transition,\n"
    ")\n\n__all__ = [\n",
)
replace_once(
    "src/portable_runtime/records/__init__.py",
    '    "PolicyRecord",\n]\n',
    '    "PolicyRecord",\n'
    '    "QUALIFICATION_TRANSITION_EVENT_TYPE",\n'
    '    "build_qualification_transition_event",\n'
    '    "commit_qualification_transition",\n'
    ']\n',
)

validation_path = "src/portable_runtime/protocol/validation.py"
validation_anchor = '''def assert_semantic_mutation_authorized(
    record: BaseRecord,
    existing: BaseRecord | None,
    state: dict[str, list[dict[str, object]]],
) -> None:
'''
validation_helpers = '''_QUALIFICATION_TRANSITION_EVENT_TYPE = "qualification.status.changed"
_QUALIFICATION_TRANSITION_SCHEMA = "qualification-transition-v1"


def _qualification_transition_snapshot(record: BaseRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "record_type": record.record_type,
        "lifecycle_status": record.lifecycle_status,
        "epistemic_status": record.epistemic_status,
        "version": record.version,
    }


def _assert_qualification_transition_journaled(
    record: BaseRecord,
    existing: BaseRecord,
    state: dict[str, list[dict[str, object]]],
) -> None:
    """Require an exact append-only audit event for Assertion status changes."""

    if record.record_type != "Assertion" or existing.record_type != "Assertion":
        return
    if record.epistemic_status == existing.epistemic_status:
        return
    if record.version != existing.version + 1:
        raise ValueError(
            f"qualification transition for {record.id!r} must advance version by exactly one"
        )
    expected_before = _qualification_transition_snapshot(existing)
    expected_after = _qualification_transition_snapshot(record)
    matches = 0
    for raw in state.get("event", []):
        if not isinstance(raw, dict):
            continue
        if raw.get("type") != _QUALIFICATION_TRANSITION_EVENT_TYPE or raw.get("subject_ref") != record.id:
            continue
        payload = raw.get("payload")
        if not isinstance(payload, dict) or payload.get("schema_version") != _QUALIFICATION_TRANSITION_SCHEMA:
            continue
        if payload.get("before") != expected_before or payload.get("after") != expected_after:
            continue
        reason_refs = payload.get("reason_refs")
        if not isinstance(reason_refs, list) or not reason_refs or any(
            not isinstance(ref, str) or not ref.strip() for ref in reason_refs
        ):
            continue
        matches += 1
    if matches != 1:
        raise ValueError(
            f"qualification transition for {record.id!r} requires exactly one matching append-only audit event"
        )


'''
replace_once(validation_path, validation_anchor, validation_helpers + validation_anchor)
replace_once(
    validation_path,
    '''    if existing is None or not _semantic_payload_changed(record, existing):
        return
    if record.record_type == "Revision":
''',
    '''    if existing is None or not _semantic_payload_changed(record, existing):
        return
    _assert_qualification_transition_journaled(record, existing, state)
    if record.record_type == "Revision":
''',
)

write(
    "tests/conformance/test_qualification_transition.py",
    '''"""Qualification history/currentness contracts for both state stores."""

from __future__ import annotations

import pytest

from portable_runtime.core.capabilities import CapabilityRequest
from portable_runtime.core.qualification import AssessmentContext, QualificationResolutionError
from portable_runtime.records.authorization import (
    AuthorizationGrant,
    CanonicalAuthorizationRequest,
    create_authorization_use,
)
from portable_runtime.records.models import Assertion
from portable_runtime.records.qualification_transition import commit_qualification_transition
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


def _store(backend: str, tmp_path):
    return InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / "qualification-transition.db")


def _authorized_after(store, before: Assertion, status: str) -> Assertion:
    grant = AuthorizationGrant(
        id=f"authz_{before.id}",
        principal_ref="owner",
        grantee_ref="agent",
        allowed_capabilities=["record.write"],
        resource_scope=[before.id],
        effect_ceiling="write-local",
        subject_version_refs=[f"{before.id}:v{before.version}"],
    )
    store.save_authorization(grant)
    request = CanonicalAuthorizationRequest(
        capability="record.write",
        actor_ref="agent",
        resource_ref=before.id,
        subject_version_refs=[f"{before.id}:v{before.version}"],
        effect_class="write-local",
    )
    use = create_authorization_use(grant, request)
    store.save_authorization_use(use)
    return before.model_copy(
        update={
            "epistemic_status": status,
            "version": before.version + 1,
            "metadata": {**before.metadata, "authorization_use_ref": use.id},
        }
    )


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_epistemic_transition_requires_matching_append_only_event(backend: str, tmp_path) -> None:
    store = _store(backend, tmp_path)
    try:
        before = Assertion(
            id="assert_transition_guard",
            statement="current qualification",
            lifecycle_status="current",
            epistemic_status="supported",
            version=1,
        )
        store.save_record(before)
        after = _authorized_after(store, before, "revalidation-required")
        with pytest.raises(ValueError, match="qualification transition"):
            store.save_record(after)
        event = commit_qualification_transition(
            store,
            after,
            expected_version=1,
            reason_refs=["environment:v2"],
            event_id="event_transition_guard",
        )
        assert event.type == "qualification.status.changed"
        assert store.get_record(before.id).epistemic_status == "revalidation-required"
        events = store.list_events(before.id)
        assert [item.id for item in events] == ["event_transition_guard"]
        assert events[0].payload["before"]["epistemic_status"] == "supported"
        assert events[0].payload["after"]["epistemic_status"] == "revalidation-required"
    finally:
        if backend == "sqlite":
            store.close()


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_transition_event_rolls_back_when_semantic_authority_fails(backend: str, tmp_path) -> None:
    store = _store(backend, tmp_path)
    try:
        before = Assertion(
            id="assert_transition_rollback",
            statement="current qualification",
            lifecycle_status="current",
            epistemic_status="supported",
            version=1,
        )
        store.save_record(before)
        unauthorized = before.model_copy(update={"epistemic_status": "contested", "version": 2})
        with pytest.raises(ValueError, match="authority proof"):
            commit_qualification_transition(
                store,
                unauthorized,
                expected_version=1,
                reason_refs=["observation:new"],
                event_id="event_transition_rollback",
            )
        assert store.get_event("event_transition_rollback") is None
        assert store.get_record(before.id).epistemic_status == "supported"
    finally:
        if backend == "sqlite":
            store.close()


def _qualification_request(assertion: Assertion) -> CapabilityRequest:
    return CapabilityRequest(
        id=f"request_{assertion.id}",
        capability="test.read",
        metadata={
            "qualification_refs": [
                {"id": assertion.id, "kind": "assertion", "version": assertion.version}
            ]
        },
    )


def test_positive_assertion_qualification_must_be_current_and_supported() -> None:
    store = InMemoryStateStore()
    supported = Assertion(
        id="assert_current_supported",
        statement="qualified",
        lifecycle_status="current",
        epistemic_status="supported",
        version=1,
    )
    store.save_record(supported)
    assert AssessmentContext.resolve(store, _qualification_request(supported)).refs

    stale = Assertion(
        id="assert_stale_supported",
        statement="stale",
        lifecycle_status="superseded",
        epistemic_status="supported",
        version=1,
    )
    store.save_record(stale)
    with pytest.raises(QualificationResolutionError, match="stale lifecycle"):
        AssessmentContext.resolve(store, _qualification_request(stale))

    revalidation = Assertion(
        id="assert_revalidation_required",
        statement="needs fresh evidence",
        lifecycle_status="current",
        epistemic_status="revalidation-required",
        version=1,
    )
    store.save_record(revalidation)
    with pytest.raises(QualificationResolutionError, match="currently supported"):
        AssessmentContext.resolve(store, _qualification_request(revalidation))
''',
)


# ---------------------------------------------------------------------------
# P3 — positive Assertion qualification must be current + supported.
# ---------------------------------------------------------------------------
replace_once(
    "src/portable_runtime/core/qualification.py",
    '''    lifecycle = getattr(value, "lifecycle_status", None)
    if isinstance(lifecycle, str) and lifecycle in _STALE_LIFECYCLES:
        raise QualificationResolutionError(
            f"qualification reference {ref.ref_id!r} points to stale lifecycle {lifecycle!r}"
        )
    expires_at = getattr(value, "expires_at", None) or _metadata(value).get("expires_at")
''',
    '''    lifecycle = getattr(value, "lifecycle_status", None)
    if isinstance(lifecycle, str) and lifecycle in _STALE_LIFECYCLES:
        raise QualificationResolutionError(
            f"qualification reference {ref.ref_id!r} points to stale lifecycle {lifecycle!r}"
        )
    if getattr(value, "record_type", None) == "Assertion":
        epistemic = getattr(value, "epistemic_status", None)
        if lifecycle != "current" or epistemic != "supported":
            raise QualificationResolutionError(
                f"qualification Assertion {ref.ref_id!r} must be current and currently supported; "
                f"got lifecycle={lifecycle!r}, epistemic_status={epistemic!r}"
            )
    expires_at = getattr(value, "expires_at", None) or _metadata(value).get("expires_at")
''',
)


# ---------------------------------------------------------------------------
# P4 — revalidation obligations, proof classes, and terminal audit summary.
# ---------------------------------------------------------------------------
completion_path = "src/portable_runtime/workflows/completion.py"
replace_once(
    completion_path,
    '''                "policy_obligations",
                "obligations",
            ):
''',
    '''                "policy_obligations",
                "obligations",
                "revalidation_obligations",
                "required_revalidation_obligations",
            ):
''',
)
replace_once(
    completion_path,
    '''                for field in ("verification_obligations", "required_obligations", "obligations"):
                    add(policy.get(field))
''',
    '''                for field in (
                    "verification_obligations",
                    "required_obligations",
                    "obligations",
                    "revalidation_obligations",
                    "required_revalidation_obligations",
                ):
                    add(policy.get(field))
''',
)
replace_once(
    completion_path,
    '''    @staticmethod
    def validate_proof_invariant(
''',
    '''    @staticmethod
    def _proof_class(record: object, metadata: dict[str, Any]) -> str:
        explicit = metadata.get("proof_class")
        allowed = {
            "execution",
            "observation",
            "closed-verification",
            "objective-verification",
            "revalidation",
        }
        if explicit is not None:
            value = str(explicit).strip().lower()
            if value not in allowed:
                raise ValueError(f"terminal completion proof has unknown proof_class {explicit!r}")
            return value
        kind = str(getattr(record, "kind", "")).strip().lower()
        if kind == "task-objective-proof":
            return "objective-verification"
        return "closed-verification"

    @staticmethod
    def _proof_can_cover(proof_class: str, obligation: str) -> bool:
        if proof_class == "execution":
            return False
        normalized = obligation.strip().lower()
        if normalized.startswith("revalidate."):
            return proof_class == "revalidation"
        if normalized.startswith("verify."):
            return proof_class in {"closed-verification", "objective-verification", "revalidation"}
        if normalized.startswith("observe."):
            return proof_class in {"observation", "closed-verification", "revalidation"}
        return proof_class in {
            "observation",
            "closed-verification",
            "objective-verification",
            "revalidation",
        }

    @staticmethod
    def validate_proof_invariant(
''',
)
replace_once(
    completion_path,
    '''    ) -> None:
        """Validate the complete terminal-proof contract for a Work/Run pair.
''',
    '''    ) -> tuple[list[str], list[str], list[str]]:
        """Validate the complete terminal-proof contract for a Work/Run pair.
''',
)
replace_once(
    completion_path,
    '''            raw_coverage = metadata.get(
                "obligation_refs",
                metadata.get("covered_obligations", metadata.get("verification_obligations", [])),
            )
            if isinstance(raw_coverage, str):
                covered_obligations.add(raw_coverage.strip())
            elif isinstance(raw_coverage, list):
                covered_obligations.update(
                    item.strip() for item in raw_coverage if isinstance(item, str) and item.strip()
                )
        missing = sorted(required_obligations - covered_obligations)
        if missing:
            raise ValueError(
                "terminal completion proofs do not cover required verification obligations: "
                + ", ".join(missing)
            )
''',
    '''            proof_class = CompletionAuthority._proof_class(record, metadata)
            raw_coverage = metadata.get(
                "obligation_refs",
                metadata.get("covered_obligations", metadata.get("verification_obligations", [])),
            )
            candidates: list[str] = []
            if isinstance(raw_coverage, str) and raw_coverage.strip():
                candidates.append(raw_coverage.strip())
            elif isinstance(raw_coverage, list):
                candidates.extend(
                    item.strip() for item in raw_coverage if isinstance(item, str) and item.strip()
                )
            covered_obligations.update(
                obligation
                for obligation in candidates
                if CompletionAuthority._proof_can_cover(proof_class, obligation)
            )
        required = sorted(required_obligations)
        covered = sorted(covered_obligations)
        missing = sorted(required_obligations - covered_obligations)
        if missing:
            raise ValueError(
                "terminal completion proofs do not cover required verification obligations: "
                + ", ".join(missing)
            )
        terminal_pairs = ((work, "completed"), (run, "succeeded"))
        for value, terminal_status in terminal_pairs:
            if getattr(value, "status", None) != terminal_status:
                continue
            metadata_value = value.metadata if isinstance(value.metadata, dict) else {}
            expected_audit = {
                "completion_required_obligations": required,
                "completion_covered_obligations": covered,
                "completion_missing_obligations": [],
            }
            for key, expected in expected_audit.items():
                if metadata_value.get(key) != expected:
                    raise ValueError(f"terminal completion metadata {key!r} does not match proof coverage")
        return required, covered, missing
''',
)
replace_once(
    completion_path,
    '''        if self._already_consumed(set(refs), run):
            raise ValueError("terminal completion proof refs have already been consumed")
        validate_run_transition(run.status, "succeeded")
        metadata = dict(run.metadata) if isinstance(run.metadata, dict) else {}
''',
    '''        if self._already_consumed(set(refs), run):
            raise ValueError("terminal completion proof refs have already been consumed")
        required_obligations, covered_obligations, missing_obligations = self.validate_proof_invariant(
            work,
            run,
            refs,
            self.store.get_record,
        )
        validate_run_transition(run.status, "succeeded")
        metadata = dict(run.metadata) if isinstance(run.metadata, dict) else {}
''',
)
replace_once(
    completion_path,
    '''        metadata["completion_acceptance_criteria"] = list(work.acceptance_criteria)
        from portable_runtime.core.models import utcnow
''',
    '''        metadata["completion_acceptance_criteria"] = list(work.acceptance_criteria)
        metadata["completion_required_obligations"] = required_obligations
        metadata["completion_covered_obligations"] = covered_obligations
        metadata["completion_missing_obligations"] = missing_obligations
        from portable_runtime.core.models import utcnow
''',
)
replace_once(
    completion_path,
    '''        work_metadata["completion_acceptance_criteria"] = list(work.acceptance_criteria)
        updated_work = work.model_copy(
''',
    '''        work_metadata["completion_acceptance_criteria"] = list(work.acceptance_criteria)
        work_metadata["completion_required_obligations"] = list(required_obligations)
        work_metadata["completion_covered_obligations"] = list(covered_obligations)
        work_metadata["completion_missing_obligations"] = list(missing_obligations)
        updated_work = work.model_copy(
''',
)

replace_once(
    "src/portable_runtime/protocol/validation.py",
    '''                for field in (
                    "completion_verification_scope",
                    "completion_work_version",
                    "completion_acceptance_criteria",
                ):
''',
    '''                for field in (
                    "completion_verification_scope",
                    "completion_work_version",
                    "completion_acceptance_criteria",
                    "completion_required_obligations",
                    "completion_covered_obligations",
                    "completion_missing_obligations",
                ):
''',
)

# The low-level store primitive test constructs terminal objects manually; the
# stricter primitive now requires the same coverage audit metadata that normal
# CompletionAuthority writes.
terminal_test = "tests/conformance/test_terminal_authority.py"
replace_once(
    terminal_test,
    '''        terminal_work = terminal_work.model_copy(update={"metadata": {"_completion_proof_refs": [proof.id]}})
        terminal_run = terminal_run.model_copy(update={"metadata": {"_completion_proof_refs": [proof.id]}})
        assert store.commit_terminal(terminal_work, terminal_run, [proof.id]).status == "succeeded"
''',
    '''        required = CompletionAuthority.required_obligation_refs(work)
        audit = {
            "_completion_proof_refs": [proof.id],
            "completion_required_obligations": sorted(required),
            "completion_covered_obligations": sorted(required),
            "completion_missing_obligations": [],
        }
        terminal_work = terminal_work.model_copy(update={"metadata": dict(audit)})
        terminal_run = terminal_run.model_copy(update={"metadata": dict(audit)})
        assert store.commit_terminal(terminal_work, terminal_run, [proof.id]).status == "succeeded"
''',
)
replace_once(
    terminal_test,
    '''            "policy_obligations": [{"ref": "policy-proof"}],
            "obligations": [{"key": "audit-trail"}],
            "verification_policy": {
''',
    '''            "policy_obligations": [{"ref": "policy-proof"}],
            "obligations": [{"key": "audit-trail"}],
            "revalidation_obligations": ["revalidate.subject-v2"],
            "verification_policy": {
''',
)
replace_once(
    terminal_test,
    '''        "audit-trail",
        "objective-proof",
''',
    '''        "audit-trail",
        "revalidate.subject-v2",
        "objective-proof",
''',
)

with (ROOT / terminal_test).open("a", encoding="utf-8") as handle:
    handle.write(
        '''\n\ndef test_revalidation_obligation_requires_revalidation_proof_class() -> None:\n'''
        '''    store = InMemoryStateStore()\n'''
        '''    work = Work(\n'''
        '''        id="work_revalidation_class",\n'''
        '''        title="revalidate",\n'''
        '''        metadata={"revalidation_obligations": ["revalidate.subject-v2"]},\n'''
        '''    )\n'''
        '''    run = Run(id="run_revalidation_class", work_id=work.id, status="running")\n'''
        '''    store.save_work(work)\n'''
        '''    store.save_run(run)\n'''
        '''    ordinary = _proof(work, run).model_copy(\n'''
        '''        update={\n'''
        '''            "id": "proof_revalidation_wrong_class",\n'''
        '''            "metadata": {\n'''
        '''                **_proof(work, run).metadata,\n'''
        '''                "obligation_refs": ["revalidate.subject-v2"],\n'''
        '''            },\n'''
        '''        }\n'''
        '''    )\n'''
        '''    store.save_record(ordinary)\n'''
        '''    with pytest.raises(ValueError, match="obligations"):\n'''
        '''        CompletionAuthority(store).authorize(work=work, run=run, verification_refs=[ordinary.id])\n'''
        '''    revalidation = ordinary.model_copy(\n'''
        '''        update={\n'''
        '''            "id": "proof_revalidation_right_class",\n'''
        '''            "metadata": {**ordinary.metadata, "proof_class": "revalidation"},\n'''
        '''        }\n'''
        '''    )\n'''
        '''    store.save_record(revalidation)\n'''
        '''    result = CompletionAuthority(store).authorize(\n'''
        '''        work=work, run=run, verification_refs=[revalidation.id]\n'''
        '''    )\n'''
        '''    assert result.status == "succeeded"\n'''
        '''    assert result.metadata["completion_required_obligations"] == ["revalidate.subject-v2"]\n'''
        '''    assert result.metadata["completion_covered_obligations"] == ["revalidate.subject-v2"]\n'''
        '''    assert result.metadata["completion_missing_obligations"] == []\n'''
    )

print("responsibility contract rollout patches applied")
