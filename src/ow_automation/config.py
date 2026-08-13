"""Configuration loading for the automation runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping

import yaml

from .models import ScreenState
from .state_machine import DEFAULT_TIMEOUTS, StateMachineConfig


@dataclass(frozen=True)
class WindowConfig:
    expected_resolution: tuple[int, int] = (1920, 1080)
    require_focus: bool = True
    title_contains: str | None = None


@dataclass(frozen=True)
class RecognitionConfig:
    confidence_threshold: float = 0.90
    required_consecutive_frames: int = 3
    capture_interval_ms: int = 300


@dataclass(frozen=True)
class TimeoutConfig:
    queue_seconds: int = 900
    hero_select_seconds: int = 20
    spawn_movement_seconds: int = 30
    active_game_seconds: int = 1800
    post_game_seconds: int = 120

    def as_state_timeouts(self) -> dict[ScreenState, timedelta]:
        return {
            **DEFAULT_TIMEOUTS,
            ScreenState.QUEUE_REQUESTED: timedelta(seconds=self.queue_seconds),
            ScreenState.HERO_SELECT: timedelta(seconds=self.hero_select_seconds),
            ScreenState.SPAWN_ROOM: timedelta(seconds=self.spawn_movement_seconds),
            ScreenState.ACTIVE_GAME: timedelta(seconds=self.active_game_seconds),
            ScreenState.POST_GAME: timedelta(seconds=self.post_game_seconds),
        }


@dataclass(frozen=True)
class SafetyConfig:
    emergency_stop_key: str = "f12"
    max_consecutive_failures: int = 3
    stop_on_unknown_screen: bool = True
    stop_on_focus_loss: bool = True


@dataclass(frozen=True)
class SessionConfig:
    target_wins: int = 50
    state_file: Path = Path("runtime/session.json")
    exit_action: str = "return_to_menu"


@dataclass(frozen=True)
class AppConfig:
    window: WindowConfig = field(default_factory=WindowConfig)
    recognition: RecognitionConfig = field(default_factory=RecognitionConfig)
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    session: SessionConfig = field(default_factory=SessionConfig)

    def state_machine_config(self) -> StateMachineConfig:
        return StateMachineConfig(
            confidence_threshold=self.recognition.confidence_threshold,
            required_consecutive_frames=self.recognition.required_consecutive_frames,
            target_wins=self.session.target_wins,
            max_consecutive_failures=self.safety.max_consecutive_failures,
            state_timeouts=self.timeouts.as_state_timeouts(),
        )


def load_config(path: str | Path) -> AppConfig:
    """Load a YAML configuration file and reject malformed sections early."""
    with Path(path).open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    if not isinstance(raw, Mapping):
        raise ValueError("configuration root must be a mapping")

    window_data = _section(raw, "window")
    recognition_data = _section(raw, "recognition")
    timeout_data = _section(raw, "timeouts")
    safety_data = _section(raw, "safety")
    session_data = _section(raw, "session")
    resolution = window_data.get("expected_resolution", [1920, 1080])
    if not isinstance(resolution, list | tuple) or len(resolution) != 2:
        raise ValueError("window.expected_resolution must contain exactly two values")

    return AppConfig(
        window=WindowConfig(
            expected_resolution=(int(resolution[0]), int(resolution[1])),
            require_focus=bool(window_data.get("require_focus", True)),
            title_contains=_optional_string(window_data.get("title_contains")),
        ),
        recognition=RecognitionConfig(
            confidence_threshold=float(recognition_data.get("confidence_threshold", 0.90)),
            required_consecutive_frames=int(recognition_data.get("required_consecutive_frames", 3)),
            capture_interval_ms=int(recognition_data.get("capture_interval_ms", 300)),
        ),
        timeouts=TimeoutConfig(
            queue_seconds=int(timeout_data.get("queue_seconds", 900)),
            hero_select_seconds=int(timeout_data.get("hero_select_seconds", 20)),
            spawn_movement_seconds=int(timeout_data.get("spawn_movement_seconds", 30)),
            active_game_seconds=int(timeout_data.get("active_game_seconds", 1800)),
            post_game_seconds=int(timeout_data.get("post_game_seconds", 120)),
        ),
        safety=SafetyConfig(
            emergency_stop_key=str(safety_data.get("emergency_stop_key", "f12")).lower(),
            max_consecutive_failures=int(safety_data.get("max_consecutive_failures", 3)),
            stop_on_unknown_screen=bool(safety_data.get("stop_on_unknown_screen", True)),
            stop_on_focus_loss=bool(safety_data.get("stop_on_focus_loss", True)),
        ),
        session=SessionConfig(
            target_wins=int(session_data.get("target_wins", 50)),
            state_file=Path(str(session_data.get("state_file", "runtime/session.json"))),
            exit_action=str(session_data.get("exit_action", "return_to_menu")),
        ),
    )


def _section(data: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("window.title_contains must be a string")
    return value
