from datetime import datetime, timezone

import pytest

from ow_automation import MatchResult, ScreenState, SessionSnapshot, SessionStore


def test_store_round_trips_snapshot_atomically(tmp_path) -> None:
    path = tmp_path / "runtime" / "session.json"
    snapshot = SessionSnapshot(
        wins=7,
        current_state=ScreenState.POST_GAME,
        last_match_result=MatchResult.VICTORY,
        consecutive_failures=1,
        last_transition_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )

    store = SessionStore(path)
    store.save(snapshot)

    assert store.load() == snapshot
    assert not list(path.parent.glob("*.tmp"))


def test_store_rejects_invalid_json_schema(tmp_path) -> None:
    path = tmp_path / "session.json"
    path.write_text('{"current_state": "NOT_A_STATE"}', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid session state"):
        SessionStore(path).load()
