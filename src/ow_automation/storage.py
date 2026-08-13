"""Atomic local persistence for state-machine session snapshots."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping

from .models import MatchResult, ScreenState, SessionSnapshot


class SessionStore:
    """Read and atomically write minimal session state without a database."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> SessionSnapshot:
        if not self.path.exists():
            return SessionSnapshot()
        with self.path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        if not isinstance(raw, Mapping):
            raise ValueError("session state must be a JSON object")
        return _snapshot_from_mapping(raw)

    def save(self, snapshot: SessionSnapshot) -> None:
        """Atomically replace state so interruption cannot leave partial JSON."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "wins": snapshot.wins,
            "current_state": snapshot.current_state.value,
            "last_match_result": snapshot.last_match_result.value if snapshot.last_match_result else None,
            "consecutive_failures": snapshot.consecutive_failures,
            "last_transition_at": snapshot.last_transition_at.astimezone(timezone.utc).isoformat(),
        }
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.path.parent,
            prefix=f".{self.path.name}.", suffix=".tmp", delete=False,
        ) as file:
            json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
            temp_path = Path(file.name)
        os.replace(temp_path, self.path)


def _snapshot_from_mapping(raw: Mapping[str, Any]) -> SessionSnapshot:
    try:
        result_value = raw.get("last_match_result")
        return SessionSnapshot(
            wins=int(raw.get("wins", 0)),
            current_state=ScreenState(str(raw.get("current_state", ScreenState.INIT.value))),
            last_match_result=MatchResult(result_value) if result_value is not None else None,
            consecutive_failures=int(raw.get("consecutive_failures", 0)),
            last_transition_at=datetime.fromisoformat(str(raw["last_transition_at"])),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid session state") from error
