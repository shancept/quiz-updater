from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from unittest import mock

from quiz_backend import __main__ as cli
from quiz_backend import drive
from quiz_backend.drive import SHEETS_MIME, XLSX_MIME

from .fake_google import FakeGoogle, google_error
from .helpers import TEST_EMAIL, service_account_json, workbook_bytes

TOKEN_PATH = "/token"
FILES = "/drive/v3/files"
TOKEN_OK = (200, {"access_token": "ya29.test-token", "expires_in": 3600})

SHEET = {"id": "sheet1", "name": "Классика #59 результаты", "mimeType": SHEETS_MIME,
         "modifiedTime": "2026-09-30T18:00:00.000Z"}
XLSX = {"id": "xlsx1", "name": "Старая.xlsx", "mimeType": XLSX_MIME, "modifiedTime": "2026-09-01T10:00:00.000Z"}
DOC = {"id": "doc1", "name": "Заметки", "mimeType": "application/vnd.google-apps.document",
       "modifiedTime": "2026-09-02T10:00:00.000Z"}

HEADER = ["Место", "Команда", "Итого"] + [f"Раунд {i}" for i in range(1, 10)]
# 9 колонок раундов на Drive: ровно сколько взять, решает Keynote.
RESULTS = workbook_bytes([
    HEADER,
    [1, "Альфа", 90, 10, 20, 30, 40, 50, 60, 70, 80, 90],
    [2, "Бета", 40, 1, 2, 3, 4, None, 6, 7, 8, 9],
])


def run_cli(*argv: str) -> tuple:
    """Запускает main() как из терминала → (код выхода, распарсенный JSON из stdout)."""
    out = io.StringIO()
    with mock.patch("sys.argv", ["quiz_backend", *argv]), contextlib.redirect_stdout(out):
        code = cli.main()
    lines = out.getvalue().strip().splitlines()
    assert len(lines) == 1, f"бэкенд должен печатать ровно один JSON-объект, а напечатал: {out.getvalue()!r}"
    return code, json.loads(lines[0])


class CommandTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.support_dir = os.path.join(tmp.name, "Support")

        self.fake = FakeGoogle().start()
        self.addCleanup(self.fake.stop)
        self.fake.on("POST", TOKEN_PATH, TOKEN_OK)

        for target, value in (
            (drive, {"SUPPORT_DIR": self.support_dir,
                     "API_BASE": self.fake.base_url + "/drive/v3",
                     "TOKEN_URI": self.fake.base_url + TOKEN_PATH}),
        ):
            for name, val in value.items():
                patcher = mock.patch.object(target, name, val)
                patcher.start()
                self.addCleanup(patcher.stop)

    def install_key(self, email: str = TEST_EMAIL) -> str:
        path = os.path.join(self.tmp, "key-source.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(service_account_json(email=email), fh)
        drive.install_key(path)
        return path

    def share_sheet(self, file_meta: dict = SHEET, content: bytes = RESULTS) -> None:
        file_id = file_meta["id"]
        self.fake.on("GET", f"{FILES}/{file_id}", (200, file_meta), (200, content))
        self.fake.on("GET", f"{FILES}/{file_id}/export", (200, content))


class DriveStatusTest(CommandTestCase):
    def test_not_connected_is_not_an_error(self):
        code, payload = run_cli("drive-status")
        self.assertEqual(code, 0)
        self.assertEqual(payload, {"ok": True, "connected": False, "clientEmail": None})

    def test_connected_reports_robot_address_without_network(self):
        self.install_key()
        code, payload = run_cli("drive-status")
        self.assertEqual(payload, {"ok": True, "connected": True, "clientEmail": TEST_EMAIL})
        self.assertEqual(self.fake.requests, [])


class ConnectDriveTest(CommandTestCase):
    def setUp(self):
        super().setUp()
        self.key_file = os.path.join(self.tmp, "downloaded.json")
        with open(self.key_file, "w", encoding="utf-8") as fh:
            json.dump(service_account_json(), fh)

    def test_verifies_access_then_installs_key(self):
        self.fake.on("GET", FILES, (200, {"files": [SHEET, XLSX]}))
        code, payload = run_cli("connect-drive", "--key", self.key_file)

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload, {"ok": True, "clientEmail": TEST_EMAIL, "sheetCount": 2})
        self.assertEqual(stat.S_IMODE(os.stat(drive.key_path()).st_mode), 0o600)

    def test_zero_sheets_is_still_connected(self):
        self.fake.on("GET", FILES, (200, {"files": []}))
        code, payload = run_cli("connect-drive", "--key", self.key_file)
        self.assertEqual((code, payload["sheetCount"]), (0, 0))
        self.assertTrue(drive.is_connected())

    def test_rejected_key_is_not_installed(self):
        self.fake.on("POST", TOKEN_PATH, (400, {"error": "invalid_grant", "error_description": "Invalid JWT Signature."}))
        code, payload = run_cli("connect-drive", "--key", self.key_file)
        self.assertEqual(code, 1)
        self.assertEqual(payload["code"], "DRIVE_AUTH_FAILED")
        self.assertFalse(drive.is_connected())

    def test_failed_reconnect_keeps_previous_working_key(self):
        self.install_key(email="old@test-project.iam.gserviceaccount.com")
        self.fake.on("POST", TOKEN_PATH, (400, {"error": "invalid_grant", "error_description": "bad"}))
        run_cli("connect-drive", "--key", self.key_file)
        self.assertEqual(drive.load_installed_key().client_email, "old@test-project.iam.gserviceaccount.com")

    def test_oauth_client_secret_file_is_rejected_without_network(self):
        with open(self.key_file, "w", encoding="utf-8") as fh:
            json.dump({"installed": {"client_id": "x"}}, fh)
        code, payload = run_cli("connect-drive", "--key", self.key_file)
        self.assertEqual((code, payload["code"]), (1, "DRIVE_KEY_INVALID"))
        self.assertEqual(self.fake.requests, [])
        self.assertFalse(drive.is_connected())


