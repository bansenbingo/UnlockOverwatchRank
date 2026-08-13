"""Conservative screen-driven desktop automation primitives."""

from .models import MatchResult, Observation, ScreenState, SessionSnapshot, Transition
from .state_machine import StateMachine, StateMachineConfig

__all__ = [
    "MatchResult",
    "Observation",
    "ScreenState",
    "SessionSnapshot",
    "StateMachine",
    "StateMachineConfig",
    "Transition",
]
