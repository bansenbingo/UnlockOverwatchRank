"""Bounded, fail-safe system input primitives.

The controller accepts only structured click and movement actions. It never
executes free-form macros, and every early exit releases the keys it owns.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from time import monotonic, sleep
from typing import Callable, Protocol, Sequence


SAFE_MOVEMENT_KEYS = frozenset({"w", "a", "s", "d"})


class InputBackend(Protocol):
    """Minimal system-input adapter; production code may use pynput or SendInput."""

    def key_down(self, key: str) -> None: ...

    def key_up(self, key: str) -> None: ...

    def click(self, x: int, y: int) -> None: ...


@dataclass(frozen=True)
class ClickAction:
    x: int
    y: int


@dataclass(frozen=True)
class MovementStep:
    """A short, bounded movement action intended only for controlled testing."""

    keys: frozenset[str]
    duration_seconds: float

    def __post_init__(self) -> None:
        if not self.keys:
            raise ValueError("movement step requires at least one key")
        if not self.keys <= SAFE_MOVEMENT_KEYS:
            raise ValueError("movement step includes a key outside the safe movement set")
        if self.duration_seconds <= 0:
            raise ValueError("movement duration must be positive")


class InputSafetyError(RuntimeError):
    """Raised when a requested input action would violate a safety constraint."""


class PynputInputBackend:
    """Production backend with lazy imports so offline tests remain platform-neutral."""

    def __init__(self) -> None:
        try:
            from pynput.keyboard import Controller as KeyboardController
            from pynput.mouse import Button, Controller as MouseController
        except ImportError as error:  # pragma: no cover - requirements protect this path
            raise RuntimeError("pynput is not installed") from error
        self._keyboard = KeyboardController()
        self._mouse = MouseController()
        self._button = Button.left

    def key_down(self, key: str) -> None:
        self._keyboard.press(key)

    def key_up(self, key: str) -> None:
        self._keyboard.release(key)

    def click(self, x: int, y: int) -> None:
        self._mouse.position = (x, y)
        self._mouse.click(self._button)


class InputController:
    """Executes finite actions and guarantees release of tracked keys."""

    def __init__(
        self,
        backend: InputBackend,
        *,
        max_step_seconds: float = 2.0,
        max_sequence_seconds: float = 10.0,
        focus_is_valid: Callable[[], bool] | None = None,
        stop_event: Event | None = None,
        sleeper: Callable[[float], None] = sleep,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_step_seconds <= 0 or max_sequence_seconds <= 0:
            raise ValueError("input duration limits must be positive")
        self.backend = backend
        self.max_step_seconds = max_step_seconds
        self.max_sequence_seconds = max_sequence_seconds
        self.focus_is_valid = focus_is_valid or (lambda: True)
        self.stop_event = stop_event or Event()
        self._sleeper = sleeper
        self._clock = clock
        self._held_keys: set[str] = set()

    @property
    def held_keys(self) -> frozenset[str]:
        return frozenset(self._held_keys)

    def click(self, action: ClickAction) -> None:
        self._ensure_ready()
        self.backend.click(action.x, action.y)

    def execute_movement(self, steps: Sequence[MovementStep]) -> None:
        """Execute a finite sequence; aborting at any point releases all keys."""
        total_duration = sum(step.duration_seconds for step in steps)
        if total_duration > self.max_sequence_seconds:
            raise InputSafetyError("movement sequence exceeds the configured maximum duration")
        if any(step.duration_seconds > self.max_step_seconds for step in steps):
            raise InputSafetyError("movement step exceeds the configured maximum duration")

        started_at = self._clock()
        try:
            for step in steps:
                self._ensure_ready()
                self._hold(step.keys)
                self._wait_while_safe(step.duration_seconds, started_at)
                self.release_all()
        except BaseException:
            self.release_all()
            raise
        finally:
            self.release_all()

    def request_stop(self) -> None:
        self.stop_event.set()
        self.release_all()

    def release_all(self) -> None:
        """Best effort: no key may remain pressed even if one release fails."""
        errors: list[Exception] = []
        for key in tuple(self._held_keys):
            try:
                self.backend.key_up(key)
            except Exception as error:  # pragma: no cover - physical backends vary
                errors.append(error)
            finally:
                self._held_keys.discard(key)
        if errors:
            raise InputSafetyError("failed to release one or more keys") from errors[0]

    def _hold(self, keys: frozenset[str]) -> None:
        for key in sorted(keys):
            self.backend.key_down(key)
            self._held_keys.add(key)

    def _wait_while_safe(self, duration_seconds: float, started_at: float) -> None:
        deadline = self._clock() + duration_seconds
        while self._clock() < deadline:
            self._ensure_ready()
            if self._clock() - started_at > self.max_sequence_seconds:
                raise InputSafetyError("movement sequence exceeded its deadline")
            self._sleeper(min(0.05, deadline - self._clock()))

    def _ensure_ready(self) -> None:
        if self.stop_event.is_set():
            raise InputSafetyError("emergency stop is active")
        if not self.focus_is_valid():
            raise InputSafetyError("target window is no longer focused")
