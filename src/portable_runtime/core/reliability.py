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
from typing import Any


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
        # sliding window 60s
        self._action_timestamps = [t for t in self._action_timestamps if now - t < 60]
        if len(self._action_timestamps) >= self.max_action_rate:
            return self._block("max_action_rate exceeded")
        if not side_effect:
            self._last_block_reason = None
            return True, "allowed"

        if action_blast_radius < 1:
            return self._block("blast_radius must be positive")
        if action_blast_radius > self.blast_radius:
            return self._block(
                f"blast_radius {action_blast_radius} exceeds limit {self.blast_radius}"
            )
        if self._active_side_effects >= self.max_parallel_side_effects:
            return self._block("max_parallel_side_effects exceeded")
        if self._side_effect_count >= self.side_effect_budget:
            return self._block("side_effect_budget exhausted")

        requested_exposure = exposure if exposure is not None else action_blast_radius
        if requested_exposure < 1:
            return self._block("exposure must be positive")
        if self._exposure_used + requested_exposure > self.exposure_budget:
            return self._block("exposure_budget exhausted")

        if (
            self.cooldown_seconds > 0
            and self._last_side_effect_at is not None
            and now - self._last_side_effect_at < self.cooldown_seconds
        ):
            return self._block("cooldown active")

        enhanced = procedure_profile == "enhanced" or irreversible
        if enhanced:
            if not isinstance(timing, dict):
                return self._block("enhanced side effect requires recovery timing")
            try:
                t_detect = float(timing["t_detect"])
                t_judge = float(timing["t_judge"])
                t_correct = float(timing["t_correct"])
                t_irreversible = float(timing["t_irreversible"])
            except (KeyError, TypeError, ValueError):
                return self._block("recovery timing is incomplete")
            if min(t_detect, t_judge, t_correct, t_irreversible) < 0:
                return self._block("recovery timing must be non-negative")
            if not self.check_rate_compatibility(
                t_detect, t_judge, t_correct, t_irreversible
            ):
                return self._block("recovery loop exceeds irreversible window")

        self._last_block_reason = None
        return True, "allowed"

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

    def check_rate_compatibility(  # noqa: E501
        self, t_detect: float, t_judge: float, t_correct: float, t_irreversible: float
    ) -> bool:
        return (t_detect + t_judge + t_correct) < t_irreversible

