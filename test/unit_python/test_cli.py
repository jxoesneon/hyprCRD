#!/usr/bin/env python3
"""
Unit tests for bin/hyprcrd CLI
Verifies doctor check, status reporting, process start/stop, restart,
background daemonization, and CLI argument parsing.
"""

import os
import sys
import json
import signal
import hashlib
import tempfile
import unittest
import subprocess
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

    def test_18_main_version(self):
        with patch.object(sys, "argv", ["hyprcrd", "--version"]):
            with self.assertRaises(SystemExit) as cm:
                hyprcrd_cli.main()
            self.assertEqual(cm.exception.code, 0)

    def test_19_runtime_and_state_dirs(self):
        with patch.dict(
            os.environ,
            {"XDG_RUNTIME_DIR": "/run/test-rt", "XDG_STATE_HOME": "/state-x"},
        ):
            self.assertEqual(hyprcrd_cli.runtime_dir(), Path("/run/test-rt/hyprcrd"))
            self.assertEqual(hyprcrd_cli.state_dir(), Path("/state-x/hyprcrd"))
        # Without XDG vars, fall back to per-user locations — never world-writable /tmp
        with patch.dict(os.environ):
            os.environ.pop("XDG_RUNTIME_DIR", None)
            os.environ.pop("XDG_STATE_HOME", None)
            self.assertEqual(
                hyprcrd_cli.runtime_dir(),
                Path(f"/run/user/{os.getuid()}/hyprcrd"),
            )
            self.assertEqual(
                hyprcrd_cli.state_dir(),
                Path.home() / ".local" / "state" / "hyprcrd",
            )
            self.assertNotIn("/tmp", str(hyprcrd_cli.runtime_dir()))
            self.assertNotIn("/tmp", str(hyprcrd_cli.state_dir()))

    def test_20_find_component_sibling_libexec(self):
        # An installed CLI at <prefix>/bin must find components in
        # <prefix>/lib/hyprcrd without absolute-path fallbacks.
        fake_root = Path(self.temp_dir.name) / "prefix"
        (fake_root / "bin").mkdir(parents=True)
        (fake_root / "lib" / "hyprcrd").mkdir(parents=True)
        comp = fake_root / "lib" / "hyprcrd" / "test-component-xyz"
        comp.write_text("x")
        with patch.object(hyprcrd_cli, "__file__", str(fake_root / "bin" / "hyprcrd")):
            self.assertEqual(hyprcrd_cli.find_component("test-component-xyz"), comp)

    def test_21_find_daemon_sibling_libexec(self):
        fake_root = Path(self.temp_dir.name) / "prefix"
        (fake_root / "bin").mkdir(parents=True)
        (fake_root / "lib" / "hyprcrd").mkdir(parents=True)
        daemon = fake_root / "lib" / "hyprcrd" / "daemon.py"
        daemon.write_text("x")
        with patch.object(
            hyprcrd_cli, "__file__", str(fake_root / "bin" / "hyprcrd")
        ), patch.object(hyprcrd_cli, "CORE_DIR", fake_root / "empty-core"):
            self.assertEqual(hyprcrd_cli.find_daemon(), daemon)

    def test_22_find_crd_version_env(self):
        env_file = Path(self.temp_dir.name) / "crd_version.env"
        env_file.write_text('CRD_VERSION="1.0.0"\n')
        with patch.dict(os.environ, {"HYPRCRD_CRD_VERSION_ENV": str(env_file)}):
            self.assertEqual(hyprcrd_cli.find_crd_version_env(), env_file)
        # Without the override, the repository scripts/crd_version.env resolves
        with patch.dict(os.environ):
            os.environ.pop("HYPRCRD_CRD_VERSION_ENV", None)
            self.assertEqual(
                hyprcrd_cli.find_crd_version_env(),
                BASE_DIR / "scripts" / "crd_version.env",
            )

    def test_23_load_crd_version(self):
        meta = hyprcrd_cli.load_crd_version()
        self.assertEqual(meta["version"], "155.0.8059.19")
        self.assertEqual(
            meta["sha256"],
            "39701c6951b3d9edff08143dccad919468e1866b9897c873141dc4f66baaff72",
        )
        # ${CRD_VERSION} in CRD_DEB_URL must be expanded
        self.assertIn("chrome-remote-desktop_155.0.8059.19_amd64.deb", meta["url"])
        self.assertNotIn("${CRD_VERSION}", meta["url"])
        self.assertTrue(meta["packages_url"].startswith("https://"))

    def test_24_google_component_dir_existing_portal(self):
        portal = Path(self.temp_dir.name) / "lib" / "hyprcrd" / "hyprcrd-portal"
        portal.parent.mkdir(parents=True)
        portal.write_text("x")
        with patch.object(hyprcrd_cli, "find_component", return_value=portal):
            self.assertEqual(hyprcrd_cli._google_component_dir(), portal.parent)

    def test_25_google_component_dir_home_fallback(self):
        fake_home = Path(self.temp_dir.name) / "home"
        missing_portal = fake_home / "unrelated" / "hyprcrd-portal"
        with patch.object(
            hyprcrd_cli, "find_component", return_value=missing_portal
        ), patch.object(Path, "home", return_value=fake_home):
            out = hyprcrd_cli._google_component_dir()
        self.assertEqual(out, fake_home / ".local" / "lib" / "hyprcrd")
        self.assertTrue(out.is_dir())

    def test_26_extract_deb_bsdtar(self):
        work = Path(self.temp_dir.name) / "work-bsdtar"
        work.mkdir()

        def fake_run(cmd, **kwargs):
            if cmd[0] == "bsdtar":
                (work / "data.tar.xz").write_bytes(b"tar")
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_run) as mock_run:
            out = hyprcrd_cli._extract_deb(Path("/tmp/fake.deb"), work)
        self.assertEqual(
            out, work / "data" / "opt" / "google" / "chrome-remote-desktop"
        )
        called = [c.args[0][0] for c in mock_run.call_args_list]
        self.assertEqual(called, ["bsdtar", "tar"])

    def test_27_extract_deb_ar_fallback(self):
        work = Path(self.temp_dir.name) / "work-ar"
        work.mkdir()

        def fake_run(cmd, **kwargs):
            if cmd[0] == "bsdtar":
                raise FileNotFoundError("bsdtar")
            if cmd[0] == "ar":
                (work / "data.tar.xz").write_bytes(b"tar")
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_run) as mock_run:
            out = hyprcrd_cli._extract_deb(Path("/tmp/fake.deb"), work)
        self.assertEqual(
            out, work / "data" / "opt" / "google" / "chrome-remote-desktop"
        )
        called = [c.args[0][0] for c in mock_run.call_args_list]
        self.assertEqual(called, ["bsdtar", "ar", "tar"])

    def test_28_extract_deb_missing_data_tar(self):
        work = Path(self.temp_dir.name) / "work-empty"
        work.mkdir()
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            with self.assertRaises(RuntimeError):
                hyprcrd_cli._extract_deb(Path("/tmp/fake.deb"), work)

    def _install_host_meta(self, deb_bytes):
        return {
            "version": "155.0.8059.19",
            "sha256": hashlib.sha256(deb_bytes).hexdigest(),
            "url": "https://example.invalid/crd.deb",
            "packages_url": "https://example.invalid/Packages",
        }

    def _urlopen_resp(self, payload):
        resp = MagicMock()
        resp.read.return_value = payload
        resp.__enter__.return_value = resp
        return resp

    def test_29_cmd_install_host_success(self):
        deb_bytes = b"fake-deb-payload"
        meta = self._install_host_meta(deb_bytes)
        target = Path(self.temp_dir.name) / "target"
        # Pre-existing stale locales exercise the rmtree + copytree path
        (target / "remoting_locales").mkdir(parents=True)
        (target / "remoting_locales" / "stale.pak").write_bytes(b"stale")
        deb_root = Path(self.temp_dir.name) / "deb-root"
        deb_root.mkdir()
        for name in (
            "chrome-remote-desktop-host",
            "crashpad-handler",
            "native-messaging-host",
            "start-host",
        ):
            (deb_root / name).write_bytes(b"bin")
        (deb_root / "libremoting_core.so").write_bytes(b"lib")
        (deb_root / "icudtl.dat").write_bytes(b"icu")
        (deb_root / "remoting_locales").mkdir()
        (deb_root / "remoting_locales" / "en.pak").write_bytes(b"pak")
        # A live PID file triggers the "restart to use the new host" hint
        self.fake_pid_file.write_text("4321")

        args = MagicMock()
        with patch.object(
            hyprcrd_cli, "load_crd_version", return_value=meta
        ), patch.object(
            hyprcrd_cli, "_google_component_dir", return_value=target
        ), patch.object(
            hyprcrd_cli, "_extract_deb", return_value=deb_root
        ), patch(
            "urllib.request.urlopen", return_value=self._urlopen_resp(deb_bytes)
        ), patch(
            "psutil.pid_exists", return_value=True
        ), patch(
            "builtins.print"
        ) as mock_print:
            hyprcrd_cli.cmd_install_host(args)

        for name in (
            "chrome-remote-desktop-host",
            "crashpad-handler",
            "native-messaging-host",
            "start-host",
        ):
            self.assertEqual((target / name).read_bytes(), b"bin")
            self.assertEqual((target / name).stat().st_mode & 0o777, 0o755)
        self.assertEqual((target / "libremoting_core.so").read_bytes(), b"lib")
        self.assertEqual((target / "libremoting_core.so").stat().st_mode & 0o777, 0o644)
        self.assertEqual((target / "remoting_locales" / "en.pak").read_bytes(), b"pak")
        self.assertFalse((target / "remoting_locales" / "stale.pak").exists())
        out = " ".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
        self.assertIn("Checksum verified", out)
        self.assertIn("restart", out)

    def test_30_cmd_install_host_sha_mismatch(self):
        meta = self._install_host_meta(b"expected-payload")
        target = Path(self.temp_dir.name) / "target"

        args = MagicMock()
        with patch.object(
            hyprcrd_cli, "load_crd_version", return_value=meta
        ), patch.object(
            hyprcrd_cli, "_google_component_dir", return_value=target
        ), patch.object(
            hyprcrd_cli, "_extract_deb"
        ) as mock_extract, patch(
            "urllib.request.urlopen",
            return_value=self._urlopen_resp(b"tampered-payload"),
        ), patch(
            "builtins.print"
        ):
            with self.assertRaises(SystemExit) as cm:
                hyprcrd_cli.cmd_install_host(args)
        self.assertEqual(cm.exception.code, 1)
        mock_extract.assert_not_called()
        self.assertFalse(target.exists())

    def test_31_cmd_install_host_download_failure(self):
        meta = self._install_host_meta(b"payload")
        target = Path(self.temp_dir.name) / "target"
        args = MagicMock()
        with patch.object(
            hyprcrd_cli, "load_crd_version", return_value=meta
        ), patch.object(
            hyprcrd_cli, "_google_component_dir", return_value=target
        ), patch(
            "urllib.request.urlopen", side_effect=OSError("no network")
        ), patch(
            "builtins.print"
        ):
            with self.assertRaises(SystemExit) as cm:
                hyprcrd_cli.cmd_install_host(args)
        self.assertEqual(cm.exception.code, 1)

    def test_32_cmd_install_host_extract_failure(self):
        deb_bytes = b"fake-deb-payload"
        meta = self._install_host_meta(deb_bytes)
        target = Path(self.temp_dir.name) / "target"

        args = MagicMock()
        with patch.object(
            hyprcrd_cli, "load_crd_version", return_value=meta
        ), patch.object(
            hyprcrd_cli, "_google_component_dir", return_value=target
        ), patch.object(
            hyprcrd_cli,
            "_extract_deb",
            side_effect=subprocess.CalledProcessError(1, "ar"),
        ), patch(
            "urllib.request.urlopen", return_value=self._urlopen_resp(deb_bytes)
        ), patch(
            "builtins.print"
        ):
            with self.assertRaises(SystemExit) as cm:
                hyprcrd_cli.cmd_install_host(args)
        self.assertEqual(cm.exception.code, 1)

    def test_32b_cmd_install_host_permission_denied(self):
        deb_bytes = b"fake-deb-payload"
        meta = self._install_host_meta(deb_bytes)
        target = Path(self.temp_dir.name) / "target"
        deb_root = Path(self.temp_dir.name) / "deb-root"
        deb_root.mkdir()

        args = MagicMock()
        with patch.object(
            hyprcrd_cli, "load_crd_version", return_value=meta
        ), patch.object(
            hyprcrd_cli, "_google_component_dir", return_value=target
        ), patch.object(
            hyprcrd_cli, "_extract_deb", return_value=deb_root
        ), patch.object(
            Path, "mkdir", side_effect=PermissionError("denied")
        ), patch(
            "urllib.request.urlopen", return_value=self._urlopen_resp(deb_bytes)
        ), patch(
            "builtins.print"
        ):
            with self.assertRaises(SystemExit) as cm:
                hyprcrd_cli.cmd_install_host(args)
        self.assertEqual(cm.exception.code, 1)

    def test_33_cmd_install_host_missing_env(self):
        args = MagicMock()
        with patch.object(
            hyprcrd_cli, "find_crd_version_env", return_value=None
        ), patch("builtins.print"):
            with self.assertRaises(SystemExit) as cm:
                hyprcrd_cli.cmd_install_host(args)
        self.assertEqual(cm.exception.code, 1)

    def _packages_index(self, versions):
        lines = []
        for v in versions:
            lines += ["Package: chrome-remote-desktop", f"Version: {v}", ""]
        return "\n".join(lines)

    def _run_check_host_update(self, index, version="155.0.8059.19"):
        meta = {
            "version": version,
            "sha256": "0" * 64,
            "url": "https://example.invalid/crd.deb",
            "packages_url": "https://example.invalid/Packages",
        }
        resp = MagicMock()
        resp.read.return_value = index.encode()
        resp.__enter__.return_value = resp
        args = MagicMock()
        with patch.object(hyprcrd_cli, "load_crd_version", return_value=meta), patch(
            "urllib.request.urlopen", return_value=resp
        ), patch("builtins.print") as mock_print:
            hyprcrd_cli.cmd_check_host_update(args)
        return " ".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)

    def test_34_cmd_check_host_update_latest(self):
        index = self._packages_index(["155.0.8059.18", "155.0.8059.19"])
        out = self._run_check_host_update(index)
        self.assertIn("latest upstream release", out)

    def test_35_cmd_check_host_update_newer(self):
        index = self._packages_index(["155.0.8059.19", "156.0.1.0"])
        out = self._run_check_host_update(index)
        self.assertIn("newer upstream release", out)

    def test_36_cmd_check_host_update_no_versions(self):
        index = "Package: other-package\nVersion: 1.0\n"
        meta = {
            "version": "155.0.8059.19",
            "sha256": "0" * 64,
            "url": "https://example.invalid/crd.deb",
            "packages_url": "https://example.invalid/Packages",
        }
        resp = MagicMock()
        resp.read.return_value = index.encode()
        resp.__enter__.return_value = resp
        args = MagicMock()
        with patch.object(hyprcrd_cli, "load_crd_version", return_value=meta), patch(
            "urllib.request.urlopen", return_value=resp
        ), patch("builtins.print"):
            with self.assertRaises(SystemExit) as cm:
                hyprcrd_cli.cmd_check_host_update(args)
        self.assertEqual(cm.exception.code, 1)

    def test_37_cmd_check_host_update_fetch_error(self):
        meta = {
            "version": "155.0.8059.19",
            "sha256": "0" * 64,
            "url": "https://example.invalid/crd.deb",
            "packages_url": "https://example.invalid/Packages",
        }
        args = MagicMock()
        with patch.object(hyprcrd_cli, "load_crd_version", return_value=meta), patch(
            "urllib.request.urlopen", side_effect=OSError("no network")
        ), patch("builtins.print"):
            with self.assertRaises(SystemExit) as cm:
                hyprcrd_cli.cmd_check_host_update(args)
        self.assertEqual(cm.exception.code, 1)

    def test_38_find_component_user_lib(self):
        # A component in ~/.local/lib/hyprcrd must be found before the
        # absolute /usr fallbacks.
        fake_home = Path(self.temp_dir.name) / "home"
        comp = fake_home / ".local" / "lib" / "hyprcrd" / "test-component-xyz"
        comp.parent.mkdir(parents=True)
        comp.write_text("x")
        fake_root = Path(self.temp_dir.name) / "prefix"
        (fake_root / "bin").mkdir(parents=True)
        with patch.dict(os.environ):
            os.environ.pop("HYPRCRD_TEST_COMPONENT_XYZ", None)
            with patch.object(
                hyprcrd_cli, "__file__", str(fake_root / "bin" / "hyprcrd")
            ), patch.object(hyprcrd_cli, "BIN_DIR", fake_root / "bin"), patch.object(
                Path, "home", return_value=fake_home
            ):
                self.assertEqual(hyprcrd_cli.find_component("test-component-xyz"), comp)

    def test_39_main_dispatch_host_commands(self):
        with patch.object(sys, "argv", ["hyprcrd", "install-host"]):
            with patch.object(hyprcrd_cli, "cmd_install_host") as mock_install:
                hyprcrd_cli.main()
                mock_install.assert_called_once()
        with patch.object(sys, "argv", ["hyprcrd", "check-host-update"]):
            with patch.object(hyprcrd_cli, "cmd_check_host_update") as mock_check:
                hyprcrd_cli.main()
                mock_check.assert_called_once()

    def test_40_find_component_env_and_fallback(self):
        comp = Path(self.temp_dir.name) / "env-component"
        comp.write_text("x")
        with patch.dict(os.environ, {"HYPRCRD_ENV_COMPONENT": str(comp)}):
            self.assertEqual(hyprcrd_cli.find_component("env-component"), comp)
        # Nothing resolves -> default BIN_DIR candidate
        with patch.dict(os.environ):
            os.environ.pop("HYPRCRD_NONEXISTENT_XYZ", None)
            self.assertEqual(
                hyprcrd_cli.find_component("nonexistent-xyz"),
                hyprcrd_cli.BIN_DIR / "nonexistent-xyz",
            )

    def test_41_find_crd_version_env_none(self):
        with patch.object(Path, "exists", return_value=False):
            self.assertIsNone(hyprcrd_cli.find_crd_version_env())

    def test_42_find_daemon_fallback(self):
        fake_core = Path(self.temp_dir.name) / "empty-core"
        with patch.object(hyprcrd_cli, "CORE_DIR", fake_core), patch.object(
            Path, "exists", return_value=False
        ):
            self.assertEqual(hyprcrd_cli.find_daemon(), fake_core / "daemon.py")

    def test_43_cmd_install_host_corrupt_pid(self):
        deb_bytes = b"fake-deb-payload"
        meta = self._install_host_meta(deb_bytes)
        target = Path(self.temp_dir.name) / "target"
        deb_root = Path(self.temp_dir.name) / "deb-root"
        deb_root.mkdir()
        # A corrupt PID file is ignored by the post-install restart hint
        self.fake_pid_file.write_text("not-a-number")
        args = MagicMock()
        with patch.object(
            hyprcrd_cli, "load_crd_version", return_value=meta
        ), patch.object(
            hyprcrd_cli, "_google_component_dir", return_value=target
        ), patch.object(
            hyprcrd_cli, "_extract_deb", return_value=deb_root
        ), patch(
            "urllib.request.urlopen", return_value=self._urlopen_resp(deb_bytes)
        ), patch(
            "builtins.print"
        ):
            hyprcrd_cli.cmd_install_host(args)

    def test_44_cmd_stop_pid_unlink_failure(self):
        mock_pid = MagicMock()
        mock_pid.exists.return_value = True
        mock_pid.read_text.return_value = "not-a-number"
        mock_pid.unlink.side_effect = OSError("busy")
        args = MagicMock()
        with patch.object(hyprcrd_cli, "PID_FILE", mock_pid), patch(
            "psutil.process_iter", return_value=[]
        ), patch("builtins.print") as mock_print:
            hyprcrd_cli.cmd_stop(args)
            mock_print.assert_called()

    def test_45_cmd_status_daemon_via_process_list(self):
        mock_proc = MagicMock()
        mock_proc.info = {
            "cmdline": ["python3", str(BASE_DIR / "core" / "daemon.py")],
            "pid": 777,
            "name": "python3",
        }
        args = MagicMock()
        with patch("psutil.pid_exists", return_value=False), patch(
            "psutil.process_iter", return_value=[mock_proc]
        ), patch("builtins.print") as mock_print:
            hyprcrd_cli.cmd_status(args)
            mock_print.assert_called()


if __name__ == "__main__":
    unittest.main()
