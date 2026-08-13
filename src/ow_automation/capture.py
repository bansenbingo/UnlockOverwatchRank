"""Screen capture adapters that return RGB frames without process access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class CaptureRegion:
    """An explicit desktop rectangle; coordinates are never inferred from a process."""

    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("capture region width and height must be positive")

    def as_mss_monitor(self) -> dict[str, int]:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class CapturedFrame:
    """A timestamped RGB image captured from a configured desktop region."""

    image: np.ndarray
    region: CaptureRegion
    captured_at: datetime

    def __post_init__(self) -> None:
        if self.image.ndim != 3 or self.image.shape[2] != 3:
            raise ValueError("captured frames must be RGB images with three channels")
        if self.image.shape[:2] != (self.region.height, self.region.width):
            raise ValueError("captured frame dimensions must match its region")


class FrameSource(Protocol):
    """Minimal capture interface that enables simulated tests and platform adapters."""

    def capture(self) -> CapturedFrame:
        """Return exactly one RGB frame."""


class MssFrameSource:
    """Desktop-region capture implemented with mss; works without game integration."""

    def __init__(self, region: CaptureRegion) -> None:
        self.region = region

    def capture(self) -> CapturedFrame:
        try:
            import mss
        except ImportError as error:  # pragma: no cover - requirements protect this path
            raise RuntimeError("mss is not installed") from error
        with mss.mss() as recorder:
            bgra = np.asarray(recorder.grab(self.region.as_mss_monitor()))
        rgb = bgra[:, :, :3][:, :, ::-1].copy()
        return CapturedFrame(rgb, self.region, datetime.now(timezone.utc))


class StaticFrameSource:
    """A deterministic frame source for replay tests and local development."""

    def __init__(self, image: np.ndarray, region: CaptureRegion | None = None) -> None:
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("static image must be an RGB image with three channels")
        self.image = image.copy()
        self.region = region or CaptureRegion(0, 0, image.shape[1], image.shape[0])

    def capture(self) -> CapturedFrame:
        return CapturedFrame(
            image=self.image.copy(), region=self.region, captured_at=datetime.now(timezone.utc)
        )
