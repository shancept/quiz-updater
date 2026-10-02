from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from unittest import mock

from quiz_backend import drive
from quiz_backend.errors import BackendError

from .helpers import TEST_EMAIL, service_account_json


class InstalledKeyTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.support_dir = os.path.join(tmp.name, "Application Support", "QuizUpdater")
        patcher = mock.patch.object(drive, "SUPPORT_DIR", self.support_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.source = os.path.join(tmp.name, "downloaded-key.json")
        self._write(self.source, service_account_json())

    @staticmethod
    def _write(path: str, data: dict) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def test_key_lives_in_application_support(self):
        self.assertTrue(drive.key_path().startswith(self.support_dir))

    def test_default_support_dir_is_application_support_quizupdater(self):
        self.assertTrue(drive.DEFAULT_SUPPORT_DIR.endswith("Library/Application Support/QuizUpdater"))

    def test_not_connected_without_key(self):
        self.assertFalse(drive.is_connected())
        with self.assertRaises(BackendError) as ctx:
            drive.load_installed_key()
        self.assertEqual(ctx.exception.code, "DRIVE_NOT_CONNECTED")
        self.assertIn("Подключить Google Drive", ctx.exception.message)

    def test_install_copies_key_with_private_permissions(self):
        drive.install_key(self.source)

        self.assertTrue(drive.is_connected())
        self.assertEqual(drive.load_installed_key().client_email, TEST_EMAIL)
        self.assertEqual(stat.S_IMODE(os.stat(drive.key_path()).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.support_dir).st_mode), 0o700)
        with open(self.source, "rb") as src, open(drive.key_path(), "rb") as dst:
            self.assertEqual(src.read(), dst.read())

    def test_install_replaces_previous_key(self):
        drive.install_key(self.source)
        self._write(self.source, service_account_json(email="other@test-project.iam.gserviceaccount.com"))
        drive.install_key(self.source)
        self.assertEqual(drive.load_installed_key().client_email, "other@test-project.iam.gserviceaccount.com")

    def test_installing_the_already_installed_file_is_harmless(self):
        drive.install_key(self.source)
        drive.install_key(drive.key_path())
        self.assertEqual(drive.load_installed_key().client_email, TEST_EMAIL)

    def test_read_key_file_missing(self):
        with self.assertRaises(BackendError) as ctx:
            drive.read_key_file(os.path.join(self.support_dir, "nope.json"))
        self.assertEqual(ctx.exception.code, "DRIVE_KEY_INVALID")

    def test_broken_installed_key_is_reported_as_invalid(self):
        os.makedirs(self.support_dir)
        with open(drive.key_path(), "w") as fh:
            fh.write("{}")
        with self.assertRaises(BackendError) as ctx:
            drive.load_installed_key()
        self.assertEqual(ctx.exception.code, "DRIVE_KEY_INVALID")


if __name__ == "__main__":
    unittest.main()
