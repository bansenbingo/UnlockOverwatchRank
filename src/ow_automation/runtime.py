"""Runtime orchestration between capture, recognition, persistence, and input.

The runtime is deliberately conservative: observations cause state transitions;
only selected transitions map to a predeclared action plan. Any safe/unknown
state releases all held keys before returning control to the operator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Protocol

from .capture import CapturedFrame, FrameSource
from .input_control import ClickAction, InputController, MovementStep
from .models import Observation, ScreenState, Transition
from .state_machine import StateMachine
from .storage import SessionStore


class FrameClassifier(Protocol):
    """Classifies a captured frame without performing input."""

    def classify(self, frame: CapturedFrame) -> Observation:
        """Return the strongest current visual observation."""


@dataclass(frozen=True)
class ClickTarget:
    """A logical click target resolved by a vision layer, not a hardcoded screen action."""

    label: str


@dataclass(frozen=True)
class ActionPlan:
    """Predeclared actions keyed by state-entry transition destinations."""

    clicks: Mapping[ScreenState, ClickTarget] = field(default_factory=dict)
    movement_on_spawn: tuple[MovementStep, ...] = ()


class Runtime:
    """Single-cycle coordinator suitable for a scheduled application loop."""

    def __init__(
        self,
        *,
        source: FrameSource,
        classifier: FrameClassifier,
        state_machine: StateMachine,
        store: SessionStore,
        input_controller: InputController,
        action_plan: ActionPlan = ActionPlan(),
        target_resolver: Callable[[str, CapturedFrame], ClickAction | None] | None = None,
    ) -> None:
        self.source = source
        self.classifier = classifier
        self.state_machine = state_machine
        self.store = store
        self.input_controller = input_controller
        self.action_plan = action_plan
        self.target_resolver = target_resolver

    def tick(self) -> Transition | None:
        """Capture one frame, process one transition, persist, then act if allowed."""
        frame = self.source.capture()
        transition = self.state_machine.observe(self.classifier.classify(frame))
        if transition is None:
            transition = self.state_machine.advance(frame.captured_at)
        if transition is None:
            return None

        self.store.save(self.state_machine.snapshot())
        if transition.current in {
            ScreenState.UNKNOWN_SCREEN,
            ScreenState.MANUAL_INTERVENTION,
            ScreenState.SAFE_EXIT,
            ScreenState.STOPPED,
        }:
            self.input_controller.release_all()
            return transition

        self._execute_transition_action(transition, frame)
        return transition

    def request_stop(self, reason: str = "manual emergency stop") -> Transition | None:
        """Stop input first and persist the resulting safe state."""
        self.input_controller.request_stop()
        transition = self.state_machine.request_stop(reason)
        if transition is not None:
            self.store.save(self.state_machine.snapshot())
        return transition

    def _execute_transition_action(self, transition: Transition, frame: CapturedFrame) -> None:
        if transition.current == ScreenState.SPAWN_ROOM and self.action_plan.movement_on_spawn:
            self.input_controller.execute_movement(self.action_plan.movement_on_spawn)
            return
        target = self.action_plan.clicks.get(transition.current)
        if target is None or self.target_resolver is None:
            return
        action = self.target_resolver(target.label, frame)
        if action is None:
            self.input_controller.release_all()
            return
        self.input_controller.click(action)


def template_asset_path(root: str | Path, label: str) -> Path:
    """Resolve a template label under a caller-controlled assets directory."""
    root = Path(root).resolve()
    candidate = (root / f"{label}.png").resolve()
    if root not in candidate.parents:
        raise ValueError("template label resolves outside the assets directory")
    return candidate
