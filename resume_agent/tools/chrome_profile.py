"""Sync cookies and login data from the real Chrome profile to a debug profile.

Chrome won't share a profile directory with another running instance, so we
maintain a separate debug profile and copy authentication-related files from
the user's real Chrome installation before each launch.
"""

from __future__ import annotations

import logging
import platform
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Files to copy from Default/ subdirectory
_PROFILE_FILES = [
    "Cookies",
    "Cookies-journal",
    "Login Data",
    "Login Data-journal",
    "Login Data For Account",
    "Login Data For Account-journal",
]

# Platform-specific default Chrome user-data directories
_SOURCE_DIRS = {
    "Darwin": "~/Library/Application Support/Google/Chrome",
    "Linux": "~/.config/google-chrome",
}


def _detect_source_dir() -> Path | None:
    """Auto-detect the real Chrome user-data directory for the current platform."""
    template = _SOURCE_DIRS.get(platform.system())
    if not template:
        return None
    p = Path(template).expanduser()
    return p if p.is_dir() else None


def sync_chrome_profile(debug_dir: str, source_dir: str | None = None) -> None:
    """Copy cookie and login files from real Chrome into *debug_dir*.

    Args:
        debug_dir: The ``--user-data-dir`` path used for the debug Chrome instance.
        source_dir: Explicit path to the real Chrome user-data directory.
                    If empty or ``None``, auto-detected from the current platform.
    """
    src_root: Path | None
    if source_dir:
        src_root = Path(source_dir).expanduser()
    else:
        src_root = _detect_source_dir()

    if src_root is None or not src_root.is_dir():
        logger.warning("Chrome source profile not found; skipping cookie sync")
        return

    dst_root = Path(debug_dir).expanduser()
    dst_default = dst_root / "Default"
    dst_default.mkdir(parents=True, exist_ok=True)

    src_default = src_root / "Default"
    copied = 0
    for name in _PROFILE_FILES:
        src = src_default / name
        if not src.exists():
            logger.debug("Skipping missing file: %s", src)
            continue
        try:
            shutil.copy2(src, dst_default / name)
            copied += 1
        except OSError as e:
            logger.warning("Failed to copy %s: %s", name, e)

    # Copy Local State (profile registry) to user-data-dir root
    local_state = src_root / "Local State"
    if local_state.exists():
        try:
            shutil.copy2(local_state, dst_root / "Local State")
        except OSError as e:
            logger.warning("Failed to copy Local State: %s", e)

    logger.info("Synced %d cookie/login files to debug profile %s", copied, dst_root)
