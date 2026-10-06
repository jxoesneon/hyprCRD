#!/usr/bin/env python3
"""
Unit tests for bin/hyprcrd-picker
Verifies the CRD-only auto-selection handshake (select-pending marker),
delegation to hyprland-share-picker, and fail-closed behavior.
"""

import os
import time
import tempfile
import unittest
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PICKER = BASE_DIR / "bin" / "hyprcrd-picker"


class TestHyprcrdPicker(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        tmp = Path(self.temp_dir.name)

        self.runtime_dir = tmp / "runtime"
        self.marker_dir = self.runtime_dir / "hyprcrd"
        self.marker_dir.mkdir(parents=True)
        self.marker = self.marker_dir / "select-pending"

        self.stub_dir = tmp / "stubbin"
        self.stub_dir.mkdir()
        self.stub_log = tmp / "picker-invoked"

        stub_hyprctl = self.stub_dir / "hyprctl"
        stub_hyprctl.write_text('#!/bin/sh\necho \'[{"name":"eDP-1"}]\'\n')
        stub_hyprctl.chmod(0o755)

        self.stub_picker = self.stub_dir / "hyprland-share-picker"
        self.stub_picker.write_text(
            "#!/bin/sh\n"
            f'echo invoked >> "{self.stub_log}"\n'
            'echo "[SELECTION]stub-picker"\n'
        )
        self.stub_picker.chmod(0o755)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _run_picker(self, share_picker=None):
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = str(self.runtime_dir)
        env["PATH"] = f"{self.stub_dir}:{env['PATH']}"
        env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
        env["HYPRCRD_SHARE_PICKER"] = (
            str(share_picker) if share_picker else str(self.stub_picker)
        )
        return subprocess.run(
            ["bash", str(PICKER)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

    def _write_marker(self, age_seconds=0):
        self.marker.write_text("/org/freedesktop/portal/desktop/session/1_2/test")
        mtime = time.time() - age_seconds
        os.utime(self.marker, (mtime, mtime))

    def test_01_fresh_marker_auto_selects_and_consumes(self):
        self._write_marker()
        result = self._run_picker()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[SELECTION]r/screen:eDP-1", result.stdout)
        self.assertFalse(self.marker.exists(), "marker must be consumed")
        self.assertFalse(self.stub_log.exists(), "share picker must not be invoked")

    def test_02_stale_marker_delegates(self):
        self._write_marker(age_seconds=60)
        result = self._run_picker()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[SELECTION]stub-picker", result.stdout)
        self.assertTrue(self.stub_log.exists())
        self.assertTrue(self.marker.exists(), "stale marker must not be consumed")

    def test_03_no_marker_delegates(self):
        result = self._run_picker()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[SELECTION]stub-picker", result.stdout)
        self.assertTrue(self.stub_log.exists())

    def test_04_no_marker_no_picker_fails_closed(self):
        result = self._run_picker(share_picker=self.stub_dir / "nonexistent-picker")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("[SELECTION]", result.stdout)


if __name__ == "__main__":
    unittest.main()
