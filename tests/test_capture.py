import numpy as np
import pytest

from ow_automation.capture import CaptureRegion, StaticFrameSource


def test_capture_region_rejects_non_positive_dimensions() -> None:
    with pytest.raises(ValueError, match="positive"):
        CaptureRegion(0, 0, 0, 100)


def test_static_frame_source_returns_rgb_copy_and_region() -> None:
    image = np.zeros((4, 6, 3), dtype=np.uint8)
    image[0, 0] = (1, 2, 3)
    source = StaticFrameSource(image)

    frame = source.capture()
    image[0, 0] = (0, 0, 0)

    assert frame.image.shape == (4, 6, 3)
    assert tuple(frame.image[0, 0]) == (1, 2, 3)
    assert frame.region == CaptureRegion(0, 0, 6, 4)
