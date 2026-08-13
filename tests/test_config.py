from datetime import timedelta

import pytest

from ow_automation.config import load_config
from ow_automation.models import ScreenState


def test_load_config_maps_safety_values(tmp_path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
window:
  expected_resolution: [2560, 1440]
recognition:
  confidence_threshold: 0.95
  required_consecutive_frames: 4
timeouts:
  queue_seconds: 120
session:
  target_wins: 3
  state_file: custom/session.json
""",
        encoding="utf-8",
    )

    config = load_config(config_file)
    machine_config = config.state_machine_config()

    assert config.window.expected_resolution == (2560, 1440)
    assert config.session.state_file.as_posix() == "custom/session.json"
    assert machine_config.confidence_threshold == 0.95
    assert machine_config.required_consecutive_frames == 4
    assert machine_config.target_wins == 3
    assert machine_config.state_timeouts is not None
    assert machine_config.state_timeouts[ScreenState.QUEUE_REQUESTED] == timedelta(seconds=120)


def test_rejects_invalid_resolution(tmp_path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("window:\n  expected_resolution: [1920]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="expected_resolution"):
        load_config(config_file)
