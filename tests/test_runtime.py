from datetime import datetime, timezone

import numpy as np

from ow_automation import Observation, ScreenState, SessionStore, StateMachine, StateMachineConfig
from ow_automation.capture import CapturedFrame, CaptureRegion
from ow_automation.input_control import InputController, MovementStep
from ow_automation.runtime import ActionPlan, Runtime


class FakeSource:
    def capture(self) -> CapturedFrame:
        return CapturedFrame(
            image=np.zeros((4, 4, 3), dtype=np.uint8),
            region=CaptureRegion(0, 0, 4, 4),
            captured_at=datetime.now(timezone.utc),
        )


class FixedClassifier:
    def __init__(self, state: ScreenState) -> None:
        self.state = state

    def classify(self, frame: CapturedFrame) -> Observation:
        return Observation(self.state, confidence=0.99, captured_at=frame.captured_at)


class FakeBackend:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def key_down(self, key: str) -> None:
        self.events.append(("down", key))

    def key_up(self, key: str) -> None:
        self.events.append(("up", key))

    def click(self, x: int, y: int) -> None:
        self.events.append(("click", f"{x},{y}"))


def test_runtime_persists_transition_and_runs_bounded_spawn_movement(tmp_path) -> None:
    backend = FakeBackend()
    machine = StateMachine(StateMachineConfig(required_consecutive_frames=1))
    machine.state = ScreenState.HERO_SELECT
    runtime = Runtime(
        source=FakeSource(),
        classifier=FixedClassifier(ScreenState.SPAWN_ROOM),
        state_machine=machine,
        store=SessionStore(tmp_path / "session.json"),
        input_controller=InputController(backend, max_step_seconds=1, max_sequence_seconds=1),
        action_plan=ActionPlan(movement_on_spawn=(MovementStep(frozenset({"w"}), 0.01),)),
    )

    transition = runtime.tick()

    assert transition is not None
    assert transition.current == ScreenState.SPAWN_ROOM
    assert runtime.store.load().current_state == ScreenState.SPAWN_ROOM
    assert ("down", "w") in backend.events
    assert ("up", "w") in backend.events


def test_runtime_releases_held_keys_for_unknown_screen(tmp_path) -> None:
    backend = FakeBackend()
    machine = StateMachine(StateMachineConfig(required_consecutive_frames=1))
    machine.state = ScreenState.MAIN_MENU
    controller = InputController(backend)
    controller._hold(frozenset({"w"}))
    runtime = Runtime(
        source=FakeSource(),
        classifier=FixedClassifier(ScreenState.UNKNOWN_SCREEN),
        state_machine=machine,
        store=SessionStore(tmp_path / "session.json"),
        input_controller=controller,
    )

    transition = runtime.tick()

    assert transition is not None
    assert transition.current == ScreenState.UNKNOWN_SCREEN
    assert controller.held_keys == frozenset()
    assert ("up", "w") in backend.events
