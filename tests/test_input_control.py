from threading import Event

import pytest

from ow_automation.input_control import InputController, InputSafetyError, MovementStep


class FakeBackend:
    def __init__(self) -> None:
        self.events: list[tuple[str, str | int, int | None]] = []

    def key_down(self, key: str) -> None:
        self.events.append(("down", key, None))

    def key_up(self, key: str) -> None:
        self.events.append(("up", key, None))

    def click(self, x: int, y: int) -> None:
        self.events.append(("click", x, y))


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def test_movement_releases_each_key_after_every_step() -> None:
    backend = FakeBackend()
    clock = FakeClock()
    controller = InputController(
        backend, max_step_seconds=1, max_sequence_seconds=2, sleeper=clock.sleep, clock=clock
    )

    controller.execute_movement([MovementStep(frozenset({"w", "a"}), 0.1)])

    assert controller.held_keys == frozenset()
    assert {event[1] for event in backend.events if event[0] == "up"} == {"w", "a"}


def test_focus_loss_releases_keys_and_stops_action() -> None:
    backend = FakeBackend()
    clock = FakeClock()
    focus_checks = iter((True, False))
    controller = InputController(
        backend,
        max_step_seconds=1,
        max_sequence_seconds=2,
        focus_is_valid=lambda: next(focus_checks),
        sleeper=clock.sleep,
        clock=clock,
    )

    with pytest.raises(InputSafetyError, match="focused"):
        controller.execute_movement([MovementStep(frozenset({"w"}), 0.1)])

    assert controller.held_keys == frozenset()
    assert ("up", "w", None) in backend.events


def test_emergency_stop_prevents_input() -> None:
    backend = FakeBackend()
    stop_event = Event()
    stop_event.set()
    controller = InputController(backend, stop_event=stop_event)

    with pytest.raises(InputSafetyError, match="emergency stop"):
        controller.execute_movement([MovementStep(frozenset({"w"}), 0.1)])

    assert backend.events == []


def test_rejects_disallowed_keys_and_excessive_sequences() -> None:
    with pytest.raises(ValueError, match="safe movement"):
        MovementStep(frozenset({"space"}), 0.1)

    controller = InputController(FakeBackend(), max_step_seconds=1, max_sequence_seconds=1)
    with pytest.raises(InputSafetyError, match="sequence"):
        controller.execute_movement([MovementStep(frozenset({"w"}), 1.1)])
