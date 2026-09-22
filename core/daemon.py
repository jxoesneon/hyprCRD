#!/usr/bin/env python3
"""
hyprCRD Daemon - Native Chrome Remote Desktop Host for Hyprland
Provides 1:1 parity with official Google Chrome Remote Desktop while
natively attaching to the Hyprland Wayland compositor using PipeWire
ScreenCast and the hyprcrd-portal RemoteDesktop input bridge.
"""

import os
import sys
import glob
import json
import time
import signal
import logging
import argparse
import subprocess
import threading

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BIN_DIR = os.path.join(BASE_DIR, "bin")
HOST_BINARY = os.path.join(BIN_DIR, "chrome-remote-desktop-host")
PORTAL_BINARY = os.path.join(BIN_DIR, "hyprcrd-portal")
PAM_SHIM = os.path.join(BIN_DIR, "pam_shim.so")
DEFAULT_CONFIG_DIR = os.path.expanduser("~/.config/chrome-remote-desktop")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [hyprCRD] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

class HyprCRDDaemon:
    def __init__(self, wayland_display=None, config_path=None, audio_pipe=None):
        self.wayland_display = wayland_display or os.environ.get("WAYLAND_DISPLAY", "wayland-1")
        self.config_path = config_path or self._find_host_config()
        self.audio_pipe = audio_pipe
        self.host_proc = None
        self.portal_proc = None
        self.running = False
        self.host_ready = False

    def _find_host_config(self):
        configs = glob.glob(os.path.join(DEFAULT_CONFIG_DIR, "host#*.json"))
        if not configs:
            raise FileNotFoundError(
                f"No host configuration found in {DEFAULT_CONFIG_DIR}. "
                "Run 'hyprcrd register' or enroll this machine first."
            )
        # Use latest modified config
        configs.sort(key=os.path.getmtime, reverse=True)
        return configs[0]

    def _load_host_config(self):
        logging.info(f"Loading host configuration: {self.config_path}")
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def start_portal_if_needed(self):
        # Check if portal is already running on session bus
        try:
            check = subprocess.run(
                ["busctl", "--user", "status", "org.freedesktop.impl.portal.desktop.hypr-remote"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if check.returncode == 0:
                logging.info("hyprcrd-portal is already active on D-Bus.")
                return
        except Exception:
            pass

        logging.info(f"Starting hyprcrd-portal for Wayland display '{self.wayland_display}'...")
        portal_env = os.environ.copy()
        portal_env["WAYLAND_DISPLAY"] = self.wayland_display
        portal_env["XDG_CURRENT_DESKTOP"] = "Hyprland"

        self.portal_proc = subprocess.Popen(
            [PORTAL_BINARY],
            env=portal_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        def log_portal():
            for line in self.portal_proc.stdout:
                line = line.strip()
                if line:
                    logging.debug(f"[portal] {line}")

        t = threading.Thread(target=log_portal, daemon=True)
        t.start()
        time.sleep(0.5)

        if self.portal_proc.poll() is not None:
            logging.warning("Portal process exited early; verifying D-Bus status.")
        else:
            logging.info("hyprcrd-portal initialized successfully.")

    def run(self):
        self.running = True
        config_data = self._load_host_config()
        host_name = config_data.get("host_name", "Unknown")
        host_id = config_data.get("host_id", "Unknown")
        logging.info(f"Starting hyprCRD host '{host_name}' (ID: {host_id})")
        logging.info(f"Targeting Hyprland Wayland display: {self.wayland_display}")

        self.start_portal_if_needed()

        # Build environment for chrome-remote-desktop-host
        host_env = os.environ.copy()
        current_ld_path = host_env.get("LD_LIBRARY_PATH", "")
        host_env["LD_LIBRARY_PATH"] = f"{BIN_DIR}:{current_ld_path}".rstrip(":")
        
        # Inject PAM shim
        if os.path.exists(PAM_SHIM):
            current_preload = host_env.get("LD_PRELOAD", "")
            host_env["LD_PRELOAD"] = f"{PAM_SHIM} {current_preload}".strip()
            logging.info(f"Injected PAM shim: {PAM_SHIM}")

        host_env["WAYLAND_DISPLAY"] = self.wayland_display
        host_env["XDG_SESSION_TYPE"] = "wayland"
        host_env["XDG_CURRENT_DESKTOP"] = "Hyprland"
        host_env["CHROME_REMOTE_DESKTOP_SESSION"] = "1"
        host_env["CHROME_REMOTE_DESKTOP_USE_WAYLAND"] = "1"

        args = [HOST_BINARY, "--host-config=-", "--signal-parent"]
        if self.audio_pipe:
            args.append(f"--audio-pipe-name={self.audio_pipe}")

        # Setup SIGUSR1 handler to catch readiness signal from host
        def sigusr1_handler(signum, frame):
            logging.info("🎉 Host received SIGUSR1: Ready to receive connections!")
            self.host_ready = True

        signal.signal(signal.SIGUSR1, sigusr1_handler)

        logging.info(f"Launching host binary: {HOST_BINARY}")
        self.host_proc = subprocess.Popen(
            args,
            env=host_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        # Pipe config to stdin
        try:
            self.host_proc.stdin.write(json.dumps(config_data))
            self.host_proc.stdin.close()
        except Exception as e:
            logging.error(f"Failed to write host config to stdin: {e}")

        # Stream output
        def stream_host_output():
            for line in self.host_proc.stdout:
                line = line.strip()
                if line:
                    logging.info(f"[host] {line}")

        t_out = threading.Thread(target=stream_host_output, daemon=True)
        t_out.start()

        # Supervision loop
        try:
            while self.running:
                ret = self.host_proc.poll()
                if ret is not None:
                    logging.warning(f"Host process exited with returncode {ret}")
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Interrupted by user.")
        finally:
            self.stop()

    def stop(self):
        self.running = False
        logging.info("Stopping hyprCRD host daemon...")
        if self.host_proc and self.host_proc.poll() is None:
            try:
                self.host_proc.terminate()
                self.host_proc.wait(timeout=3)
            except Exception:
                self.host_proc.kill()
        if self.portal_proc and self.portal_proc.poll() is None:
            try:
                self.portal_proc.terminate()
                self.portal_proc.wait(timeout=2)
            except Exception:
                self.portal_proc.kill()
        logging.info("hyprCRD host daemon stopped cleanly.")

def main():
    parser = argparse.ArgumentParser(description="hyprCRD - Native Chrome Remote Desktop for Hyprland")
    parser.add_argument("--display", help="Target Wayland display (e.g. wayland-1 or wayland-2)")
    parser.add_argument("--config", help="Path to host config JSON")
    parser.add_argument("--audio-pipe", help="Path to PipeWire audio pipe")
    args = parser.parse_args()

    daemon = HyprCRDDaemon(
        wayland_display=args.display,
        config_path=args.config,
        audio_pipe=args.audio_pipe
    )

    def handle_shutdown(signum, frame):
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    daemon.run()

if __name__ == "__main__":
    main()