class ListSheetsTest(CommandTestCase):
    def test_lists_sheets_for_the_picker(self):
        self.install_key()
        self.fake.on("GET", FILES, (200, {"files": [SHEET, XLSX]}))
        code, payload = run_cli("list-sheets")
        self.assertEqual(code, 0)
        self.assertEqual(payload["sheets"], [SHEET, XLSX])
        self.assertEqual(payload["clientEmail"], TEST_EMAIL)

    def test_without_key_says_drive_is_not_connected(self):
        code, payload = run_cli("list-sheets")
        self.assertEqual((code, payload["code"]), (1, "DRIVE_NOT_CONNECTED"))


class ResolveLinkTest(CommandTestCase):
    def setUp(self):
        super().setUp()
        self.install_key()

    def test_link_to_google_sheet_returns_its_metadata(self):
        self.fake.on("GET", f"{FILES}/sheet1", (200, SHEET))
        code, payload = run_cli("resolve-link", "--link", "https://docs.google.com/spreadsheets/d/sheet1/edit#gid=0")
        self.assertEqual((code, payload["sheet"]), (0, SHEET))

    def test_bad_link_is_rejected_without_network(self):
        code, payload = run_cli("resolve-link", "--link", "привет")
        self.assertEqual((code, payload["code"]), (1, "INVALID_LINK"))
        self.assertEqual(self.fake.requests, [])

    def test_link_to_unshared_file_asks_to_share_with_robot(self):
        self.fake.on("GET", f"{FILES}/secret", google_error(404, "notFound"))
        code, payload = run_cli("resolve-link", "--link", "https://docs.google.com/spreadsheets/d/secret/edit")
        self.assertEqual((code, payload["code"]), (1, "FILE_NOT_SHARED"))
        self.assertEqual(payload["clientEmail"], TEST_EMAIL)
        self.assertIn(TEST_EMAIL, payload["error"])

    def test_link_to_non_spreadsheet_is_rejected(self):
        self.fake.on("GET", f"{FILES}/doc1", (200, DOC))
        code, payload = run_cli("resolve-link", "--link", "https://docs.google.com/document/d/doc1/edit")
        self.assertEqual((code, payload["code"]), (1, "EXCEL_BAD_FORMAT"))


class ReadSheetTest(CommandTestCase):
    def setUp(self):
        super().setUp()
        self.install_key()

    def test_reads_teams_from_google_sheet(self):
        self.share_sheet()
        code, payload = run_cli("read-sheet", "--file-id", "sheet1", "--rounds", "2")
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["sheetName"], SHEET["name"])
        self.assertEqual(payload["teams"][0], {"place": 1, "name": "Альфа", "total": 90, "rounds": [10, 20]})

    def test_reads_teams_from_uploaded_xlsx(self):
        self.share_sheet(XLSX)
        code, payload = run_cli("read-sheet", "--file-id", "xlsx1")
        self.assertEqual(code, 0, payload)
        self.assertEqual([t["name"] for t in payload["teams"]], ["Альфа", "Бета"])

    def test_every_call_downloads_fresh_data(self):
        self.share_sheet()
        _, first = run_cli("read-sheet", "--file-id", "sheet1")
        self.share_sheet(content=workbook_bytes([HEADER, [1, "Гамма", 99]]))
        _, second = run_cli("read-sheet", "--file-id", "sheet1")
        self.assertEqual(first["teams"][0]["name"], "Альфа")
        self.assertEqual(second["teams"][0]["name"], "Гамма")

    def test_not_shared_file(self):
        self.fake.on("GET", f"{FILES}/sheet1", google_error(404, "notFound"))
        code, payload = run_cli("read-sheet", "--file-id", "sheet1")
        self.assertEqual((code, payload["code"], payload["clientEmail"]), (1, "FILE_NOT_SHARED", TEST_EMAIL))

    def test_missing_sheet1_lists_sheets(self):
        self.share_sheet(content=workbook_bytes([HEADER], title="Результаты"))
        code, payload = run_cli("read-sheet", "--file-id", "sheet1")
        self.assertEqual((code, payload["code"]), (1, "EXCEL_BAD_FORMAT"))
        self.assertIn("Результаты", payload["error"])


