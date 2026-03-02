"""Tests for chrome_profile.sync_chrome_profile (mocked at filesystem boundary)."""

from pathlib import Path
from unittest.mock import patch

from resume_agent.tools.chrome_profile import sync_chrome_profile


class TestSyncChromeProfile:
    def test_copies_cookie_and_login_files(self, tmp_path: Path):
        """All expected files are copied when source exists."""
        source = tmp_path / "Chrome"
        source_default = source / "Default"
        source_default.mkdir(parents=True)

        expected_files = [
            "Cookies",
            "Cookies-journal",
            "Login Data",
            "Login Data-journal",
            "Login Data For Account",
            "Login Data For Account-journal",
        ]
        for name in expected_files:
            (source_default / name).write_text(f"data-{name}")

        # Also create Local State at root level
        (source / "Local State").write_text("local-state-data")

        debug = tmp_path / "debug-profile"

        sync_chrome_profile(str(debug), source_dir=str(source))

        for name in expected_files:
            dst = debug / "Default" / name
            assert dst.exists(), f"{name} should be copied"
            assert dst.read_text() == f"data-{name}"

        assert (debug / "Local State").exists()
        assert (debug / "Local State").read_text() == "local-state-data"

    def test_graceful_on_missing_files(self, tmp_path: Path):
        """Missing source files are skipped without raising."""
        source = tmp_path / "Chrome"
        source_default = source / "Default"
        source_default.mkdir(parents=True)
        # Only create Cookies, skip the rest
        (source_default / "Cookies").write_text("cookie-data")

        debug = tmp_path / "debug-profile"

        # Should not raise
        sync_chrome_profile(str(debug), source_dir=str(source))

        assert (debug / "Default" / "Cookies").exists()
        assert not (debug / "Default" / "Login Data").exists()

    def test_skips_when_source_not_found(self, tmp_path: Path):
        """When source dir doesn't exist, logs warning and returns."""
        debug = tmp_path / "debug-profile"

        # Should not raise
        sync_chrome_profile(str(debug), source_dir="/nonexistent/path")

        # Debug dir should not be created
        assert not debug.exists()

    def test_auto_detect_source_dir(self, tmp_path: Path):
        """When source_dir is None, auto-detection is attempted."""
        debug = tmp_path / "debug-profile"

        with patch(
            "resume_agent.tools.chrome_profile._detect_source_dir",
            return_value=None,
        ):
            # Should not raise even when auto-detect returns None
            sync_chrome_profile(str(debug))

        assert not debug.exists()

    def test_creates_default_subdirectory(self, tmp_path: Path):
        """The Default/ subdirectory is created even if debug_dir is empty."""
        source = tmp_path / "Chrome"
        source_default = source / "Default"
        source_default.mkdir(parents=True)
        (source_default / "Cookies").write_text("data")

        debug = tmp_path / "debug-profile"
        assert not debug.exists()

        sync_chrome_profile(str(debug), source_dir=str(source))

        assert (debug / "Default").is_dir()
