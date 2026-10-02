from __future__ import annotations

import unittest

from quiz_backend.drive import parse_drive_link
from quiz_backend.errors import BackendError

FILE_ID = "1AbC_dEf-1234567890xyz"


class ParseDriveLinkTest(unittest.TestCase):
    def assertId(self, link: str) -> None:
        self.assertEqual(parse_drive_link(link), FILE_ID, link)

    def assertInvalid(self, link: str) -> None:
        with self.assertRaises(BackendError) as ctx:
            parse_drive_link(link)
        self.assertEqual(ctx.exception.code, "INVALID_LINK", link)

    def test_google_sheets_edit_link_with_gid(self):
        self.assertId(f"https://docs.google.com/spreadsheets/d/{FILE_ID}/edit#gid=0")

    def test_google_sheets_link_with_sharing_query(self):
        self.assertId(f"https://docs.google.com/spreadsheets/d/{FILE_ID}/edit?usp=sharing")

    def test_google_sheets_link_with_account_index(self):
        self.assertId(f"https://docs.google.com/spreadsheets/u/0/d/{FILE_ID}/edit")

    def test_drive_file_link_for_uploaded_xlsx(self):
        self.assertId(f"https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing")

    def test_drive_open_link_with_id_query(self):
        self.assertId(f"https://drive.google.com/open?id={FILE_ID}")

    def test_surrounding_whitespace_is_ignored(self):
        self.assertId(f"  \nhttps://docs.google.com/spreadsheets/d/{FILE_ID}/edit \n")

    def test_link_without_scheme(self):
        self.assertId(f"docs.google.com/spreadsheets/d/{FILE_ID}/edit")

    def test_arbitrary_text_is_not_a_link(self):
        self.assertInvalid("привет")

    def test_empty_string(self):
        self.assertInvalid("   ")

    def test_foreign_host(self):
        self.assertInvalid(f"https://example.com/spreadsheets/d/{FILE_ID}/edit")

    def test_lookalike_host_is_rejected(self):
        self.assertInvalid(f"https://docs.google.com.evil.example/spreadsheets/d/{FILE_ID}/edit")

    def test_folder_link_is_not_a_file(self):
        self.assertInvalid(f"https://drive.google.com/drive/folders/{FILE_ID}")

    def test_published_to_web_link_has_no_file_id(self):
        self.assertInvalid("https://docs.google.com/spreadsheets/d/e/2PACX-1vTabcdefghij/pubhtml")

    def test_message_explains_what_link_is_expected(self):
        with self.assertRaises(BackendError) as ctx:
            parse_drive_link("привет")
        self.assertIn("Google Drive", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