class UpdateRatingTest(CommandTestCase):
    def setUp(self):
        super().setUp()
        self.install_key()
        self.share_sheet()
        self.applescript = mock.Mock(return_value="OK")
        for target, value in (
            ("resolve_doc_name", mock.Mock(return_value="Квиз")),
            ("read_rating_rounds", mock.Mock(return_value=8)),
        ):
            patcher = mock.patch.object(cli.keynote_mod, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(cli, "run_applescript", self.applescript)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_dry_run_takes_exactly_as_many_rounds_as_keynote_table_has(self):
        code, payload = run_cli("update-rating", "--slide", "81", "--file-id", "sheet1", "--dry-run")
        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["dryRun"])
        self.assertEqual(payload["rounds"], 8)
        self.assertEqual(payload["teams"][0]["rounds"], [10, 20, 30, 40, 50, 60, 70, 80])
        self.assertEqual(payload["teams"][1]["rounds"], [1, 2, 3, 4, None, 6, 7, 8])  # пустая ячейка → пустая
        self.applescript.assert_not_called()

    def test_seven_round_table_gets_seven_rounds(self):
        cli.keynote_mod.read_rating_rounds.return_value = 7
        _, payload = run_cli("update-rating", "--slide", "81", "--file-id", "sheet1", "--dry-run")
        self.assertEqual(payload["rounds"], 7)
        self.assertEqual(payload["teams"][0]["rounds"], [10, 20, 30, 40, 50, 60, 70])

    def test_real_run_writes_eight_rounds_to_keynote(self):
        code, payload = run_cli("update-rating", "--slide", "81", "--file-id", "sheet1")
        self.assertEqual(code, 0, payload)
        script = self.applescript.call_args[0][0]
        self.assertIn("set value of cell 11 of row 1 of t to 80", script)
        self.assertNotIn("cell 12", script)

    def test_max_rows_limits_teams(self):
        _, payload = run_cli("update-rating", "--slide", "81", "--file-id", "sheet1", "--max-rows", "1", "--dry-run")
        self.assertEqual([t["name"] for t in payload["teams"]], ["Альфа"])

    def test_keynote_error_is_reported_before_touching_drive_data(self):
        from quiz_backend.errors import BackendError
        cli.keynote_mod.read_rating_rounds.side_effect = BackendError("TEMPLATE_INVALID", "нет таблицы")
        code, payload = run_cli("update-rating", "--slide", "81", "--file-id", "sheet1", "--dry-run")
        self.assertEqual((code, payload["code"]), (1, "TEMPLATE_INVALID"))


class ReplaceNamesTest(CommandTestCase):
    def setUp(self):
        super().setUp()
        self.install_key()
        self.share_sheet()
        for target, value in (
            ("resolve_doc_name", mock.Mock(return_value="Квиз")),
            ("check_placeholders", mock.Mock(return_value={182: True, 181: False})),
        ):
            patcher = mock.patch.object(cli.keynote_mod, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_dry_run_matches_places_from_drive_to_slides(self):
        code, payload = run_cli("replace-names", "--file-id", "sheet1", "--pairs", "1:182,2:181", "--dry-run")
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["assignments"], [
            {"place": 1, "slide": 182, "team": "Альфа", "placeholderFound": True},
            {"place": 2, "slide": 181, "team": "Бета", "placeholderFound": False},
        ])


class LocalModeRemovedTest(unittest.TestCase):
    def _rejects(self, *argv: str) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.build_parser().parse_args(list(argv))

    def test_read_excel_subcommand_is_gone(self):
        self._rejects("read-excel")

    def test_excel_option_is_gone_from_update_rating(self):
        self._rejects("update-rating", "--excel", "/tmp/x.xlsx", "--file-id", "a")

    def test_excel_option_is_gone_from_replace_names(self):
        self._rejects("replace-names", "--excel", "/tmp/x.xlsx", "--file-id", "a", "--pairs", "1:2")

    def test_no_default_excel_path(self):
        self.assertFalse(hasattr(cli, "DEFAULT_EXCEL"))

    def test_file_id_is_required(self):
        self._rejects("update-rating", "--slide", "81")
        self._rejects("replace-names", "--pairs", "1:2")
        self._rejects("read-sheet")


if __name__ == "__main__":
    unittest.main()
