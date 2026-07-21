from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


APP_DIRECTORY_NAME = "Historical Bloodlines"
CSIDL_PERSONAL = 5
SHGFP_TYPE_CURRENT = 0


def repository_root() -> Path:
    """Return the project root while running from source."""
    return Path(__file__).resolve().parents[3]


def runtime_resources_dir() -> Path:
    """Return the directory containing resources bundled by PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return repository_root()


def documents_directory() -> Path:
    """Resolve the user's Documents directory without hard-coding a locale."""
    override = os.getenv("BLOODLINES_DOCUMENTS_DIR")
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        buffer = ctypes.create_unicode_buffer(260)
        result = ctypes.windll.shell32.SHGetFolderPathW(  # type: ignore[attr-defined]
            None,
            CSIDL_PERSONAL,
            None,
            SHGFP_TYPE_CURRENT,
            buffer,
        )
        if result == 0 and buffer.value:
            return Path(buffer.value)

    return Path.home() / "Documents"


def default_data_directory() -> Path:
    return documents_directory() / APP_DIRECTORY_NAME
