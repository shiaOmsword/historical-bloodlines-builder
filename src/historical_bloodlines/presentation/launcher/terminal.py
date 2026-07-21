from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True, slots=True)
class TerminalRuntime:
    utf8_enabled: bool
    virtual_terminal_enabled: bool
    interactive: bool


def prepare_terminal() -> TerminalRuntime:
    """Make Rich output predictable in cmd.exe, PowerShell and CI logs."""
    interactive = bool(getattr(sys.stdout, "isatty", lambda: False)())
    utf8_enabled = _reconfigure_streams()
    virtual_terminal_enabled = False

    if os.name == "nt":
        utf8_enabled = _set_windows_utf8_codepages() or utf8_enabled
        virtual_terminal_enabled = _enable_windows_virtual_terminal()

    return TerminalRuntime(
        utf8_enabled=utf8_enabled,
        virtual_terminal_enabled=virtual_terminal_enabled,
        interactive=interactive,
    )


def _reconfigure_streams() -> bool:
    configured = False
    for stream in (sys.stdout, sys.stderr):
        configured = _reconfigure_stream(stream) or configured
    return configured


def _reconfigure_stream(stream: TextIO | None) -> bool:
    if stream is None:
        return False
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return False
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        return False
    return True


def _set_windows_utf8_codepages() -> bool:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP.argtypes = [ctypes.c_uint]
        kernel32.SetConsoleOutputCP.restype = ctypes.c_int
        kernel32.SetConsoleCP.argtypes = [ctypes.c_uint]
        kernel32.SetConsoleCP.restype = ctypes.c_int
        output_ok = bool(kernel32.SetConsoleOutputCP(65001))
        input_ok = bool(kernel32.SetConsoleCP(65001))
        return output_ok or input_ok
    except (AttributeError, OSError):
        return False


def _enable_windows_virtual_terminal() -> bool:
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetConsoleMode.restype = wintypes.BOOL
        kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetConsoleMode.restype = wintypes.BOOL

        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        invalid_handle = ctypes.c_void_p(-1).value
        if handle in (None, 0, invalid_handle):
            return False

        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False

        enable_virtual_terminal_processing = 0x0004
        if not kernel32.SetConsoleMode(
            handle,
            mode.value | enable_virtual_terminal_processing,
        ):
            return False
        return True
    except (AttributeError, OSError):
        return False
