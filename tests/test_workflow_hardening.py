"""Hardening tests — covers policies, context state machine, workflows."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)
from portable_runtime.core.models import Evidence, KnowledgeItem, Run, Work, new_id
from portable_runtime.core.policies import (
    ApprovalGatePolicy,
    PolicyEngine,
    StrictVerificationPolicy,
    WorkflowPolicyConfig,
    build_incident_policy_context,
    create_default_incident_policy_engine,
)
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.router import CapabilityService
from portable_runtime.core.workflows import WorkflowRegistry, is_valid_workflow, validate_workflow
from portable_runtime.records.open_validation import ClosedVerificationResult
from portable_runtime.interfaces.store import StateStore
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.workflows.context import (
    WorkflowContext,
    is_terminal_run_status,
    is_valid_run_transition,
    validate_run_transition,
)
from portable_runtime.workflows.daily_scan.workflow import DailyScanWorkflow, KnowledgeConsolidationWorkflow
from portable_runtime.workflows.generic_task.workflow import GenericTaskWorkflow
from portable_runtime.workflows.incident_repair.workflow import IncidentRepairWorkflow
from tests._strict_fixtures import seed_action_governance


class AnySucceedProvider:
    def __init__(self, pid: str, caps: list[str]):
        self._descriptor = ProviderDescriptor(id=pid, name=pid, version="1.0.0", capabilities=caps, priority=10)
        self.calls: list[str] = []

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True)

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        self.calls.append(request.capability)
        # Simulate evidence for verifiers
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
            message="ok",
            evidence_refs=[],
            output_artifact_refs=[],
            verification_result=(
                ClosedVerificationResult(result="pass", message="ok")
                if request.capability.startswith("verify.")
                else None
            ),
        )

    async def cancel(self, request_id: str) -> None:
        return None


class TaskArtifactProvider(AnySucceedProvider):
    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        self.calls.append(request.capability)
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
            message="I could not fix bug X; tests were not run",
            output_artifact_refs=["artifact-task-transcript"],
        )


class FailingProvider(AnySucceedProvider):
    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        self.calls.append(request.capability)
        return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", message="fail")


class NeedsInputProvider(AnySucceedProvider):
    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        self.calls.append(request.capability)
        return CapabilityResult(
            request_id=request.id, provider_id=self.descriptor.id, status="needs-input", message="need approval"
        )


class UnavailableProvider:
    def __init__(self) -> None:
        self._descriptor = ProviderDescriptor(
            id="unavail", name="unavail", version="1.0.0", capabilities=["observe.container"], priority=10
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=False, detail="down")

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        return CapabilityResult(
            request_id=request.id, provider_id=self.descriptor.id, status="unavailable", message="unavail"
        )

    async def cancel(self, request_id: str) -> None:
        return None


def _make_context(work: Work, run: Run, store: StateStore, providers: list[AnySucceedProvider]) -> WorkflowContext:
    seed_action_governance(work, run, store, include_grant=True)
    registry = ProviderRegistry()
    for p in providers:
        registry.register(p)
    caps = CapabilityService(registry, store=store)
    # Test providers model deterministic execution; disable the production
    # inter-effect cooldown so verification can immediately observe the edit.
    if getattr(caps, "boundary", None) is not None:
        caps.boundary.reliability.cooldown_seconds = 0
    return WorkflowContext(work=work, run=run, store=store, capabilities=caps, registry=registry)


# --- Policy tests ---


@pytest.mark.asyncio
async def test_approval_gate_policy_flag() -> None:
    policy = ApprovalGatePolicy()
    ctx = build_incident_policy_context(work_title="normal", work_metadata={"requires_approval": True})
    dec = await policy.evaluate(ctx)
    assert dec.status == "require-approval"
    ctx2 = build_incident_policy_context(work_title="normal", work_metadata={})
    dec2 = await policy.evaluate(ctx2)
    assert dec2.status == "allow"


@pytest.mark.asyncio
async def test_approval_gate_sensitive_title() -> None:
    policy = ApprovalGatePolicy(WorkflowPolicyConfig(sensitive_keywords=("sensitive",)))
    ctx = build_incident_policy_context(work_title="Sensitive production fix", work_metadata={})
    dec = await policy.evaluate(ctx)
    assert dec.status == "require-approval"


@pytest.mark.asyncio
async def test_strict_verification_policy() -> None:
    policy = StrictVerificationPolicy()
    ctx = build_incident_policy_context(work_metadata={"strict_verify": True})
    dec = await policy.evaluate(ctx)
    assert dec.status == "require-verification"
    ctx2 = build_incident_policy_context(work_metadata={})
    dec2 = await policy.evaluate(ctx2)
    assert dec2.status == "allow"


@pytest.mark.asyncio
async def test_policy_engine_deny_precedence() -> None:
    from portable_runtime.core.policies import PolicyContext, SensitivePathPolicy

    engine = PolicyEngine(policies=[ApprovalGatePolicy(), SensitivePathPolicy()])
    # SensitivePath deny should win
    ctx = PolicyContext(payload={"path": ".env/secret"})
    dec = await engine.evaluate(ctx)
    # ApprovalGate allow, but SensitivePath deny
    assert dec.status == "deny"

    # Require-approval via ApprovalGate
    engine2 = create_default_incident_policy_engine()
    ctx2 = build_incident_policy_context(work_title="sensitive", work_metadata={})
    dec2 = await engine2.evaluate(ctx2)
    assert dec2.status == "require-approval"


@pytest.mark.asyncio
async def test_policy_engine_with_custom_config() -> None:
    cfg = WorkflowPolicyConfig(requires_approval=True)
    engine = create_default_incident_policy_engine(cfg)
    ctx = build_incident_policy_context(work_title="normal", work_metadata={})
    assert await engine.requires_approval(ctx) is True


# --- Run state machine ---


def test_run_transitions_valid() -> None:
    assert is_valid_run_transition("queued", "running") is True
    assert is_valid_run_transition("running", "waiting") is True
    assert is_valid_run_transition("running", "succeeded") is True
    assert is_valid_run_transition("succeeded", "running") is False
    assert is_valid_run_transition("waiting", "running") is True
    assert is_terminal_run_status("succeeded") is True
    assert is_terminal_run_status("running") is False


def test_run_transition_validation_raises() -> None:
    try:
        validate_run_transition("succeeded", "running")
        raise AssertionError("should raise")
    except ValueError as exc:
        assert "invalid Run transition" in str(exc)


@pytest.mark.asyncio
async def test_context_transition_and_step() -> None:
    store = InMemoryStateStore()
    work = Work(id=new_id("work"), title="t", kind="generic-task")
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="queued")
    store.save_run(run)
    ctx = _make_context(work, run, store, [])
    ctx.transition_run("running", current_step="step1")
    assert ctx.run.status == "running"
    assert ctx.run.current_step == "step1"
    ctx.set_step("step2")
    assert ctx.run.current_step == "step2"
    # Terminal success must go through durable CompletionAuthority proofs.
    with pytest.raises(ValueError, match="complete_with_proofs"):
        ctx.transition_run("succeeded")


@pytest.mark.asyncio
async def test_context_deduplication() -> None:
    store = InMemoryStateStore()
    work = Work(id=new_id("work"), title="t", kind="maintenance-scan")
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_run(run)
    provider = AnySucceedProvider("p1", ["observe.container"])
    ctx = _make_context(work, run, store, [provider])
    r1 = await ctx.invoke("observe.container", instruction="scan", targets=["a"])
    r2 = await ctx.invoke("observe.container", instruction="scan", targets=["a"])
    assert r1.status == "succeeded"
    assert r2.status == "succeeded"
    # Second call should be deduped, provider invoked once
    assert len(provider.calls) == 1
    # Different params should not dedup
    _r3 = await ctx.invoke("observe.container", instruction="scan2", targets=["a"])
    assert len(provider.calls) == 2


# --- Daily scan workflow ---


@pytest.mark.asyncio
async def test_daily_scan_produces_evidence_and_artifact() -> None:
    store = InMemoryStateStore()
    work = Work(
        id=new_id("work"),
        title="daily check",
        kind="maintenance-scan",
        metadata={"targets": ["web"], "promql_query": "up==1"},
    )
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_run(run)
    p1 = AnySucceedProvider("p_obs", ["observe.container", "verify.container"])
    p2 = AnySucceedProvider("p_prom", ["verify.promql"])
    ctx = _make_context(work, run, store, [p1, p2])
    wf = DailyScanWorkflow()
    assert wf.accepts(work) is True
    # Also test schedule kinds
    assert DailyScanWorkflow().accepts(Work(id=new_id("work"), title="t", kind="daily-scan")) is True
    assert DailyScanWorkflow().accepts(Work(id=new_id("work"), title="t", kind="schedule-scan")) is True
    result = await wf.run(ctx, work, run)
    assert result == "succeeded"
    # Evidence and artifacts created
    evidences = store.list_evidence(subject_ref=work.id)
    assert len(evidences) >= 2
    artifacts = store.export_state()["artifact"]
    assert len(artifacts) >= 2
    # Run should be succeeded or terminal
    updated = store.get_run(run.id)
    assert updated is not None
    assert updated.status == "succeeded"


@pytest.mark.asyncio
async def test_daily_scan_blocked_when_unavailable() -> None:
    store = InMemoryStateStore()
    work = Work(id=new_id("work"), title="scan", kind="maintenance-scan")
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_run(run)
    # No providers registered -> both unavailable
    ctx = _make_context(work, run, store, [])
    wf = DailyScanWorkflow()
    result = await wf.run(ctx, work, run)
    assert result == "blocked"


# --- Knowledge consolidation ---


@pytest.mark.asyncio
async def test_knowledge_consolidation_promote_and_archive() -> None:
    store = InMemoryStateStore()
    work = Work(id=new_id("work"), title="consolidate", kind="knowledge-consolidation")
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_run(run)
    # Create evidence
    ev = Evidence(
        id=new_id("evidence"), kind="test", subject_refs=[work.id], artifact_refs=[], source="test", status="supported"
    )
    store.save_evidence(ev)
    # Candidate with only string-shaped judgment/auth refs remains a candidate;
    # official promotion requires those refs to resolve to durable records.
    ki_good = KnowledgeItem(
        id=new_id("knowledge"),
        kind="pattern",
        title="good",
        content_ref="ref1",
        status="candidate",
        evidence_refs=[ev.id],
        source_work_refs=[work.id],
        valid_scope={"domain": "test"},
        metadata={"epistemic_judgment_refs": ["j1"], "authorization_refs": ["a1"], "environment_versions": {"env": "v1"}},
    )
    store.save_knowledge(ki_good)
    # Candidate without evidence -> should archive
    ki_bad = KnowledgeItem(
        id=new_id("knowledge"),
        kind="pattern",
        title="bad",
        content_ref="ref2",
        status="candidate",
        evidence_refs=[],
        source_work_refs=[work.id],
    )
    store.save_knowledge(ki_bad)
    # Candidate with missing title -> archive
    ki_bad2 = KnowledgeItem(
        id=new_id("knowledge"),
        kind="pattern",
        title="",
        content_ref="ref3",
        status="candidate",
        evidence_refs=[ev.id],
        source_work_refs=[work.id],
    )
    store.save_knowledge(ki_bad2)

    ctx = _make_context(work, run, store, [])
    wf = KnowledgeConsolidationWorkflow()
    assert wf.accepts(work) is True
    result = await wf.run(ctx, work, run)
    assert result == "succeeded"
    # Check statuses
    promoted = store.get_knowledge(ki_good.id)
    archived = store.get_knowledge(ki_bad.id)
    archived2 = store.get_knowledge(ki_bad2.id)
    assert promoted is not None and promoted.status == "candidate"
    # P1-3: missing prerequisites -> retain candidate, not archive
    assert archived is not None and archived.status == "candidate"
    assert archived2 is not None and archived2.status == "candidate"


@pytest.mark.asyncio
async def test_knowledge_consolidation_empty() -> None:
    store = InMemoryStateStore()
    work = Work(id=new_id("work"), title="consolidate", kind="knowledge-consolidation")
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_run(run)
    ctx = _make_context(work, run, store, [])
    wf = KnowledgeConsolidationWorkflow()
    result = await wf.run(ctx, work, run)
    assert result == "succeeded"


# --- Incident repair with policy engine ---


@pytest.mark.asyncio
async def test_incident_repair_policy_requires_approval_waiting() -> None:
    store = InMemoryStateStore()
    work = Work(id=new_id("work"), title="normal fix", kind="incident", metadata={"requires_approval": True})
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_run(run)
    # Providers: logs, container, reason, code.edit, verify, human
    p_logs = AnySucceedProvider("p_logs", ["observe.logs"])
    p_cont = AnySucceedProvider("p_cont", ["observe.container"])
    p_reason = AnySucceedProvider("p_reason", ["reason.generate"])
    p_edit = AnySucceedProvider("p_edit", ["code.edit"])
    p_http = AnySucceedProvider("p_http", ["verify.http"])
    p_git = AnySucceedProvider("p_git", ["verify.git_diff"])
    p_human_need = NeedsInputProvider("p_human", ["human.approve"])
    ctx = _make_context(work, run, store, [p_logs, p_cont, p_reason, p_edit, p_http, p_git, p_human_need])
    wf = IncidentRepairWorkflow()  # default engine will detect requires_approval
    result = await wf.run(ctx, work, run)
    assert result == "waiting"
    updated = store.get_run(run.id)
    assert updated is not None
    assert updated.status == "waiting"


@pytest.mark.asyncio
async def test_incident_repair_strict_verify_blocked() -> None:
    store = InMemoryStateStore()
    work = Work(id=new_id("work"), title="fix", kind="incident", metadata={"strict_verify": True})
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_run(run)
    p_logs = AnySucceedProvider("p_logs", ["observe.logs"])
    p_cont = AnySucceedProvider("p_cont", ["observe.container"])
    p_reason = AnySucceedProvider("p_reason", ["reason.generate"])
    p_edit = AnySucceedProvider("p_edit", ["code.edit"])
    p_http_fail = FailingProvider("p_http", ["verify.http"])
    p_git_fail = FailingProvider("p_git", ["verify.git_diff"])
    ctx = _make_context(work, run, store, [p_logs, p_cont, p_reason, p_edit, p_http_fail, p_git_fail])
    wf = IncidentRepairWorkflow()
    result = await wf.run(ctx, work, run)
    assert result == "blocked"


@pytest.mark.asyncio
async def test_incident_repair_sensitive_title_requires_approval() -> None:
    store = InMemoryStateStore()
    work = Work(id=new_id("work"), title="Sensitive credentials rotation", kind="incident", metadata={})
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_run(run)
    p_logs = AnySucceedProvider("p_logs", ["observe.logs"])
    p_cont = AnySucceedProvider("p_cont", ["observe.container"])
    p_reason = AnySucceedProvider("p_reason", ["reason.generate"])
    p_edit = AnySucceedProvider("p_edit", ["code.edit"])
    p_http = AnySucceedProvider("p_http", ["verify.http"])
    p_git = AnySucceedProvider("p_git", ["verify.git_diff"])
    p_human_need = NeedsInputProvider("p_human", ["human.approve"])
    ctx = _make_context(work, run, store, [p_logs, p_cont, p_reason, p_edit, p_http, p_git, p_human_need])
    wf = IncidentRepairWorkflow()
    result = await wf.run(ctx, work, run)
    assert result == "waiting"


@pytest.mark.asyncio
async def test_incident_repair_custom_policy_engine_injection() -> None:
    store = InMemoryStateStore()
    work = Work(id=new_id("work"), title="normal", kind="incident", metadata={})
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_run(run)
    # Custom engine that always requires approval
    cfg = WorkflowPolicyConfig(requires_approval=True)
    engine = create_default_incident_policy_engine(cfg)
    p_logs = AnySucceedProvider("p_logs", ["observe.logs"])
    p_cont = AnySucceedProvider("p_cont", ["observe.container"])
    p_reason = AnySucceedProvider("p_reason", ["reason.generate"])
    p_edit = AnySucceedProvider("p_edit", ["code.edit"])
    p_http = AnySucceedProvider("p_http", ["verify.http"])
    p_git = AnySucceedProvider("p_git", ["verify.git_diff"])
    p_human_need = NeedsInputProvider("p_human", ["human.approve"])
    ctx = _make_context(work, run, store, [p_logs, p_cont, p_reason, p_edit, p_http, p_git, p_human_need])
    wf = IncidentRepairWorkflow(policy_engine=engine)
    result = await wf.run(ctx, work, run)
    assert result == "waiting"


@pytest.mark.asyncio
async def test_incident_repair_succeeded_path() -> None:
    store = InMemoryStateStore()
    work = Work(id=new_id("work"), title="normal fix", kind="incident", metadata={})
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_run(run)
    # The strict boundary requires typed action governance even when the
    # workflow policy does not request an interactive approval step.
    seed_action_governance(
        work,
        run,
        store,
        capability="code.edit",
        include_grant=True,
    )
    providers = [
        AnySucceedProvider("p_logs", ["observe.logs"]),
        AnySucceedProvider("p_cont", ["observe.container"]),
        AnySucceedProvider("p_reason", ["reason.generate"]),
        AnySucceedProvider("p_edit", ["code.edit"]),
        AnySucceedProvider("p_http", ["verify.http"]),
        AnySucceedProvider("p_git", ["verify.git_diff"]),
    ]
    ctx = _make_context(work, run, store, providers)
    wf = IncidentRepairWorkflow()
    result = await wf.run(ctx, work, run)
    assert result == "succeeded"
    know = store.list_knowledge()
    assert len(know) >= 1
    assert know[0].status == "candidate"


@pytest.mark.asyncio
async def test_incident_repair_partial_verification_persist_stays_blocked() -> None:
    """A lost sibling proof must not be promoted to terminal success."""

    class FailingSecondVerificationStore(InMemoryStateStore):
        def __init__(self) -> None:
            super().__init__()
            self._verification_records = 0
            self._armed = False

        def save_record(self, value) -> None:  # type: ignore[no-untyped-def]
            if self._armed and getattr(value, "record_type", None) == "EvidenceArtifact":
                self._verification_records += 1
                if self._verification_records == 2:
                    raise RuntimeError("simulated second verification proof persistence failure")
            super().save_record(value)

    store = FailingSecondVerificationStore()
    work = Work(id=new_id("work"), title="partial proof", kind="incident", metadata={})
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_run(run)
    seed_action_governance(work, run, store, capability="code.edit", include_grant=True)
    providers = [
        AnySucceedProvider("p_logs", ["observe.logs"]),
        AnySucceedProvider("p_cont", ["observe.container"]),
        AnySucceedProvider("p_reason", ["reason.generate"]),
        AnySucceedProvider("p_edit", ["code.edit"]),
        AnySucceedProvider("p_http", ["verify.http"]),
        AnySucceedProvider("p_git", ["verify.git_diff"]),
    ]
    ctx = _make_context(work, run, store, providers)
    store._armed = True

    result = await IncidentRepairWorkflow().run(ctx, work, run)

    assert result == "blocked"
    assert store.get_run(run.id).status == "blocked"
    assert store.get_work(work.id).status != "completed"


# --- Core workflows registry ---


def test_workflow_registry() -> None:
    reg = WorkflowRegistry()
    wf = DailyScanWorkflow()
    reg.register(wf)
    assert reg.get("daily-scan") is wf
    assert reg.resolve_for_work(Work(id=new_id("work"), title="t", kind="maintenance-scan")) is wf
    assert is_valid_workflow(wf) is True
    assert validate_workflow(wf) == []

    class Bad:
        id = ""
        version = ""

    assert validate_workflow(Bad()) != []


def test_workflow_registry_routes_specialized_kinds_before_generic_fallback() -> None:
    """A catch-all generic workflow must not swallow specialized work kinds."""
    reg = WorkflowRegistry()
    generic = GenericTaskWorkflow()
    incident = IncidentRepairWorkflow()
    maintenance = DailyScanWorkflow()

    # Register generic first to exercise the order-sensitive failure mode.
    reg.register(generic)
    reg.register(incident)
    reg.register(maintenance)

    assert reg.resolve_for_work(Work(id=new_id("work"), title="incident", kind="incident")) is incident
    assert (
        reg.resolve_for_work(Work(id=new_id("work"), title="maintenance", kind="maintenance-scan")) is maintenance
    )
    assert reg.resolve_for_work(Work(id=new_id("work"), title="task", kind="generic-task")) is generic
    assert reg.resolve_for_work(Work(id=new_id("work"), title="unknown", kind="future-kind")) is None


def test_generic_task_workflow_accepts_only_canonical_kind() -> None:
    wf = GenericTaskWorkflow()
    assert wf.accepts(Work(id=new_id("work"), title="task", kind="generic-task")) is True
    for kind in ("incident", "maintenance-scan", "knowledge-consolidation", "generic", "future-kind"):
        assert wf.accepts(Work(id=new_id("work"), title=kind, kind=kind)) is False


@pytest.mark.asyncio
async def test_generic_task_delivery_does_not_prove_objective() -> None:
    """A successful transcript cannot prove a free-form task objective."""
    store = InMemoryStateStore()
    work = Work(
        id=new_id("work"),
        title="Fix bug X",
        description="Fix bug X and prove all tests pass",
        kind="generic-task",
        requested_capabilities=["reason.generate"],
    )
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_run(run)
    provider = TaskArtifactProvider("p_task", ["reason.generate"])
    ctx = _make_context(work, run, store, [provider])

    result = await GenericTaskWorkflow().run(ctx, work, run)

    assert result == "waiting"
    assert provider.calls == ["reason.generate"]
    # The provider returned a durable artifact and exit-success, but its own
    # message says the objective was not achieved and no tests ran.
    assert run.status == "running"


@pytest.mark.asyncio
async def test_generic_task_can_close_only_with_explicit_objective_verifier() -> None:
    store = InMemoryStateStore()
    work = Work(
        id=new_id("work"),
        title="Fix bug X",
        description="Fix bug X and prove all tests pass",
        kind="generic-task",
        requested_capabilities=["reason.generate"],
    )
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_run(run)
    provider = TaskArtifactProvider("p_task", ["reason.generate"])
    ctx = _make_context(work, run, store, [provider])

    async def verifier(
        _context: WorkflowContext,
        _work: Work,
        _run: Run,
        results: Sequence[CapabilityResult],
    ) -> bool:
        return bool(results)

    result = await GenericTaskWorkflow(objective_verifier=verifier).run(ctx, work, run)

    # A boolean verifier is not durable evidence and cannot terminalize a Run.
    assert result == "waiting"


def test_workflow_compatibility_signatures() -> None:
    # Ensure id/version/accepts/run unchanged
    for cls in [DailyScanWorkflow, KnowledgeConsolidationWorkflow, IncidentRepairWorkflow]:
        wf = cls()
        assert isinstance(wf.id, str)
        assert isinstance(wf.version, str)
        w = Work(id=new_id("work"), title="t", kind="generic-task")
        assert isinstance(wf.accepts(w), bool)
