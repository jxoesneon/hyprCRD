#!/usr/bin/env python3
"""
Comprehensive Unit Tests for bin/hyprcrd CLI
Verifies doctor check, status reporting, process start/stop, restart,
background daemonization, and CLI argument parsing.
"""

import os
import sys
import json
import signal
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR / "bin"))

from importlib.machinery import SourceFileLoader  # noqa: E402

hyprcrd_cli = SourceFileLoader(
    "hyprcrd_cli", str(BASE_DIR / "bin" / "hyprcrd")
).load_module()


class TestHyprCRDCLI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.fake_pid_file = Path(self.temp_dir.name) / "hyprcrd.pid"
        self.fake_config_dir = Path(self.temp_dir.name) / "chrome-remote-desktop"
        self.fake_config_dir.mkdir(parents=True, exist_ok=True)

        # Patch PID_FILE and CONFIG_DIR in the loaded module
        self.patcher_pid = patch.object(hyprcrd_cli, "PID_FILE", self.fake_pid_file)
        self.patcher_cfg = patch.object(hyprcrd_cli, "CONFIG_DIR", self.fake_config_dir)
        self.patcher_pid.start()
        self.patcher_cfg.start()

    def tearDown(self):
        self.patcher_pid.stop()
        self.patcher_cfg.stop()
        self.temp_dir.cleanup()

    def test_01_banner(self):
        with patch("builtins.print") as mock_print:
            hyprcrd_cli.print_banner()
            mock_print.assert_called()

    @patch("subprocess.run")
    def test_02_cmd_doctor_all_passing(self, mock_subproc):
        # Create a mock config file in CONFIG_DIR
        mock_cfg = self.fake_config_dir / "host#123.json"
        mock_cfg.write_text("{}")

        mock_subproc.return_value = MagicMock(returncode=0, stdout="1234 pipewire\n")
        args = MagicMock()
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-1"}):
            with patch("builtins.print") as mock_print:
                hyprcrd_cli.cmd_doctor(args)
                mock_print.assert_called()

    @patch("subprocess.run")
    def test_03_cmd_doctor_with_failures(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=1, stdout="")
        args = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            with patch("builtins.print") as mock_print:
                hyprcrd_cli.cmd_doctor(args)
                mock_print.assert_called()

    @patch("subprocess.run")
    def test_04_cmd_test(self, mock_run):
        args = MagicMock()
        with patch("builtins.print"):
            with patch.object(Path, "exists", return_value=True):
                hyprcrd_cli.cmd_test(args)
                mock_run.assert_called_once()

    @patch("psutil.pid_exists", return_value=True)
    def test_05_cmd_start_already_running(self, mock_pid_exists):
        self.fake_pid_file.write_text("12345")
        args = MagicMock(display="wayland-1", config=None, foreground=False)
        with patch("builtins.print") as mock_print:
            hyprcrd_cli.cmd_start(args)
            mock_print.assert_called()

    @patch("subprocess.run")
    @patch("psutil.pid_exists", return_value=False)
    def test_06_cmd_start_foreground(self, mock_pid_exists, mock_run):
        args = MagicMock(display="wayland-1", config="/tmp/cfg.json", foreground=True)
        with patch("builtins.print"):
            hyprcrd_cli.cmd_start(args)
            mock_run.assert_called_once()

    @patch("subprocess.Popen")
    @patch("psutil.pid_exists", return_value=False)
    def test_07_cmd_start_background(self, mock_pid_exists, mock_popen):
        mock_proc = MagicMock(pid=54321)
        mock_popen.return_value = mock_proc
        args = MagicMock(display="wayland-1", config=None, foreground=False)
        with patch("builtins.open", unittest.mock.mock_open()):
            with patch("builtins.print"):
                hyprcrd_cli.cmd_start(args)
                self.assertEqual(self.fake_pid_file.read_text(), "54321")

    @patch("os.kill")
    @patch("time.sleep")
    @patch("psutil.pid_exists", side_effect=[True, False])
    @patch("psutil.process_iter", return_value=[])
    def test_08_cmd_stop_running(
        self, mock_iter, mock_pid_exists, mock_sleep, mock_kill
    ):
        self.fake_pid_file.write_text("54321")
        args = MagicMock()
        with patch("builtins.print") as mock_print:
            hyprcrd_cli.cmd_stop(args)
            mock_kill.assert_called_with(54321, signal.SIGTERM)
            mock_print.assert_called()
        self.assertFalse(self.fake_pid_file.exists())

    @patch("os.kill")
    @patch("time.sleep")
    @patch("psutil.pid_exists", side_effect=[True, True])
    @patch("psutil.process_iter")
    def test_09_cmd_stop_lingering_process(
        self, mock_iter, mock_pid_exists, mock_sleep, mock_kill
    ):
        self.fake_pid_file.write_text("54321")
        mock_lingering = MagicMock()
        mock_lingering.info = {"cmdline": ["hyprcrd-portal"], "pid": 9999}
        mock_iter.return_value = [mock_lingering]

        args = MagicMock()
        with patch("builtins.print"):
            hyprcrd_cli.cmd_stop(args)
            # SIGTERM then SIGKILL
            self.assertEqual(mock_kill.call_count, 2)
            mock_lingering.terminate.assert_called_once()

    @patch("psutil.pid_exists", return_value=False)
    @patch("psutil.process_iter", return_value=[])
    def test_10_cmd_status_stopped(self, mock_iter, mock_pid_exists):
        args = MagicMock()
        with patch("builtins.print") as mock_print:
            hyprcrd_cli.cmd_status(args)
            mock_print.assert_called()

    @patch("psutil.pid_exists", return_value=True)
    @patch("psutil.process_iter")
    def test_11_cmd_status_running_with_host_config(self, mock_iter, mock_pid_exists):
        self.fake_pid_file.write_text("11223")
        mock_portal = MagicMock()
        mock_portal.info = {"name": "hyprcrd-portal", "pid": 11224}
        mock_iter.return_value = [mock_portal]

        # Add valid enrolled config
        sample_host_cfg = self.fake_config_dir / "host#12345.json"
        sample_host_cfg.write_text(
            json.dumps({"host_name": "TestHost", "host_id": "test-id"})
        )

        args = MagicMock()
        with patch("builtins.print") as mock_print:
            hyprcrd_cli.cmd_status(args)
            mock_print.assert_called()

    @patch("sys.exit")
    def test_12_main_dispatcher(self, mock_exit):
        mock_exit.side_effect = SystemExit(0)
        # Test help when no command given
        with patch.object(sys, "argv", ["hyprcrd"]):
            with self.assertRaises(SystemExit):
                hyprcrd_cli.main()
            mock_exit.assert_called_with(0)

        # Test command dispatch to doctor
        with patch.object(sys, "argv", ["hyprcrd", "doctor"]):
            with patch.object(hyprcrd_cli, "cmd_doctor") as mock_doc:
                hyprcrd_cli.main()
                mock_doc.assert_called_once()

        # Test command dispatch to stop
        with patch.object(sys, "argv", ["hyprcrd", "stop"]):
            with patch.object(hyprcrd_cli, "cmd_stop") as mock_stop:
                hyprcrd_cli.main()
                mock_stop.assert_called_once()

    @patch("sys.exit")
    def test_13_cmd_test_missing_script(self, mock_exit):
        mock_exit.side_effect = SystemExit(1)
        args = MagicMock()
        with patch.object(Path, "exists", return_value=False):
            with patch("builtins.print"):
                with self.assertRaises(SystemExit):
                    hyprcrd_cli.cmd_test(args)

    @patch("subprocess.Popen")
    @patch("psutil.pid_exists", return_value=False)
    def test_14_cmd_start_corrupt_pid(self, mock_pid_exists, mock_popen):
        self.fake_pid_file.write_text("not-a-number")
        mock_proc = MagicMock(pid=9911)
        mock_popen.return_value = mock_proc
        args = MagicMock(display="wayland-1", config=None, foreground=False)
        with patch("builtins.open", unittest.mock.mock_open()):
            with patch("builtins.print"):
                hyprcrd_cli.cmd_start(args)

    def test_15_cmd_stop_corrupt_pid_and_access_denied(self):
        import psutil

        self.fake_pid_file.write_text("not-a-number")
        args = MagicMock()
        mock_proc = MagicMock()
        mock_proc.info = {"cmdline": ["hyprcrd-portal"], "pid": 123}
        mock_proc.terminate.side_effect = psutil.AccessDenied()
        with patch("psutil.process_iter", return_value=[mock_proc]):
            with patch("builtins.print") as mock_print:
                hyprcrd_cli.cmd_stop(args)
                mock_print.assert_called()

    def test_16_cmd_status_corrupt_pid_and_json(self):
        self.fake_pid_file.write_text("not-a-number")
        bad_cfg = self.fake_config_dir / "host#bad.json"
        bad_cfg.write_text("{invalid json")
        args = MagicMock()
        with patch("psutil.process_iter", return_value=[]):
            with patch("builtins.print") as mock_print:
                hyprcrd_cli.cmd_status(args)
                mock_print.assert_called()

    def test_17_main_restart(self):
        with patch.object(sys, "argv", ["hyprcrd", "restart"]):
            with patch.object(hyprcrd_cli, "cmd_stop") as mock_stop:
                with patch.object(hyprcrd_cli, "cmd_start") as mock_start:
                    hyprcrd_cli.main()
                    mock_stop.assert_called_once()
                    mock_start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
