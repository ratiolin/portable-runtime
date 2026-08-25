from __future__ import annotations

from portable_runtime.core.capabilities import CapabilityRequest
from portable_runtime.core.models import Run, Step, StepAttempt, Work
from portable_runtime.core.qualification import InvocationPermit
from portable_runtime.governance.dispatch import (
    DISPATCH_COMMIT_EVENT,
    GovernanceDispatchCommitter,
)
from portable_runtime.governance.distinction import DistinctionState, UseContext
from portable_runtime.governance.persistence import InMemoryDistinctionGovernancePersistence
from portable_runtime.governance.use_admission import (
    GovernanceUseAdmission,
    GovernanceUseRequirement,
)
from portable_runtime.stores.memory import InMemoryStateStore


class _FailDispatchEventStore(InMemoryStateStore):
    def append_event(self, value: object) -> None:
        if getattr(value, "type", "") == DISPATCH_COMMIT_EVENT:
            raise RuntimeError("injected dispatch event failure")
        super().append_event(value)  # type: ignore[arg-type]


def _resolver(_request: CapabilityRequest) -> GovernanceUseRequirement:
    return GovernanceUseRequirement(
        scheme_id="d",
        use_context=UseContext("ctx", frozenset({"a"})),
    )


def test_e2b_dispatch_event_failure_rolls_back_attempt_binding() -> None:
    store = _FailDispatchEventStore()
    persistence = InMemoryDistinctionGovernancePersistence(store)
    persistence.seed_state(
        "d",
        DistinctionState(
            qualification="qualified",
            activation="active",
            scope=frozenset({"a"}),
            partition=(frozenset({"a"}),),
            version=1,
        ),
    )
    work = Work(id="work-e2b-atomic", title="E2b atomicity")
    run = Run(id="run-e2b-atomic", work_id=work.id, status="running")
    step = Step(
        id="step-e2b-atomic",
        run_id=run.id,
        step_key="dispatch",
        status="running",
        effect_semantics="idempotent",
        side_effect_class="idempotent",
    )
    attempt = StepAttempt(
        id="attempt-e2b-atomic",
        step_id=step.id,
        provider_id="e2b-provider",
        request_ref="req-e2b-atomic",
        idempotency_key="idem-e2b-atomic",
        status="running",
    )
    store.save_work(work)
    store.save_run(run)
    store.save_step(step)
    store.save_attempt(attempt)

    request = CapabilityRequest(
        id="req-e2b-atomic",
        capability="test.read",
        work_id=work.id,
        run_id=run.id,
        idempotency_key="idem-e2b-atomic",
    )
    admission = GovernanceUseAdmission(store).evaluate(request, _resolver)
    assert admission.status == "allowed"
    assert admission.requirement_digest is not None
    assert admission.snapshot_digest is not None
    permit = InvocationPermit.issue(
        request,
        provider_id="e2b-provider",
        qualification_digest="",
        lease_generation=0,
        governance_applicable=True,
        governance_requirement_digest=admission.requirement_digest,
        governance_snapshot_digest=admission.snapshot_digest,
    )

    decision = GovernanceDispatchCommitter(store).commit(
        request,
        permit,
        _resolver,
        attempt_id=attempt.id,
    )

    assert decision.status == "unavailable"
    rebound = store.get_attempt(attempt.id)
    assert rebound is not None
    assert "dispatch_commit_ref" not in rebound.metadata
    assert not [event for event in store.list_events() if event.type == DISPATCH_COMMIT_EVENT]
