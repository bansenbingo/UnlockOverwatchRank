"""A conservative finite-state machine driven by visual observations.

The machine has no direct screen, keyboard, mouse, process, or network access.
Its only job is to turn high-confidence classified frames into safe, auditable
state changes. Platform integrations can subscribe to those transitions later.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .models import MatchResult, Observation, ScreenState, SessionSnapshot, Transition


@dataclass(frozen=True)
class StateMachineConfig:
    """Safety limits for state recognition and automated session progression."""

    confidence_threshold: float = 0.90
    required_consecutive_frames: int = 3
    target_wins: int = 50
    max_consecutive_failures: int = 3
    state_timeouts: dict[ScreenState, timedelta] | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0.0 and 1.0")
        if self.required_consecutive_frames < 1:
            raise ValueError("required_consecutive_frames must be at least 1")
        if self.target_wins < 1:
            raise ValueError("target_wins must be at least 1")
        if self.max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be at least 1")


DEFAULT_TIMEOUTS: dict[ScreenState, timedelta] = {
    ScreenState.QUEUE_REQUESTED: timedelta(minutes=15),
    ScreenState.HERO_SELECT: timedelta(seconds=20),
    ScreenState.SPAWN_ROOM: timedelta(seconds=30),
    ScreenState.ACTIVE_GAME: timedelta(minutes=30),
    ScreenState.POST_GAME: timedelta(minutes=2),
}


ALLOWED_TRANSITIONS: dict[ScreenState, set[ScreenState]] = {
    ScreenState.INIT: {ScreenState.MAIN_MENU},
    ScreenState.MAIN_MENU: {ScreenState.MODE_SELECT},
    ScreenState.MODE_SELECT: {ScreenState.QUEUE_REQUESTED},
    ScreenState.QUEUE_REQUESTED: {ScreenState.MATCH_FOUND},
    ScreenState.MATCH_FOUND: {ScreenState.HERO_SELECT},
    ScreenState.HERO_SELECT: {ScreenState.SPAWN_ROOM},
    ScreenState.SPAWN_ROOM: {ScreenState.ACTIVE_GAME},
    ScreenState.ACTIVE_GAME: {ScreenState.POST_GAME},
    ScreenState.POST_GAME: {ScreenState.RESULT_CONFIRMED},
    ScreenState.RESULT_CONFIRMED: {ScreenState.MAIN_MENU, ScreenState.SAFE_EXIT},
    ScreenState.SAFE_EXIT: {ScreenState.STOPPED},
}

SAFE_DESTINATIONS = {
    ScreenState.UNKNOWN_SCREEN,
    ScreenState.MANUAL_INTERVENTION,
    ScreenState.SAFE_EXIT,
    ScreenState.STOPPED,
}


class StateMachine:
    """Consumes observations and stops safely whenever a state is uncertain."""

    def __init__(
        self,
        config: StateMachineConfig | None = None,
        snapshot: SessionSnapshot | None = None,
    ) -> None:
        self.config = config or StateMachineConfig()
        self.state = (snapshot or SessionSnapshot()).current_state
        self.wins = (snapshot or SessionSnapshot()).wins
        self.last_match_result = (snapshot or SessionSnapshot()).last_match_result
        self.consecutive_failures = (snapshot or SessionSnapshot()).consecutive_failures
        self._entered_at = (snapshot or SessionSnapshot()).last_transition_at
        self._observations: deque[Observation] = deque(
            maxlen=self.config.required_consecutive_frames
        )

    def snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            wins=self.wins,
            current_state=self.state,
            last_match_result=self.last_match_result,
            consecutive_failures=self.consecutive_failures,
            last_transition_at=self._entered_at,
        )

    def observe(self, observation: Observation) -> Transition | None:
        """Record one frame and transition only after consistent high-confidence input."""
        if self.state in {ScreenState.STOPPED, ScreenState.SAFE_EXIT}:
            return None

        if observation.confidence < self.config.confidence_threshold:
            return self._fail("low-confidence observation", observation.captured_at)

        self._observations.append(observation)
        if not self._is_stable(observation):
            return None

        self.consecutive_failures = 0
        if observation.state == self.state:
            return None

        if observation.state in {ScreenState.UNKNOWN_SCREEN, ScreenState.MANUAL_INTERVENTION}:
            return self._transition(observation.state, "safety screen detected", observation.captured_at)

        if observation.state not in ALLOWED_TRANSITIONS.get(self.state, set()):
            return self._fail(
                f"invalid transition from {self.state.value} to {observation.state.value}",
                observation.captured_at,
            )

        transition = self._transition(
            observation.state,
            "stable visual state detected",
            observation.captured_at,
        )
        if observation.state == ScreenState.RESULT_CONFIRMED and observation.result is not None:
            self.last_match_result = observation.result
            if observation.result == MatchResult.VICTORY:
                self.wins += 1
        return transition

    def advance(self, now: datetime | None = None) -> Transition | None:
        """Process timeout and result routing without generating input events."""
        now = now or datetime.now(timezone.utc)
        timeout = (self.config.state_timeouts or DEFAULT_TIMEOUTS).get(self.state)
        if timeout is not None and now - self._entered_at > timeout:
            return self._fail(f"{self.state.value} timed out", now)

        if self.state == ScreenState.RESULT_CONFIRMED:
            destination = ScreenState.SAFE_EXIT if self.wins >= self.config.target_wins else ScreenState.MAIN_MENU
            return self._transition(destination, "match result persisted", now)

        if self.state == ScreenState.SAFE_EXIT:
            return self._transition(ScreenState.STOPPED, "safe exit completed", now)
        return None

    def request_stop(self, reason: str = "manual emergency stop") -> Transition | None:
        """Request an immediate safe stop; the input layer must release keys first."""
        if self.state == ScreenState.STOPPED:
            return None
        return self._transition(ScreenState.SAFE_EXIT, reason, datetime.now(timezone.utc))

    def _is_stable(self, latest: Observation) -> bool:
        return len(self._observations) == self.config.required_consecutive_frames and all(
            item.state == latest.state and item.result == latest.result
            for item in self._observations
        )

    def _fail(self, reason: str, occurred_at: datetime) -> Transition | None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.config.max_consecutive_failures:
            return self._transition(ScreenState.MANUAL_INTERVENTION, reason, occurred_at)
        return self._transition(ScreenState.UNKNOWN_SCREEN, reason, occurred_at)

    def _transition(
        self, destination: ScreenState, reason: str, occurred_at: datetime
    ) -> Transition | None:
        if self.state == destination:
            return None
        previous = self.state
        self.state = destination
        self._entered_at = occurred_at
        self._observations.clear()
        return Transition(previous, destination, reason, occurred_at)
