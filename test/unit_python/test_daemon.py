#!/usr/bin/env python3
"""
Unit tests for core/daemon.py
Verifies configuration detection, environment configuration, process control,
and argument parsing for HyprCRDDaemon.
"""

import os
import re
import sys
import json
import time
import signal
import tempfile
import unittest
import subprocess
from contextlib import contextmanager
from unittest.mock import patch, MagicMock, mock_open

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
            "private_key": "MOCK_DEVELOPMENT_KEY_PLACEHOLDER",
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

    @patch("subprocess.run")
    def test_15_wake_display(self, mock_subproc):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        daemon._wake_display()
        self.assertTrue(mock_subproc.called)
        dispatched_cmds = [call.args[0] for call in mock_subproc.call_args_list]
        # DPMS on must be dispatched via the Lua table form
        self.assertIn(
            ["hyprctl", "dispatch", 'hl.dsp.dpms({ action = "on" })'],
            dispatched_cmds,
        )
        # The string form hl.dsp.dpms("...") is silently ignored by Lua configs
        flat_args = [arg for cmd in dispatched_cmds for arg in cmd]
        self.assertFalse(
            any('hl.dsp.dpms("' in arg for arg in flat_args),
            "String-form hl.dsp.dpms dispatch must never be used",
        )

    @patch.object(HyprCRDDaemon, "_wake_display")
    @patch.object(HyprCRDDaemon, "_start_display_keepalive")
    @patch.object(HyprCRDDaemon, "_stop_display_keepalive")
    @patch.object(HyprCRDDaemon, "_check_restore_lid_sleep")
    def test_16_client_connection_lifecycle(
        self, mock_lid, mock_stop_ka, mock_start_ka, mock_wake
    ):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        self.assertEqual(daemon.active_clients, 0)

        # Connect client 1
        daemon._on_client_connected("Client connected: test@example.com")
        self.assertEqual(daemon.active_clients, 1)
        mock_wake.assert_called_once()
        mock_start_ka.assert_called_once()

        # Disconnect client 1
        daemon._on_client_disconnected("Client disconnected: test@example.com")
        self.assertEqual(daemon.active_clients, 0)
        mock_stop_ka.assert_called_once()
        mock_lid.assert_called_once()

    @contextmanager
    def _hypr_instances(self, instances, alive_pids=(), foreign_pids=()):
        """Mocks a /run/user/<uid>/hypr tree.

        instances: {name: (pid, mtime)}; alive_pids respond to os.kill(pid, 0);
        foreign_pids raise PermissionError (alive but owned by another user);
        any other pid raises ProcessLookupError.
        """

        def fake_open(path, *args, **kwargs):
            name = os.path.basename(os.path.dirname(path))
            if name in instances and os.path.basename(path) == "hyprland.lock":
                return mock_open(read_data=f"{instances[name][0]}\n")()
            raise FileNotFoundError(path)

        def fake_kill(pid, sig):
            if pid in alive_pids:
                return
            if pid in foreign_pids:
                raise PermissionError(pid)
            raise ProcessLookupError(pid)

        with patch("os.path.isdir", return_value=True), patch(
            "os.listdir", return_value=list(instances)
        ), patch(
            "os.path.getmtime",
            side_effect=lambda p: instances[os.path.basename(p)][1],
        ), patch(
            "builtins.open", side_effect=fake_open
        ), patch(
            "os.kill", side_effect=fake_kill
        ):
            yield

    def test_17_get_hypr_env(self):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        with self._hypr_instances({"sig123": (4242, 100)}, alive_pids={4242}):
            with patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "sig123"}):
                env = daemon._get_hypr_env()
        self.assertEqual(env.get("HYPRLAND_INSTANCE_SIGNATURE"), "sig123")

    def test_29_get_hypr_env_picks_live_over_dead_newest(self):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        instances = {
            "sig-dead": (2222, 200),  # newest dir but dead instance
            "sig-live": (1111, 100),
        }
        with self._hypr_instances(instances, alive_pids={1111}):
            with patch.dict(os.environ):
                os.environ.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
                env = daemon._get_hypr_env()
        self.assertEqual(env.get("HYPRLAND_INSTANCE_SIGNATURE"), "sig-live")

    def test_30_get_hypr_env_dead_preset_replaced(self):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        instances = {
            "sig-dead": (2222, 200),
            "sig-live": (1111, 100),
        }
        with self._hypr_instances(instances, alive_pids={1111}):
            with patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "sig-dead"}):
                env = daemon._get_hypr_env()
        self.assertEqual(env.get("HYPRLAND_INSTANCE_SIGNATURE"), "sig-live")

    def test_31_get_hypr_env_none_alive(self):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        with self._hypr_instances({"sig-dead": (2222, 200)}):
            with patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "sig-dead"}):
                env = daemon._get_hypr_env()
        self.assertNotIn("HYPRLAND_INSTANCE_SIGNATURE", env)

    def test_32_get_hypr_env_permission_counts_alive(self):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        with self._hypr_instances({"sig123": (4242, 100)}, foreign_pids={4242}):
            with patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "sig123"}):
                env = daemon._get_hypr_env()
        self.assertEqual(env.get("HYPRLAND_INSTANCE_SIGNATURE"), "sig123")

    @patch("subprocess.run")
    def test_18_dispatch_dpms_lua_ok_no_fallback(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout="ok\n")
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        daemon._dispatch_dpms("on")
        mock_subproc.assert_called_once()
        cmd = mock_subproc.call_args.args[0]
        self.assertEqual(cmd, ["hyprctl", "dispatch", 'hl.dsp.dpms({ action = "on" })'])

    @patch("subprocess.run")
    def test_19_dispatch_dpms_legacy_fallback(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout="Invalid dispatcher")
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        daemon._dispatch_dpms("on")
        self.assertEqual(mock_subproc.call_count, 2)
        fallback_cmd = mock_subproc.call_args_list[1].args[0]
        self.assertEqual(fallback_cmd, ["hyprctl", "dispatch", "dpms", "on"])

    @patch("subprocess.run")
    def test_20_dispatch_dpms_off_with_monitor(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout="err")
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        daemon._dispatch_dpms("off", "eDP-1")
        self.assertEqual(mock_subproc.call_count, 2)
        lua_cmd = mock_subproc.call_args_list[0].args[0]
        self.assertEqual(
            lua_cmd,
            [
                "hyprctl",
                "dispatch",
                'hl.dsp.dpms({ action = "off", monitor = "eDP-1" })',
            ],
        )
        fallback_cmd = mock_subproc.call_args_list[1].args[0]
        self.assertEqual(fallback_cmd, ["hyprctl", "dispatch", "dpms", "off", "eDP-1"])

    @patch.object(HyprCRDDaemon, "_dispatch_dpms")
    def test_21_lid_closed_restores_dpms_off(self, mock_dpms):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        with patch(
            "glob.glob", return_value=["/proc/acpi/button/lid/LID0/state"]
        ), patch("builtins.open", mock_open(read_data="state:          closed")):
            daemon._check_restore_lid_sleep()
        mock_dpms.assert_called_once_with("off", "eDP-1")

    @patch.object(HyprCRDDaemon, "_dispatch_dpms")
    @patch("time.sleep")
    def test_22_keepalive_dispatches_dpms_on(self, mock_sleep, mock_dpms):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        daemon.running = True
        daemon.active_clients = 1

        def stop_after_one_sleep(_seconds):
            daemon.keepalive_running = False

        mock_sleep.side_effect = stop_after_one_sleep
        daemon._start_display_keepalive()
        daemon.keepalive_thread.join(timeout=5)
        mock_dpms.assert_called_once_with("on")

    @patch("subprocess.run")
    def test_24_dispatch_dpms_exception(self, mock_subproc):
        mock_subproc.side_effect = Exception("hyprctl unavailable")
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        daemon._dispatch_dpms("on")
        mock_subproc.assert_called_once()

    @patch.object(HyprCRDDaemon, "_dispatch_dpms", side_effect=Exception("boom"))
    def test_25_wake_display_dispatch_exception(self, mock_dpms):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        daemon._wake_display()
        mock_dpms.assert_called_once_with("on")

    def test_26_keepalive_already_running(self):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        daemon.keepalive_running = True
        daemon._start_display_keepalive()
        self.assertIsNone(daemon.keepalive_thread)

    @patch.object(HyprCRDDaemon, "_dispatch_dpms")
    def test_27_lid_state_read_error(self, mock_dpms):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        with patch(
            "glob.glob", return_value=["/proc/acpi/button/lid/LID0/state"]
        ), patch("builtins.open", side_effect=OSError("no lid")):
            daemon._check_restore_lid_sleep()
        mock_dpms.assert_not_called()

    def test_28_no_string_form_dpms_dispatch_in_repo(self):
        # hl.dsp.dpms("on") is silently ignored under a Lua config; the table
        # form hl.dsp.dpms({ action = "on" }) is required everywhere.
        pattern = re.compile(r"hl\.dsp\.dpms\(\s*[\"']")
        scan_dirs = ("bin/", "core/", "scripts/", "systemd/", "config/")
        try:
            tracked = subprocess.check_output(
                ["git", "ls-files"], cwd=BASE_DIR, text=True
            ).splitlines()
        except (OSError, subprocess.CalledProcessError):
            # Environments where git refuses the checkout (e.g. containers
            # running as a different uid than the files' owner): scan the
            # source directories directly.
            tracked = []
            for scan_dir in scan_dirs:
                for root, _, files in os.walk(os.path.join(BASE_DIR, scan_dir)):
                    tracked += [
                        os.path.relpath(os.path.join(root, name), BASE_DIR)
                        for name in files
                    ]
        for rel in tracked:
            if not rel.startswith(scan_dirs):
                continue
            path = os.path.join(BASE_DIR, rel)
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            if data.startswith(b"\x7fELF") or b"\x00" in data:
                continue
            match = pattern.search(data.decode("utf-8", errors="replace"))
            self.assertIsNone(
                match,
                f"{rel} uses string-form hl.dsp.dpms(...) ignored by Lua configs",
            )

    @patch("subprocess.Popen")
    @patch.object(HyprCRDDaemon, "start_portal_if_needed")
    def test_33_run_dispatches_client_events(self, mock_start_portal, mock_popen):
        daemon = HyprCRDDaemon(
            wayland_display="wayland-1", config_path=self.sample_config_path
        )
        mock_host = MagicMock()
        mock_host.stdin = MagicMock()
        mock_host.stdout = [
            "Client connected: a@example.com\n",
            "noise line\n",
            "Client disconnected: a@example.com\n",
        ]
        mock_host.poll.side_effect = [0, 0, 0]
        mock_popen.return_value = mock_host

        with patch.object(daemon, "_on_client_connected") as mock_conn, patch.object(
            daemon, "_on_client_disconnected"
        ) as mock_disc, patch("os.path.exists", return_value=False):
            daemon.run()
            for _ in range(100):
                if mock_conn.called and mock_disc.called:
                    break
                time.sleep(0.01)

        mock_conn.assert_called_once_with("Client connected: a@example.com")
        mock_disc.assert_called_once_with("Client disconnected: a@example.com")

    def test_34_find_component_sibling_libexec(self):
        # A daemon installed under <prefix>/lib/hyprcrd resolves siblings; a
        # checkout layout resolves <prefix>/bin/../lib/hyprcrd as well.
        fake_root = os.path.join(self.temp_dir.name, "prefix")
        libexec = os.path.join(fake_root, "lib", "hyprcrd")
        os.makedirs(libexec)
        os.makedirs(os.path.join(fake_root, "bin"))
        comp = os.path.join(libexec, "test-component-xyz")
        with open(comp, "w", encoding="utf-8") as f:
            f.write("x")

        with patch.object(daemon_mod, "__file__", os.path.join(libexec, "daemon.py")):
            self.assertEqual(
                os.path.normpath(daemon_mod._find_component("test-component-xyz")),
                comp,
            )
        with patch.object(
            daemon_mod, "__file__", os.path.join(fake_root, "bin", "daemon.py")
        ):
            self.assertEqual(
                os.path.normpath(daemon_mod._find_component("test-component-xyz")),
                comp,
            )


if __name__ == "__main__":
    unittest.main()
