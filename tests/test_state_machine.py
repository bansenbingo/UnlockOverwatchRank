from datetime import datetime, timedelta, timezone

from ow_automation import MatchResult, Observation, ScreenState, StateMachine, StateMachineConfig


def observation(state: ScreenState, result: MatchResult | None = None) -> Observation:
    return Observation(state=state, confidence=0.99, result=result)


def stabilize(machine: StateMachine, state: ScreenState, result: MatchResult | None = None):
    transition = None
    for _ in range(machine.config.required_consecutive_frames):
        transition = machine.observe(observation(state, result))
    return transition


def test_progresses_only_after_stable_observations() -> None:
    machine = StateMachine(StateMachineConfig(required_consecutive_frames=2))

    assert machine.observe(observation(ScreenState.MAIN_MENU)) is None
    transition = machine.observe(observation(ScreenState.MAIN_MENU))

    assert transition is not None
    assert transition.current == ScreenState.MAIN_MENU


def test_invalid_transition_is_sent_to_unknown_screen() -> None:
    machine = StateMachine(StateMachineConfig(required_consecutive_frames=1))

    transition = machine.observe(observation(ScreenState.ACTIVE_GAME))

    assert transition is not None
    assert transition.current == ScreenState.UNKNOWN_SCREEN


def test_victory_is_counted_once_and_routes_to_safe_exit() -> None:
    machine = StateMachine(StateMachineConfig(required_consecutive_frames=1, target_wins=1))
    for state in (
        ScreenState.MAIN_MENU,
        ScreenState.MODE_SELECT,
        ScreenState.QUEUE_REQUESTED,
        ScreenState.MATCH_FOUND,
        ScreenState.HERO_SELECT,
        ScreenState.SPAWN_ROOM,
        ScreenState.ACTIVE_GAME,
        ScreenState.POST_GAME,
    ):
        stabilize(machine, state)

    stabilize(machine, ScreenState.RESULT_CONFIRMED, MatchResult.VICTORY)
    assert machine.snapshot().wins == 1

    transition = machine.advance()
    assert transition is not None
    assert transition.current == ScreenState.SAFE_EXIT

    transition = machine.advance()
    assert transition is not None
    assert transition.current == ScreenState.STOPPED


def test_result_waits_for_visual_main_menu_before_next_queue() -> None:
    machine = StateMachine(StateMachineConfig(required_consecutive_frames=1, target_wins=2))
    for state in (
        ScreenState.MAIN_MENU,
        ScreenState.MODE_SELECT,
        ScreenState.QUEUE_REQUESTED,
        ScreenState.MATCH_FOUND,
        ScreenState.HERO_SELECT,
        ScreenState.SPAWN_ROOM,
        ScreenState.ACTIVE_GAME,
        ScreenState.POST_GAME,
    ):
        stabilize(machine, state)
    stabilize(machine, ScreenState.RESULT_CONFIRMED, MatchResult.DEFEAT)

    transition = machine.advance()
    assert transition is not None
    assert transition.current == ScreenState.AWAIT_MAIN_MENU

    transition = stabilize(machine, ScreenState.MAIN_MENU)
    assert transition is not None
    assert transition.current == ScreenState.MAIN_MENU


def test_timeout_stops_for_manual_intervention_after_failure_limit() -> None:
    entered = datetime(2026, 1, 1, tzinfo=timezone.utc)
    machine = StateMachine(
        StateMachineConfig(
            required_consecutive_frames=1,
            max_consecutive_failures=1,
            state_timeouts={ScreenState.INIT: timedelta(seconds=1)},
        )
    )
    machine._entered_at = entered

    transition = machine.advance(entered + timedelta(seconds=2))

    assert transition is not None
    assert transition.current == ScreenState.MANUAL_INTERVENTION
