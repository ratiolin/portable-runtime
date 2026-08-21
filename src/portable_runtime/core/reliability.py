"""Circuit breaker & fault containment — V1.6 + V1.8.

``ReliabilityControls`` is deliberately a small, deterministic gate.  It
tracks both the durable budget (how much side effect has already been spent)
and the transient budget (how many side effects are currently in flight).
The boundary can therefore ask one object whether a request is admissible
before selecting or invoking a provider.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_probes: int = 1
    _failures: int = 0
    _state: str = "closed"  # closed, open, half-open
    _opened_at: float | None = None
    _successes: int = 0

    def record_success(self) -> None:
        self._failures = 0
        if self._state == "half-open":
            self._successes += 1
            if self._successes >= self.half_open_probes:
                self._state = "closed"
                self._successes = 0
        else:
            self._state = "closed"

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._state = "open"
            self._opened_at = time.monotonic()

    def allow(self) -> bool:
        if self._state == "closed":
            return True
        if self._state == "open":
            if self._opened_at is None:
                return False
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._state = "half-open"
                self._successes = 0
                return True
            return False
        # half-open
        return True

    @property
    def state(self) -> str:
        # auto-transition check
        if (
            self._state == "open"
            and self._opened_at is not None
            and time.monotonic() - self._opened_at >= self.recovery_timeout
        ):
            self._state = "half-open"
        return self._state


@dataclass(frozen=True)
class ReliabilityObservation:
    """Observed runtime facts; this object owns no governance thresholds."""

    action_rate: int
    active_side_effects: int
    side_effect_count: int
    exposure_used: int
    requested_blast_radius: int
    requested_exposure: int
    cooldown_remaining: float
    t_detect: float | None = None
    t_judge: float | None = None
    t_correct: float | None = None
    t_irreversible: float | None = None


@dataclass(frozen=True)
class ReliabilityRiskAssessment:
    """Structural risk interpretation, kept separate from disposition."""

    severity: Literal["none", "low", "high", "critical"]
    reason_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReliabilityDisposition:
    """Policy action for one reliability observation."""

    action: Literal["allow", "require", "defer", "deny"]
    policy_ref: str
    reason: str = "allowed"


@dataclass(frozen=True)
class DefaultLocalReliabilityPolicy:
    """Versioned local policy profile for default governance thresholds.

    The values are policy configuration, not framework invariants.  A caller
    can provide another profile without changing the observation or risk
    structures used by ``ReliabilityControls``.
    """

    profile_id: str = "personal-local-v1"
    version: str = "1"
    max_action_rate: int = 100
    max_parallel_side_effects: int = 10
    blast_radius: int = 5
    cooldown_seconds: float = 5.0
    exposure_budget: int = 1000
    side_effect_budget: int = 100

    @property
    def policy_ref(self) -> str:
        return f"{self.profile_id}@{self.version}"

    def evaluate(
        self,
        observation: ReliabilityObservation,
        *,
        side_effect: bool,
        irreversible: bool,
        procedure_profile: str | None,
        timing: dict[str, Any] | None,
    ) -> tuple[ReliabilityRiskAssessment, ReliabilityDisposition]:
        reasons: list[str] = []
        reason_text = "allowed"
        if observation.action_rate >= self.max_action_rate:
            reasons.append("max_action_rate")
            reason_text = "max_action_rate exceeded"
        elif side_effect and observation.requested_blast_radius < 1:
            reasons.append("blast_radius_positive")
            reason_text = "blast_radius must be positive"
        elif side_effect and observation.requested_blast_radius > self.blast_radius:
            reasons.append("blast_radius_limit")
            reason_text = f"blast_radius {observation.requested_blast_radius} exceeds limit {self.blast_radius}"
        elif side_effect and observation.requested_exposure < 1:
            reasons.append("exposure_positive")
            reason_text = "exposure must be positive"
        elif side_effect and observation.active_side_effects >= self.max_parallel_side_effects:
            reasons.append("parallel_side_effect_limit")
            reason_text = "max_parallel_side_effects exceeded"
        elif side_effect and observation.side_effect_count >= self.side_effect_budget:
            reasons.append("side_effect_budget")
            reason_text = "side_effect_budget exhausted"
        elif side_effect and observation.exposure_used + observation.requested_exposure > self.exposure_budget:
            reasons.append("exposure_budget")
            reason_text = "exposure_budget exhausted"
        elif side_effect and observation.cooldown_remaining > 0:
            reasons.append("cooldown")
            reason_text = "cooldown active"

        enhanced = procedure_profile == "enhanced" or irreversible
        if not reasons and enhanced:
            if not isinstance(timing, dict):
                reasons.append("recovery_timing_required")
                reason_text = "enhanced side effect requires recovery timing"
            else:
                try:
                    values = tuple(float(timing[key]) for key in ("t_detect", "t_judge", "t_correct", "t_irreversible"))
                except (KeyError, TypeError, ValueError):
                    values = ()
                    reasons.append("recovery_timing_incomplete")
                    reason_text = "recovery timing is incomplete"
                if values:
                    t_detect, t_judge, t_correct, t_irreversible = values
                    if min(values) < 0:
                        reasons.append("recovery_timing_non_negative")
                        reason_text = "recovery timing must be non-negative"
                    elif t_detect + t_judge + t_correct >= t_irreversible:
                        reasons.append("recovery_window")
                        reason_text = "recovery loop exceeds irreversible window"

        severity: Literal["none", "low", "high", "critical"] = "none" if not reasons else "high"
        risk = ReliabilityRiskAssessment(severity=severity, reason_refs=tuple(reasons))
        disposition = ReliabilityDisposition(
            action="allow" if not reasons else "deny",
            policy_ref=self.policy_ref,
            reason=reason_text,
        )
        return risk, disposition


@dataclass
class ReliabilityControls:
    """V1.8 reliability controls: rate, blast radius, budgets."""

    max_action_rate: int = 100  # per minute
    max_parallel_side_effects: int = 10
    blast_radius: int = 5
    cooldown_seconds: float = 5.0
    exposure_budget: int = 1000
    side_effect_budget: int = 100
    _action_timestamps: list[float] = field(default_factory=list)
    _side_effect_count: int = 0
    _active_side_effects: int = 0
    _exposure_used: int = 0
    _last_side_effect_at: float | None = None
    _last_block_reason: str | None = field(default=None, init=False, repr=False)
    policy: DefaultLocalReliabilityPolicy | None = None
    _last_risk_assessment: ReliabilityRiskAssessment | None = field(default=None, init=False, repr=False)
    _last_disposition: ReliabilityDisposition | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.policy is None:
            self.policy = DefaultLocalReliabilityPolicy(
                max_action_rate=self.max_action_rate,
                max_parallel_side_effects=self.max_parallel_side_effects,
                blast_radius=self.blast_radius,
                cooldown_seconds=self.cooldown_seconds,
                exposure_budget=self.exposure_budget,
                side_effect_budget=self.side_effect_budget,
            )
        else:
            self.max_action_rate = self.policy.max_action_rate
            self.max_parallel_side_effects = self.policy.max_parallel_side_effects
            self.blast_radius = self.policy.blast_radius
            self.cooldown_seconds = self.policy.cooldown_seconds
            self.exposure_budget = self.policy.exposure_budget
            self.side_effect_budget = self.policy.side_effect_budget

    def assess(
        self,
        side_effect: bool = False,
        *,
        action_blast_radius: int = 1,
        exposure: int | None = None,
        irreversible: bool = False,
        procedure_profile: str | None = None,
        timing: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """Return an admissibility decision and a stable reason.

        ``action_blast_radius`` and ``exposure`` are request-owned values;
        the configured fields are upper bounds.  Enhanced/irreversible work
        must provide the three recovery timing values and prove that the
        correction loop completes before the irreversible window closes.
        """

        now = time.monotonic()
        self._action_timestamps = [t for t in self._action_timestamps if now - t < 60]
        requested_exposure = exposure if exposure is not None else action_blast_radius
        cooldown_remaining = 0.0
        if self._last_side_effect_at is not None:
            cooldown_remaining = max(0.0, self.cooldown_seconds - (now - self._last_side_effect_at))
        timing_values: dict[str, float] = {}
        if isinstance(timing, dict):
            for key in ("t_detect", "t_judge", "t_correct", "t_irreversible"):
                value = timing.get(key)
                if isinstance(value, (int, float)):
                    timing_values[key] = float(value)
        observation = ReliabilityObservation(
            action_rate=len(self._action_timestamps),
            active_side_effects=self._active_side_effects,
            side_effect_count=self._side_effect_count,
            exposure_used=self._exposure_used,
            requested_blast_radius=action_blast_radius,
            requested_exposure=requested_exposure,
            cooldown_remaining=cooldown_remaining,
            t_detect=timing_values.get("t_detect"),
            t_judge=timing_values.get("t_judge"),
            t_correct=timing_values.get("t_correct"),
            t_irreversible=timing_values.get("t_irreversible"),
        )
        if self.policy is None:  # defensive guard for non-standard dataclass construction
            raise RuntimeError("reliability policy profile is unavailable")
        risk, disposition = self.policy.evaluate(
            observation,
            side_effect=side_effect,
            irreversible=irreversible,
            procedure_profile=procedure_profile,
            timing=timing,
        )
        self._last_risk_assessment = risk
        self._last_disposition = disposition
        if disposition.action == "allow":
            self._last_block_reason = None
            return True, "allowed"
        return self._block(disposition.reason)

    def _block(self, reason: str) -> tuple[bool, str]:
        self._last_block_reason = reason
        return False, reason

    def can_execute(
        self,
        side_effect: bool = False,
        *,
        action_blast_radius: int = 1,
        exposure: int | None = None,
        irreversible: bool = False,
        procedure_profile: str | None = None,
        timing: dict[str, Any] | None = None,
    ) -> bool:
        allowed, _ = self.assess(
            side_effect,
            action_blast_radius=action_blast_radius,
            exposure=exposure,
            irreversible=irreversible,
            procedure_profile=procedure_profile,
            timing=timing,
        )
        return allowed

    def record_action(
        self,
        side_effect: bool = False,
        *,
        action_blast_radius: int = 1,
        exposure: int | None = None,
    ) -> None:
        self._action_timestamps.append(time.monotonic())
        if side_effect:
            self._side_effect_count += 1
            self._active_side_effects += 1
            self._exposure_used += exposure if exposure is not None else action_blast_radius
            self._last_side_effect_at = time.monotonic()

    def complete_action(self, side_effect: bool = False) -> None:
        """Release transient parallel capacity after provider completion."""

        if side_effect and self._active_side_effects > 0:
            self._active_side_effects -= 1

    @property
    def active_side_effects(self) -> int:
        return self._active_side_effects

    @property
    def exposure_used(self) -> int:
        return self._exposure_used

    @property
    def last_block_reason(self) -> str | None:
        return self._last_block_reason

    @property
    def last_risk_assessment(self) -> ReliabilityRiskAssessment | None:
        return self._last_risk_assessment

    @property
    def last_disposition(self) -> ReliabilityDisposition | None:
        return self._last_disposition

    def check_rate_compatibility(  # noqa: E501
        self, t_detect: float, t_judge: float, t_correct: float, t_irreversible: float
    ) -> bool:
        return (t_detect + t_judge + t_correct) < t_irreversible

