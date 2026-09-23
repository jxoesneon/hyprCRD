#!/usr/bin/env python3
"""
Unit tests for core/daemon.py
Verifies configuration detection, environment configuration, process control,
and argument parsing for HyprCRDDaemon.
"""

import os
import sys
import json
import signal
import tempfile
import unittest
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, BASE_DIR)

import core.daemon as daemon_mod  # noqa: E402
from core.daemon import HyprCRDDaemon  # noqa: E402


class TestHyprCRDDaemon(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_dir = os.path.join(self.temp_dir.name, "chrome-remote-desktop")
        os.makedirs(self.config_dir, exist_ok=True)

        # Create a sample host config
        self.sample_config_path = os.path.join(self.config_dir, "host#sample-id.json")
        self.sample_config = {
            "host_id": "test-host-id-1234",
            "host_name": "TestHyprHost",
            "host_secret_hash": "sha256:abc12345",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----",
        }
        with open(self.sample_config_path, "w", encoding="utf-8") as f:
            json.dump(self.sample_config, f)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("core.daemon.DEFAULT_CONFIG_DIR")
    def test_01_find_host_config(self, mock_default_dir):
        mock_default_dir.__str__.return_value = self.config_dir
        with patch("glob.glob", return_value=[self.sample_config_path]):
            daemon = HyprCRDDaemon(wayland_display="wayland-1")
            self.assertEqual(daemon.config_path, self.sample_config_path)

    def test_02_find_host_config_missing(self):
        with patch("glob.glob", return_value=[]):
            with self.assertRaises(FileNotFoundError):
                HyprCRDDaemon(wayland_display="wayland-1")

    def test_03_load_host_config(self):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        cfg = daemon._load_host_config()
        self.assertEqual(cfg["host_id"], "test-host-id-1234")
        self.assertEqual(cfg["host_name"], "TestHyprHost")

    @patch("subprocess.run")
    def test_04_start_portal_when_already_running(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0)
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        daemon.start_portal_if_needed()
        self.assertIsNone(
            daemon.portal_proc, "Should not spawn a new portal if bus service exists"
        )

    @patch("subprocess.run")
    @patch("subprocess.Popen")
    def test_05_start_portal_when_not_running(self, mock_popen, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=1)
        mock_portal_proc = MagicMock()
        mock_portal_proc.stdout = ["Portal ready line\n", ""]
        mock_portal_proc.poll.return_value = 0
        mock_popen.return_value = mock_portal_proc

        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        daemon.start_portal_if_needed()
        self.assertIsNotNone(
            daemon.portal_proc, "Should spawn portal process if not on bus"
        )

    def test_06_stop_lifecycle(self):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        mock_host = MagicMock()
        mock_host.poll.return_value = None
        mock_portal = MagicMock()
        mock_portal.poll.return_value = None
        daemon.host_proc = mock_host
        daemon.portal_proc = mock_portal
        daemon.running = True

        daemon.stop()
        self.assertFalse(daemon.running)
        mock_host.terminate.assert_called_once()
        mock_portal.terminate.assert_called_once()

    def test_07_signal_handling(self):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        daemon.running = True

        # Test SIGUSR1 (host ready)
        daemon._on_sigusr1(signal.SIGUSR1, None)
        self.assertTrue(daemon.host_ready)

        # Test shutdown signal handler
        with patch.object(daemon, "stop") as mock_stop:
            with self.assertRaises(SystemExit):
                daemon._on_shutdown(signal.SIGTERM, None)
            mock_stop.assert_called_once()

    @patch("subprocess.Popen")
    @patch.object(HyprCRDDaemon, "start_portal_if_needed")
    def test_08_run_execution_hardware_drm(self, mock_start_portal, mock_popen):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1",
            config_path=self.sample_config_path,
            audio_pipe="/tmp/test_audio",
        )
        mock_host = MagicMock()
        mock_host.stdin = MagicMock()
        mock_host.stdout = ["Host ready line\n"]
        # Poll returns None first iteration, then 0 to terminate loop, and 0 during stop
        mock_host.poll.side_effect = [None, 0, 0, 0]
        mock_popen.return_value = mock_host

        with patch(
            "os.path.exists",
            side_effect=lambda p: p
            in ("/dev/dri/renderD128", str(daemon_mod.PAM_SHIM)),
        ):
            daemon.run()

        mock_start_portal.assert_called_once()
        mock_popen.assert_called_once()
        call_args, call_kwargs = mock_popen.call_args
        self.assertIn("--audio-pipe-name=/tmp/test_audio", call_args[0])
        env = call_kwargs["env"]
        self.assertEqual(env["EGL_PLATFORM"], "device")
        self.assertEqual(env["EGL_DEVICE_DRM"], "/dev/dri/renderD128")
        self.assertIn("pam_shim.so", env["LD_PRELOAD"])

    @patch("subprocess.Popen")
    @patch.object(HyprCRDDaemon, "start_portal_if_needed")
    def test_09_run_execution_software_egl(self, mock_start_portal, mock_popen):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        mock_host = MagicMock()
        mock_host.stdin = MagicMock()
        mock_host.stdout = []
        mock_host.poll.side_effect = [0, 0, 0]
        mock_popen.return_value = mock_host

        # Simulate no /dev/dri/renderD128
        with patch("os.path.exists", return_value=False):
            daemon.run()

        mock_popen.assert_called_once()
        _, call_kwargs = mock_popen.call_args
        env = call_kwargs["env"]
        self.assertEqual(env.get("LIBGL_ALWAYS_SOFTWARE"), "1")

    def test_10_stop_with_process_exceptions(self):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        mock_host = MagicMock()
        mock_host.poll.return_value = None
        mock_host.wait.side_effect = Exception("Timeout")
        mock_portal = MagicMock()
        mock_portal.poll.return_value = None
        mock_portal.wait.side_effect = Exception("Timeout")
        daemon.host_proc = mock_host
        daemon.portal_proc = mock_portal

        daemon.stop()
        mock_host.kill.assert_called_once()
        mock_portal.kill.assert_called_once()

    @patch("core.daemon.HyprCRDDaemon.run")
    def test_11_main(self, mock_run):
        with patch.object(
            sys,
            "argv",
            ["daemon.py", "--display=wayland-1", f"--config={self.sample_config_path}"],
        ):
            daemon_mod.main()
            mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("subprocess.Popen")
    def test_12_start_portal_dbus_exception_and_running(self, mock_popen, mock_subproc):
        mock_subproc.side_effect = Exception("DBus check error")
        mock_portal = MagicMock()
        mock_portal.stdout = ["Started\n"]
        mock_portal.poll.return_value = None  # Process remains running
        mock_popen.return_value = mock_portal

        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        daemon.start_portal_if_needed()
        self.assertIsNotNone(daemon.portal_proc)

    @patch("subprocess.Popen")
    @patch.object(HyprCRDDaemon, "start_portal_if_needed")
    def test_13_run_stdin_error(self, mock_start_portal, mock_popen):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        mock_host = MagicMock()
        mock_host.stdin.write.side_effect = Exception("Broken pipe")
        mock_host.stdout = []
        mock_host.poll.side_effect = [0, 0, 0]
        mock_popen.return_value = mock_host

        daemon.run()
        mock_popen.assert_called_once()

    @patch("time.sleep", side_effect=KeyboardInterrupt)
    @patch("subprocess.Popen")
    @patch.object(HyprCRDDaemon, "start_portal_if_needed")
    def test_14_run_keyboard_interrupt(self, mock_start_portal, mock_popen, mock_sleep):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        mock_host = MagicMock()
        mock_host.stdin = MagicMock()
        mock_host.stdout = []
        mock_host.poll.return_value = None
        mock_popen.return_value = mock_host

        daemon.run()
        self.assertFalse(daemon.running)


if __name__ == "__main__":
    unittest.main()
