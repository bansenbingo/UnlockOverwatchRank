"""Native Windows adapters for authorized desktop testing.

These adapters use documented user32 APIs only. They do not open a process,
read memory, inject code, inspect network traffic, or attempt to evade game
security controls. The module remains importable on macOS, but construction of
Windows-only adapters fails clearly until run on Windows.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

from .capture import CaptureRegion
from .input_control import InputBackend


if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
else:
    _user32 = None


class WindowsPlatformError(RuntimeError):
    """Raised when a Windows adapter is used on a non-Windows host."""


class _KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("ki", _KeyboardInput), ("mi", _MouseInput)]


class _Input(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", _InputUnion)]


KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1
INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
VK_BY_KEY = {"w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44}


def _require_windows() -> None:
    if _user32 is None:
        raise WindowsPlatformError("Windows adapters require a Windows host")


class WindowsInputBackend(InputBackend):
    """InputBackend implementation backed by user32.SendInput."""

    def __init__(self) -> None:
        _require_windows()

    def key_down(self, key: str) -> None:
        self._send_key(key, 0)

    def key_up(self, key: str) -> None:
        self._send_key(key, KEYEVENTF_KEYUP)

    def click(self, x: int, y: int) -> None:
        _require_windows()
        if not _user32.SetCursorPos(x, y):
            raise ctypes.WinError(ctypes.get_last_error())
        self._send(
            _Input(
                type=INPUT_MOUSE,
                mi=_MouseInput(
                    dx=0,
                    dy=0,
                    mouseData=0,
                    dwFlags=MOUSEEVENTF_LEFTDOWN,
                    time=0,
                    dwExtraInfo=None,
                ),
            )
        )
        self._send(
            _Input(
                type=INPUT_MOUSE,
                mi=_MouseInput(
                    dx=x,
                    dy=y,
                    mouseData=0,
                    dwFlags=MOUSEEVENTF_LEFTUP,
                    time=0,
                    dwExtraInfo=None,
                ),
            )
        )

    def _send_key(self, key: str, flags: int) -> None:
        _require_windows()
        try:
            virtual_key = VK_BY_KEY[key.casefold()]
        except KeyError as error:
            raise ValueError(f"unsupported Windows movement key: {key!r}") from error
        self._send(
            _Input(
                type=INPUT_KEYBOARD,
                ki=_KeyboardInput(
                    wVk=virtual_key,
                    wScan=0,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=None,
                ),
            )
        )

    @staticmethod
    def _send(event: _Input) -> None:
        sent = _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(_Input))
        if sent != 1:
            raise ctypes.WinError(ctypes.get_last_error())


@dataclass(frozen=True)
class WindowsWindow:
    """A visible top-level window selected by title, not by process inspection."""

    hwnd: int

    @classmethod
    def find_title_contains(cls, title_part: str) -> "WindowsWindow | None":
        _require_windows()
        if not title_part:
            raise ValueError("title_part must not be empty")
        found: list[int] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd: int, _lparam: int) -> bool:
            if not _user32.IsWindowVisible(hwnd):
                return True
            buffer = ctypes.create_unicode_buffer(512)
            _user32.GetWindowTextW(hwnd, buffer, len(buffer))
            if title_part.casefold() in buffer.value.casefold():
                found.append(hwnd)
                return False
            return True

        _user32.EnumWindows(callback, 0)
        return cls(found[0]) if found else None

    def is_focused(self) -> bool:
        _require_windows()
        return int(_user32.GetForegroundWindow()) == self.hwnd

    def focus(self) -> bool:
        _require_windows()
        return bool(_user32.SetForegroundWindow(self.hwnd))

    def capture_region(self) -> CaptureRegion:
        _require_windows()
        rect = wintypes.RECT()
        if not _user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            raise ctypes.WinError(ctypes.get_last_error())
        return CaptureRegion(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
