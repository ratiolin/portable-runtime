"""Private stage seam for :class:`RealityBoundary`.

The public interface remains ``RealityBoundary.execute``.  These small value
objects keep stage inputs and provider-facing execution facts explicit without
granting any stage a provider capability.  In particular, no stage in this
module may call a provider; the only reality exit remains the invocation block
in ``core/boundary.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from portable_runtime.core.capabilities import CapabilityRequest, CapabilityResult
from portable_runtime.core.models import Action, Step, StepAttempt, new_id, utcnow

EffectSemantics = Literal["pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"]
Reversibility = Literal["reversible", "compensatable", "irreversible", "unknown"]


@dataclass(frozen=True)
class ReliabilityStageInput:
    """Normalized governance input passed from Boundary to reliability."""

    side_effect: bool
    action_blast_radius: int
    exposure: int | None
    irreversible: bool
    procedure_profile: str
    timing: dict[str, Any] | None

    def as_kwargs(self) -> dict[str, Any]:
        return {
            "side_effect": self.side_effect,
            "action_blast_radius": self.action_blast_radius,
            "exposure": self.exposure,
            "irreversible": self.irreversible,
            "procedure_profile": self.procedure_profile,
            "timing": self.timing,
        }


@dataclass(frozen=True)
class InvocationStagePlan:
    """Provider facts consumed by Boundary's sole invocation stage."""

    provider_id: str
    side_effect_class: Literal["pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"]
    effect_semantics: Literal["pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"]
    reversibility: Literal["reversible", "compensatable", "irreversible", "unknown"]

    @classmethod
    def from_descriptor(cls, descriptor: Any) -> InvocationStagePlan:
        side_effect_class = str(getattr(descriptor, "side_effect_class", "pure"))
        allowed = {"pure", "idempotent", "deduplicatable", "reconcilable", "irreversible-opaque"}
        if side_effect_class not in allowed:
            side_effect_class = "irreversible-opaque"
        effect_semantics = str(getattr(descriptor, "effect_semantics", side_effect_class))
        if effect_semantics not in allowed:
            effect_semantics = side_effect_class
        reversibility = str(getattr(descriptor, "reversibility", "unknown"))
        if reversibility not in {"reversible", "compensatable", "irreversible", "unknown"}:
            reversibility = "unknown"
        return cls(
            provider_id=str(getattr(descriptor, "id", "")),
            side_effect_class=side_effect_class,  # type: ignore[arg-type]
            effect_semantics=effect_semantics,  # type: ignore[arg-type]
            reversibility=reversibility,  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class BoundaryStagePlan:
    """The internal stage order; callers only see ``RealityBoundary.execute``."""

    names: tuple[str, ...] = (
        "qualification",
        "governance-use",
        "policy",
        "authorization",
        "procedure",
        "reliability",
        "routing",
        "precommit",
        "invocation",
        "postcondition",
        "projection",
    )
    provider_invocation_owner: str = "RealityBoundary"


@dataclass(frozen=True)
class ReliabilityStageDecision:
    """Result of the private reliability stage implementation."""

    allowed: bool
    reason: str | None = None
    error: Exception | None = None


def evaluate_reliability_stage(
    reliability: Any,
    stage_input: ReliabilityStageInput,
    call_supported: Callable[..., Any],
) -> ReliabilityStageDecision:
    """Evaluate reliability without exposing a provider capability."""

    try:
        if hasattr(reliability, "assess"):
            allowed, reason = call_supported(reliability.assess, **stage_input.as_kwargs())
        else:
            allowed = call_supported(reliability.can_execute, **stage_input.as_kwargs())
            reason = getattr(reliability, "last_block_reason", None) or "reliability budget exhausted"
        return ReliabilityStageDecision(bool(allowed), str(reason) if reason is not None else None)
    except Exception as exc:  # pragma: no cover - caller maps the typed failure
        return ReliabilityStageDecision(False, error=exc)


@dataclass(frozen=True)
class ProviderSelectionDecision:
    """Provider health/routing result; invocation remains owned by Boundary."""

    healthy: tuple[Any, ...]
    selected: Any | None = None
    error: Exception | None = None
    error_phase: Literal["eligibility", "routing"] | None = None


async def select_provider_stage(
    registry: Any,
    routing: Any,
    request: Any,
    descriptors: Sequence[Any],
    circuit_for: Callable[[str], Any],
) -> ProviderSelectionDecision:
    """Run health, circuit and constraint selection before the reality exit."""

    healthy: list[Any] = []
    for descriptor in descriptors:
        try:
            health = await registry.health(descriptor.id)
            if not health.available:
                continue
            if not circuit_for(descriptor.id).allow():
                continue
            healthy.append(descriptor)
        except Exception as exc:  # pragma: no cover - caller maps the typed failure
            return ProviderSelectionDecision(tuple(healthy), error=exc, error_phase="eligibility")
    try:
        selected = await routing.select(request, healthy) if healthy else None
    except Exception as exc:  # pragma: no cover - caller maps the typed failure
        return ProviderSelectionDecision(tuple(healthy), error=exc, error_phase="routing")
    return ProviderSelectionDecision(tuple(healthy), selected=selected)


@dataclass(frozen=True)
class ExecutionRecordIds:
    """Identifiers created by the persistence-only precommit stage."""

    step_id: str | None = None
    attempt_id: str | None = None
    action_id: str | None = None


@dataclass(frozen=True)
class PrecommitDecision:
    records: ExecutionRecordIds = ExecutionRecordIds()
    error: Exception | None = None


def precommit_execution_records(
    store: Any,
    request: CapabilityRequest,
    *,
    provider_id: str,
    permit_digest: str,
    lease_generation: int,
    side_effect: bool,
    side_effect_class: str,
    effect_semantics: str,
    reversibility: str,
) -> PrecommitDecision:
    """Persist execution records without owning provider invocation.

    Action-critical requests fail closed when durable precommit is unavailable;
    pure requests retain their historical best-effort observation records.
    """

    if side_effect:
        if store is None or not request.work_id or not request.run_id:
            return PrecommitDecision(error=RuntimeError("side-effect invocation requires durable work/run precommit"))
        try:
            if not all(hasattr(store, method) for method in ("save_step", "save_attempt", "save_action")):
                raise RuntimeError("store lacks precommit methods")
            existing_steps = store.list_steps(request.run_id) if hasattr(store, "list_steps") else []
            step_key = request.step_key or f"{request.capability}:{request.idempotency_key or request.id}"
            step = next((candidate for candidate in existing_steps if candidate.step_key == step_key), None)
            if step is None:
                step = Step(
                    id=new_id("step"),
                    run_id=request.run_id,
                    step_key=step_key,
                    kind=request.capability.split(".")[0] if "." in request.capability else "generic",
                    status="running",
                    effect_semantics=cast(EffectSemantics, effect_semantics),
                    side_effect_class=cast(EffectSemantics, side_effect_class),
                    reversibility=cast(Reversibility, reversibility),
                    input_digest=permit_digest,
                    lease_generation=lease_generation,
                )
            else:
                step = step.model_copy(
                    update={
                        "status": "running",
                        "updated_at": utcnow(),
                        "input_digest": permit_digest,
                        "effect_semantics": effect_semantics,
                        "side_effect_class": side_effect_class,
                        "lease_generation": lease_generation,
                        "version": (step.version or 0) + 1,
                    }
                )
            attempts = store.list_attempts(step.id) if hasattr(store, "list_attempts") else []
            attempt_no = max((a.attempt_no for a in attempts), default=0) + 1
            attempt = StepAttempt(
                id=new_id("attempt"),
                step_id=step.id,
                attempt_no=attempt_no,
                provider_id=provider_id,
                request_ref=request.id,
                idempotency_key=request.idempotency_key or request.id,
                status="running",
                lease_generation=lease_generation,
            )
            action = Action(
                id=new_id("action"),
                work_id=request.work_id,
                run_id=request.run_id,
                capability=request.capability,
                provider_id=provider_id,
                request_ref=request.id,
                status="running",
            )
            if hasattr(store, "transaction"):
                with store.transaction():
                    store.save_step(step)
                    step.current_attempt = attempt_no
                    store.save_step(step)
                    store.save_attempt(attempt)
                    store.save_action(action)
            else:
                store.save_step(step)
                step.current_attempt = attempt_no
                store.save_step(step)
                store.save_attempt(attempt)
                store.save_action(action)
            return PrecommitDecision(ExecutionRecordIds(step.id, attempt.id, action.id))
        except Exception as exc:
            return PrecommitDecision(error=exc)

    if store is None or not request.work_id or not request.run_id or not hasattr(store, "save_step"):
        return PrecommitDecision()
    try:
        existing_steps = store.list_steps(request.run_id) if hasattr(store, "list_steps") else []
        step_key = request.step_key or f"{request.capability}:{request.idempotency_key or request.id}"
        step = next((candidate for candidate in existing_steps if candidate.step_key == step_key), None)
        if step is None:
            step = Step(
                id=new_id("step"),
                run_id=request.run_id,
                step_key=step_key,
                kind=request.capability.split(".")[0] if "." in request.capability else "generic",
                status="running",
                effect_semantics=cast(EffectSemantics, effect_semantics),
                side_effect_class=cast(EffectSemantics, side_effect_class),
                reversibility=cast(Reversibility, reversibility),
                input_digest=permit_digest,
                lease_generation=lease_generation,
            )
        else:
            step = step.model_copy(update={"status": "running", "updated_at": utcnow(), "input_digest": permit_digest})
        store.save_step(step)
        attempt_id: str | None = None
        if hasattr(store, "save_attempt"):
            attempt = StepAttempt(
                id=new_id("attempt"),
                step_id=step.id,
                attempt_no=1,
                provider_id=provider_id,
                request_ref=request.id,
                idempotency_key=request.idempotency_key or request.id,
                status="running",
                lease_generation=lease_generation,
            )
            attempt_id = attempt.id
            store.save_attempt(attempt)
        return PrecommitDecision(ExecutionRecordIds(step.id, attempt_id, None))
    except Exception:
        return PrecommitDecision()


@dataclass(frozen=True)
class PreinvokeAbortDecision:
    aborted: bool = False
    error: Exception | None = None


def abort_preinvocation_records(
    store: Any,
    request: CapabilityRequest,
    *,
    provider_id: str,
    records: ExecutionRecordIds,
    code: str,
    reason: str,
) -> PreinvokeAbortDecision:
    """Terminalize precommitted execution records without creating an Outcome."""

    if store is None or records.step_id is None:
        return PreinvokeAbortDecision()
    error_payload = {"code": code, "reason": reason, "phase": "before-reality-exit"}
    try:
        step = store.get_step(records.step_id) if hasattr(store, "get_step") else None
        attempt = (
            store.get_attempt(records.attempt_id)
            if records.attempt_id and hasattr(store, "get_attempt")
            else None
        )
        if step is None or (records.attempt_id is not None and attempt is None):
            raise RuntimeError("pre-invocation abort is missing precommitted execution records")
        step_update = step.model_copy(update={"status": "cancelled", "updated_at": utcnow()})
        attempt_update = (
            attempt.model_copy(
                update={
                    "status": "cancelled",
                    "ended_at": utcnow(),
                    "error": error_payload,
                }
            )
            if attempt is not None
            else None
        )
        action_update = (
            Action(
                id=records.action_id,
                work_id=request.work_id or "",
                run_id=request.run_id or "",
                capability=request.capability,
                provider_id=provider_id,
                request_ref=request.id,
                status="cancelled",
                metadata={"preinvocation_abort": error_payload},
            )
            if records.action_id is not None
            else None
        )

        def commit() -> None:
            store.save_step(step_update)
            if attempt_update is not None:
                store.save_attempt(attempt_update)
            if action_update is not None:
                store.save_action(action_update)

        if hasattr(store, "transaction"):
            with store.transaction():
                commit()
        else:
            commit()
        return PreinvokeAbortDecision(aborted=True)
    except Exception as exc:
        return PreinvokeAbortDecision(error=exc)


@dataclass(frozen=True)
class ProjectionDecision:
    projected_status: str | None = None
    outcome_id: str | None = None
    error: Exception | None = None


def commit_execution_projection(
    store: Any,
    request: CapabilityRequest,
    result: CapabilityResult,
    *,
    provider_id: str,
    records: ExecutionRecordIds,
) -> ProjectionDecision:
    """Persist execution facts only; objective Outcome authority belongs to verification."""

    if store is None or records.step_id is None:
        return ProjectionDecision()
    try:
        step = store.get_step(records.step_id) if hasattr(store, "get_step") else None
        attempt = (
            store.get_attempt(records.attempt_id)
            if records.attempt_id and hasattr(store, "get_attempt")
            else None
        )
        projected_status = (
            result.status
            if result.status in ("succeeded", "failed", "cancelled", "unknown")
            else "failed"
        )
        if step is None or attempt is None:
            raise RuntimeError("execution projection missing precommitted records")
        step_update = step.model_copy(update={"status": projected_status, "updated_at": utcnow()})
        attempt_update = attempt.model_copy(
            update={
                "status": projected_status,
                "ended_at": utcnow(),
                "result_ref": result.request_id,
                "error": result.error,
            }
        )
        action = Action(
            id=records.action_id or new_id("action"),
            work_id=request.work_id or "",
            run_id=request.run_id or "",
            capability=request.capability,
            provider_id=provider_id,
            request_ref=request.id,
            status=projected_status,
        )
        if hasattr(store, "transaction"):
            with store.transaction():
                store.save_step(step_update)
                store.save_attempt(attempt_update)
                store.save_action(action)
        else:
            store.save_step(step_update)
            store.save_attempt(attempt_update)
            store.save_action(action)
        return ProjectionDecision(projected_status, None)
    except Exception as exc:
        return ProjectionDecision(error=exc)
