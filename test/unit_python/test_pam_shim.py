#!/usr/bin/env python3
"""
Unit tests for core/pam_shim.so
Verifies PAM authentication bypass, PipeWire stream protection,
and D-Bus ScreenCast parameter rewriting.
"""

import os
import ctypes
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
SHIM_PATH = os.path.join(BASE_DIR, "bin", "pam_shim.so")


class TestPamShim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = ctypes.CDLL(SHIM_PATH)

    def test_01_pam_lifecycle(self):
        """Test pam_start, pam_acct_mgmt, and pam_end interception."""

        # struct pam_conv definition
        class PamConv(ctypes.Structure):
            _fields_ = [("conv", ctypes.c_void_p), ("appdata_ptr", ctypes.c_void_p)]

        conv = PamConv(None, None)
        handle = ctypes.c_void_p()

        # 1. pam_start for chrome-remote-desktop
        res = self.lib.pam_start(
            b"chrome-remote-desktop",
            b"eduardo",
            ctypes.byref(conv),
            ctypes.byref(handle),
        )
        self.assertEqual(res, 0, "pam_start should return PAM_SUCCESS (0)")
        self.assertIsNotNone(handle.value, "handle should be populated")

        # 2. pam_acct_mgmt should return PAM_SUCCESS for CRD handle
        res = self.lib.pam_acct_mgmt(handle, 0)
        self.assertEqual(
            res, 0, "pam_acct_mgmt should bypass and return PAM_SUCCESS (0)"
        )

        # 3. pam_end clean teardown
        res = self.lib.pam_end(handle, 0)
        self.assertEqual(res, 0, "pam_end should clean up and return PAM_SUCCESS (0)")

    def test_02_pw_stream_update_params_null_safe(self):
        """Test pw_stream_update_params safety with NULL stream pointer."""
        import errno

        res = self.lib.pw_stream_update_params(None, None, 0)
        self.assertEqual(res, -errno.EINVAL, "NULL stream should return -EINVAL (-22)")

    def test_03_dlsym_interception(self):
        """Test dlsym interception of pw_stream_update_params."""
        dlsym_fn = self.lib.dlsym
        dlsym_fn.restype = ctypes.c_void_p
        dlsym_fn.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

        sym = dlsym_fn(None, b"pw_stream_update_params")
        self.assertIsNotNone(
            sym, "dlsym should return pointer for pw_stream_update_params"
        )


if __name__ == "__main__":
    unittest.main()
