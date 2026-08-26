"""F1-B3 P3C: imported Outcome impact authority remains explicitly non-portable."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from portable_runtime.core.models import Action, Event, Run, Step, StepAttempt, Work
from portable_runtime.governance.outcome_impact import OutcomeGovernanceDependency
from portable_runtime.governance.outcome_impact_commit import (
    OUTCOME_DISPOSITION_EVENT,
    OUTCOME_IMPACT_JUDGMENT_EVENT,
    OutcomeImpactCommitRequest,
)
from portable_runtime.governance.outcome_impact_judgment import OutcomeImpact, OutcomeImpactJudgment
from portable_runtime.records.models import EvidenceArtifact, OutcomeRecord
from portable_runtime.records.revalidation import RevalidationDisposition
from portable_runtime.records.verified_outcome import VerifiedOutcomeAuthority
from portable_runtime.stores.bundle import export_bundle, import_bundle
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore

_SCOPE = {"resource": "repo/app", "operation": "effect"}
_GOVERNED_SCOPE = frozenset({"repo/app", "repo/shared"})
_VERSIONS = ("subject:v1",)
_IMPORT_ERROR = "B3 outcome impact authority history import is unsupported"


@contextmanager
def _store(backend: str, tmp_path: Path, suffix: str) -> Iterator[Any]:
    if backend == "memory":
        yield InMemoryStateStore()
        return
    store = SQLiteStateStore(tmp_path / f"b3-p3c-{suffix}.db")
    try:
        yield store
    finally:
        store.close()


def _seed_verified(store: Any, suffix: str) -> tuple[OutcomeRecord, Event]:
    work = Work(id=f"work_b3_p3c_{suffix}", title="B3 P3C", metadata={"work_version": 1})
    run = Run(id=f"run_b3_p3c_{suffix}", work_id=work.id, status="running")
    step = Step(
        id=f"step_b3_p3c_{suffix}",
        run_id=run.id,
        step_key="effect",
        status="succeeded",
        current_attempt=1,
    )
    attempt = StepAttempt(
        id=f"attempt_b3_p3c_{suffix}",
        step_id=step.id,
        provider_id="provider:executor",
        request_ref=f"request_b3_p3c_{suffix}",
        status="succeeded",
    )
    action = Action(
        id=f"action_b3_p3c_{suffix}",
        work_id=work.id,
        run_id=run.id,
        capability="code.edit",
        provider_id=attempt.provider_id,
        request_ref=attempt.request_ref or "",
        status="succeeded",
    )
    proof = EvidenceArtifact(
        id=f"evidence_b3_p3c_{suffix}",
        kind="task-objective-proof",
        source_refs=[action.id],
        lifecycle_status="current",
        metadata={
            "verification_result": {"result": "fail"},
            "proof_class": "objective-verification",
            "action_ref": action.id,
            "request_id": action.request_ref,
            "attempt_ref": attempt.id,
            "work_id": work.id,
            "run_id": run.id,
            "verification_scope": dict(_SCOPE),
            "subject_version_refs": list(_VERSIONS),
            "obligation_refs": ["verify.effect"],
            "verifier_provenance": {
                "provider_id": "provider:verifier",
                "verifier_id": "verifier:objective",
                "method": "closed-verification",
            },
        },
    )
    store.save_work(work)
    store.save_run(run)
    store.save_step(step)
    store.save_attempt(attempt)
    store.save_action(action)
    store.save_record(proof)
    outcome = VerifiedOutcomeAuthority(store).confirm(
        action_ref=action.id,
        evidence_refs=[proof.id],
        expected_work_id=work.id,
        expected_run_id=run.id,
        expected_request_id=action.request_ref,
        expected_attempt_ref=attempt.id,
        verification_scope=dict(_SCOPE),
        subject_version_refs=list(_VERSIONS),
    )
    confirmed = next(event for event in store.list_events(outcome.id) if event.type == "OutcomeConfirmed")
    return outcome, confirmed


@dataclass
class _ImpactPolicy:
    policy_ref: str = "impact-policy:p3c"
    impact: OutcomeImpact = "revalidation-required"

    def judge(self, outcome: OutcomeRecord, applicability: Any) -> tuple[OutcomeImpact, tuple[str, ...]]:
        return self.impact, (self.policy_ref, outcome.id, applicability.scheme_id)


@dataclass
class _DispositionPolicy:
    policy_ref: str = "disposition-policy:p3c"

    def decide(self, judgment: OutcomeImpactJudgment) -> RevalidationDisposition:
        return RevalidationDisposition(
            action="block-next-use",
            policy_ref=self.policy_ref,
            rationale_refs=[self.policy_ref, judgment.outcome_ref],
        )


def _commit_local_b3_history(store: Any, suffix: str) -> tuple[str, str]:
    outcome, confirmed = _seed_verified(store, suffix)
    dependency = OutcomeGovernanceDependency(
        outcome_ref=outcome.id,
        action_ref=outcome.action_ref,
        scheme_id="scheme:b3",
        context="use:deploy",
        scope=_GOVERNED_SCOPE,
        subject_version_refs=_VERSIONS,
        basis_refs=("dependency:b3-p3c",),
    )
    committed = store.commit_outcome_impact_judgment(
        OutcomeImpactCommitRequest(
            event_ref=confirmed.id,
            dependency=dependency,
            context="use:deploy",
            requested_scope=frozenset({"repo/app"}),
            subject_version_refs=_VERSIONS,
        ),
        _ImpactPolicy(),
        _DispositionPolicy(),
    )
    return committed.judgment_event_ref, committed.disposition_event_ref


def _authority_payload(kind: str, realistic: bool) -> dict[str, object]:
    if not realistic:
        return {"binding_digest": "forged"}
    common: dict[str, object] = {
        "schema_version": "outcome-governance-impact-v1",
        "semantic_level": "governance-impact",
        "binding_digest": "a" * 64,
        "trigger_event_ref": "event_outcome_confirmed_imported",
        "outcome_ref": "outcome_imported",
        "action_ref": "action_imported",
        "scheme_id": "scheme:b3",
        "context": "use:deploy",
        "governed_scope": ["repo/app", "repo/shared"],
        "subject_version_refs": ["subject:v1"],
        "applicability_basis_refs": ["dependency:b3-p3c"],
        "rationale_refs": ["basis:b3-p3c"],
    }
    if kind == "judgment":
        return {
            **common,
            "impact": "revalidation-required",
            "impact_policy_ref": "impact-policy:v1",
            "impact_policy_digest": "b" * 64,
        }
    return {
        **common,
        "judgment_event_ref": "imported_b3_judgment",
        "action": "block-next-use",
        "disposition_policy_ref": "disposition-policy:v1",
        "disposition_policy_digest": "c" * 64,
    }


def _imported_authority_events(mode: str, realistic: bool) -> list[dict[str, object]]:
    judgment = Event(
        id="imported_b3_judgment",
        type=OUTCOME_IMPACT_JUDGMENT_EVENT,
        subject_ref="outcome_imported",
        payload=_authority_payload("judgment", realistic),
    )
    disposition = Event(
        id="imported_b3_disposition",
        type=OUTCOME_DISPOSITION_EVENT,
        subject_ref="outcome_imported",
        payload=_authority_payload("disposition", realistic),
    )
    selected = {
        "judgment": (judgment,),
        "disposition": (disposition,),
        "both": (judgment, disposition),
    }[mode]
    return [event.model_dump(mode="json") for event in selected]


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
@pytest.mark.parametrize("mode", ["judgment", "disposition", "both"])
@pytest.mark.parametrize("realistic", [False, True])
def test_b3_p3c_incoming_impact_authority_is_content_independently_rejected_atomically(
    backend: str,
    mode: str,
    realistic: bool,
    tmp_path: Path,
) -> None:
    with _store(backend, tmp_path, f"reject-{backend}-{mode}-{realistic}") as target:
        sentinel_outcome, _sentinel_confirmed = _seed_verified(target, f"sentinel-{backend}-{mode}-{realistic}")
        before = target.export_state()
        imported_work = Work(id=f"imported_work_{backend}_{mode}_{realistic}", title="must not import")
        incoming = {
            "work": [imported_work.model_dump(mode="json")],
            "event": _imported_authority_events(mode, realistic),
        }

        with pytest.raises(ValueError, match=_IMPORT_ERROR):
            target.import_state(incoming)

        after = target.export_state()
        assert after == before
        assert target.get_work(imported_work.id) is None
        assert target.get_record(sentinel_outcome.id) is not None
        assert not any(str(event["id"]).startswith("imported_b3_") for event in after["event"])


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b3_p3c_unrelated_event_import_remains_supported(backend: str, tmp_path: Path) -> None:
    with _store(backend, tmp_path, f"unrelated-{backend}") as target:
        outcome, _confirmed = _seed_verified(target, f"unrelated-sentinel-{backend}")
        existing_work_id = str(outcome.metadata["work_id"])
        unrelated = Event(
            id=f"event_unrelated_import_{backend}",
            type="RuntimeAuditNote",
            subject_ref=existing_work_id,
            payload={"note": "not B3 impact authority"},
        )
        target.import_state({"event": [unrelated.model_dump(mode="json")]})
        imported = target.get_event(unrelated.id)
        assert imported is not None
        assert imported.type == "RuntimeAuditNote"


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b3_p3c_f1_b2_verified_outcome_portability_still_passes_guard(
    backend: str,
    tmp_path: Path,
) -> None:
    source = InMemoryStateStore()
    outcome, confirmed = _seed_verified(source, f"b2-source-{backend}")
    accepted = next(event for event in source.list_events(outcome.id) if event.type == "ObjectiveVerificationAccepted")

    with _store(backend, tmp_path, f"b2-target-{backend}") as target:
        target.import_state(source.export_state())
        imported = target.get_record(outcome.id)
        assert imported is not None
        assert getattr(imported, "lifecycle_status", None) == "confirmed"
        assert target.get_event(accepted.id) is not None
        assert target.get_event(confirmed.id) is not None


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b3_p3c_bundle_with_impact_authority_fails_closed_atomically(
    backend: str,
    tmp_path: Path,
) -> None:
    source = InMemoryStateStore()
    judgment_ref, disposition_ref = _commit_local_b3_history(source, f"bundle-source-{backend}")
    bundle_path = tmp_path / f"b3-impact-authority-{backend}.tar"
    export_bundle(source, None, bundle_path, runtime_id="b3-p3c")

    with _store(backend, tmp_path, f"bundle-target-{backend}") as target:
        sentinel, _confirmed = _seed_verified(target, f"bundle-sentinel-{backend}")
        before = target.export_state()
        with pytest.raises(ValueError, match=_IMPORT_ERROR):
            import_bundle(target, None, bundle_path)
        assert target.export_state() == before
        assert target.get_record(sentinel.id) is not None
        assert target.get_event(judgment_ref) is None
        assert target.get_event(disposition_ref) is None


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
@pytest.mark.parametrize("transport", ["state", "bundle"])
def test_b3_p3c_existing_local_impact_history_does_not_poison_normal_imports(
    backend: str,
    transport: str,
    tmp_path: Path,
) -> None:
    source = InMemoryStateStore()
    incoming_outcome, incoming_confirmed = _seed_verified(source, f"normal-source-{backend}-{transport}")
    bundle_path = tmp_path / f"normal-source-{backend}-{transport}.tar"
    if transport == "bundle":
        export_bundle(source, None, bundle_path, runtime_id="b3-p3c-normal")

    with _store(backend, tmp_path, f"local-b3-{backend}-{transport}") as target:
        judgment_ref, disposition_ref = _commit_local_b3_history(target, f"local-{backend}-{transport}")
        assert target.get_event(judgment_ref) is not None
        assert target.get_event(disposition_ref) is not None

        if transport == "state":
            target.import_state(source.export_state())
        else:
            import_bundle(target, None, bundle_path)

        assert target.get_event(judgment_ref) is not None
        assert target.get_event(disposition_ref) is not None
        assert target.get_record(incoming_outcome.id) is not None
        assert target.get_event(incoming_confirmed.id) is not None
