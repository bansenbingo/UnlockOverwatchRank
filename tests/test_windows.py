import sys

import pytest

from ow_automation.windows import WindowsInputBackend, WindowsPlatformError, WindowsWindow


@pytest.mark.skipif(sys.platform == "win32", reason="covers the non-Windows guard")
def test_windows_input_backend_is_explicitly_unavailable_off_windows() -> None:
    with pytest.raises(WindowsPlatformError, match="Windows host"):
        WindowsInputBackend()


@pytest.mark.skipif(sys.platform == "win32", reason="covers the non-Windows guard")
def test_windows_window_lookup_is_explicitly_unavailable_off_windows() -> None:
    with pytest.raises(WindowsPlatformError, match="Windows host"):
        WindowsWindow.find_title_contains("Overwatch")
