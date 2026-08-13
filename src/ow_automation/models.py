"""Shared data models for the visual automation state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping


class ScreenState(str, Enum):
    """Supported UI states and safe stop states."""

    INIT = "INIT"
    MAIN_MENU = "MAIN_MENU"
    MODE_SELECT = "MODE_SELECT"
    QUEUE_REQUESTED = "QUEUE_REQUESTED"
    MATCH_FOUND = "MATCH_FOUND"
    HERO_SELECT = "HERO_SELECT"
    SPAWN_ROOM = "SPAWN_ROOM"
    ACTIVE_GAME = "ACTIVE_GAME"
    POST_GAME = "POST_GAME"
    RESULT_CONFIRMED = "RESULT_CONFIRMED"
    AWAIT_MAIN_MENU = "AWAIT_MAIN_MENU"
    SAFE_EXIT = "SAFE_EXIT"
    STOPPED = "STOPPED"
    UNKNOWN_SCREEN = "UNKNOWN_SCREEN"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"


class MatchResult(str, Enum):
    """A result is counted only after the end screen is confidently classified."""

    VICTORY = "VICTORY"
    DEFEAT = "DEFEAT"


@dataclass(frozen=True)
class Observation:
    """One classified frame from the screen-recognition layer."""

    state: ScreenState
    confidence: float
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    result: MatchResult | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if self.result is not None and self.state != ScreenState.RESULT_CONFIRMED:
            raise ValueError("a match result is valid only for RESULT_CONFIRMED")


@dataclass(frozen=True)
class Transition:
    """An auditable state transition emitted by the state machine."""

    previous: ScreenState
    current: ScreenState
    reason: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class SessionSnapshot:
    """Serializable session information owned by the persistence layer."""

    wins: int = 0
    current_state: ScreenState = ScreenState.INIT
    last_match_result: MatchResult | None = None
    consecutive_failures: int = 0
    last_transition_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
