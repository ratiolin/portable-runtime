"""Circuit breaker & fault containment — V1.6 + V1.8."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


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

    def can_execute(self, side_effect: bool = False) -> bool:
        now = time.monotonic()
        # sliding window 60s
        self._action_timestamps = [t for t in self._action_timestamps if now - t < 60]
        if len(self._action_timestamps) >= self.max_action_rate:
            return False
        return not (side_effect and self._side_effect_count >= self.side_effect_budget)

    def record_action(self, side_effect: bool = False) -> None:
        self._action_timestamps.append(time.monotonic())
        if side_effect:
            self._side_effect_count += 1

    def check_rate_compatibility(  # noqa: E501
        self, t_detect: float, t_judge: float, t_correct: float, t_irreversible: float
    ) -> bool:
        return (t_detect + t_judge + t_correct) < t_irreversible

