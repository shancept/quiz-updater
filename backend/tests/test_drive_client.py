from __future__ import annotations

import json
import socket
import unittest

from quiz_backend.drive import (
    BACKOFF_SECONDS,
    SHEETS_MIME,
    XLSX_MIME,
    DriveClient,
    ServiceAccountKey,
)
from quiz_backend.errors import BackendError

from .fake_google import FakeGoogle, google_error
from .helpers import TEST_EMAIL, service_account_json

TOKEN_PATH = "/token"
FILES = "/drive/v3/files"
TOKEN_OK = (200, {"access_token": "ya29.test-token", "expires_in": 3600, "token_type": "Bearer"})
XLSX_BYTES = b"PK\x03\x04fake-xlsx-bytes"

SHEET = {"id": "sheet1", "name": "Классика #59 результаты", "mimeType": SHEETS_MIME,
         "modifiedTime": "2026-09-30T18:00:00.000Z"}
XLSX = {"id": "xlsx1", "name": "Старая таблица.xlsx", "mimeType": XLSX_MIME,
        "modifiedTime": "2026-09-01T10:00:00.000Z"}
DOC = {"id": "doc1", "name": "Заметки", "mimeType": "application/vnd.google-apps.document",
       "modifiedTime": "2026-09-02T10:00:00.000Z"}


class DriveClientTestCase(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGoogle().start()
        self.addCleanup(self.fake.stop)
        self.fake.on("POST", TOKEN_PATH, TOKEN_OK)
        self.sleeps: list = []
        key = ServiceAccountKey.from_json(json.dumps(service_account_json()))
        self.client = DriveClient(
            key,
            api_base=self.fake.base_url + "/drive/v3",
            token_uri=self.fake.base_url + TOKEN_PATH,
            sleep=self.sleeps.append,
        )

    def assertBackendError(self, code: str, call, *args):
        with self.assertRaises(BackendError) as ctx:
            call(*args)
        self.assertEqual(ctx.exception.code, code, ctx.exception.message)
        return ctx.exception


class AuthTest(DriveClientTestCase):
    def test_exchanges_signed_jwt_for_access_token_and_uses_it(self):
        self.fake.on("GET", FILES, (200, {"files": []}))
        self.client.list_sheets()

        token_request = self.fake.requests_to(TOKEN_PATH)[0]
        form = token_request.form()
        self.assertEqual(form["grant_type"], "urn:ietf:params:oauth:grant-type:jwt-bearer")
        self.assertEqual(len(form["assertion"].split(".")), 3)
        self.assertEqual(self.fake.requests_to(FILES)[0].headers["Authorization"], "Bearer ya29.test-token")

    def test_token_is_fetched_once_per_client(self):
        self.fake.on("GET", FILES, (200, {"files": []}))
        self.client.list_sheets()
        self.client.list_sheets()
        self.assertEqual(len(self.fake.requests_to(TOKEN_PATH)), 1)

    def test_rejected_key_is_reported_with_googles_description(self):
        self.fake.on("POST", TOKEN_PATH,
                     (400, {"error": "invalid_grant", "error_description": "Invalid JWT Signature."}))
        error = self.assertBackendError("DRIVE_AUTH_FAILED", self.client.list_sheets)
        self.assertIn("Invalid JWT Signature.", error.message)

    def test_api_disabled_in_project_gets_actionable_message(self):
        self.fake.on("GET", FILES, google_error(403, "accessNotConfigured",
                                                "Google Drive API has not been used in project 1 before or it is disabled."))
        error = self.assertBackendError("DRIVE_AUTH_FAILED", self.client.list_sheets)
        self.assertIn("Google Drive API", error.message)

    def test_api_401_is_auth_failure_and_not_retried(self):
        self.fake.on("GET", FILES, google_error(401, "authError", "Invalid Credentials"))
        self.assertBackendError("DRIVE_AUTH_FAILED", self.client.list_sheets)
        self.assertEqual(len(self.fake.requests_to(FILES)), 1)


class ListSheetsTest(DriveClientTestCase):
    def test_returns_files_in_server_order(self):
        self.fake.on("GET", FILES, (200, {"files": [SHEET, XLSX]}))
        self.assertEqual(self.client.list_sheets(), [SHEET, XLSX])

    def test_asks_only_for_sheets_and_xlsx_not_trashed_newest_first(self):
        self.fake.on("GET", FILES, (200, {"files": []}))
        self.client.list_sheets()
        query = self.fake.requests_to(FILES)[0].query
        q = query["q"][0]
        self.assertIn(f"mimeType = '{SHEETS_MIME}'", q)
        self.assertIn(f"mimeType = '{XLSX_MIME}'", q)
        self.assertIn("trashed = false", q)
        self.assertEqual(query["orderBy"], ["modifiedTime desc"])
        self.assertEqual(query["fields"], ["nextPageToken,files(id,name,mimeType,modifiedTime)"])

    def test_follows_pagination(self):
        self.fake.on("GET", FILES,
                     (200, {"files": [SHEET], "nextPageToken": "page2"}),
                     (200, {"files": [XLSX]}))
        self.assertEqual(self.client.list_sheets(), [SHEET, XLSX])
        requests = self.fake.requests_to(FILES)
        self.assertNotIn("pageToken", requests[0].query)
        self.assertEqual(requests[1].query["pageToken"], ["page2"])

    def test_empty_drive_returns_empty_list(self):
        self.fake.on("GET", FILES, (200, {}))
        self.assertEqual(self.client.list_sheets(), [])


class DownloadTest(DriveClientTestCase):
    def test_google_sheet_is_exported_as_xlsx(self):
        self.fake.on("GET", FILES + "/sheet1", (200, SHEET))
        self.fake.on("GET", FILES + "/sheet1/export", (200, XLSX_BYTES))
        meta, data = self.client.download_xlsx("sheet1")
        self.assertEqual(data, XLSX_BYTES)
        self.assertEqual(meta["name"], SHEET["name"])
        self.assertEqual(self.fake.requests_to(FILES + "/sheet1/export")[0].query["mimeType"], [XLSX_MIME])

    def test_uploaded_xlsx_is_downloaded_as_media(self):
        self.fake.on("GET", FILES + "/xlsx1", (200, XLSX), (200, XLSX_BYTES))
        meta, data = self.client.download_xlsx("xlsx1")
        self.assertEqual(data, XLSX_BYTES)
        media = self.fake.requests_to(FILES + "/xlsx1")[1]
        self.assertEqual(media.query["alt"], ["media"])

    def test_not_a_spreadsheet_is_rejected_before_download(self):
        self.fake.on("GET", FILES + "/doc1", (200, DOC))
        self.assertBackendError("EXCEL_BAD_FORMAT", self.client.download_xlsx, "doc1")
        self.assertEqual(len(self.fake.requests_to(FILES + "/doc1")), 1)

    def test_get_file_returns_metadata(self):
        self.fake.on("GET", FILES + "/sheet1", (200, SHEET))
        self.assertEqual(self.client.get_file("sheet1"), SHEET)
        self.assertEqual(self.fake.requests_to(FILES + "/sheet1")[0].query["fields"],
                         ["id,name,mimeType,modifiedTime"])

    def test_file_id_is_url_quoted(self):
        self.fake.on("GET", FILES + "/a%2Fb", (200, SHEET))
        self.client.get_file("a/b")
        self.assertEqual(len(self.fake.requests_to(FILES + "/a%2Fb")), 1)


class FileNotSharedTest(DriveClientTestCase):
    def test_404_means_not_shared_and_carries_robot_address(self):
        self.fake.on("GET", FILES + "/secret", google_error(404, "notFound", "File not found: secret."))
        error = self.assertBackendError("FILE_NOT_SHARED", self.client.get_file, "secret")
        self.assertIn(TEST_EMAIL, error.message)
        self.assertEqual(error.details, {"clientEmail": TEST_EMAIL})
        self.assertNotIn("404", error.message)

    def test_403_forbidden_on_file_means_not_shared(self):
        self.fake.on("GET", FILES + "/secret", google_error(403, "forbidden"))
        error = self.assertBackendError("FILE_NOT_SHARED", self.client.get_file, "secret")
        self.assertEqual(error.details, {"clientEmail": TEST_EMAIL})

    def test_other_403_on_file_is_a_generic_drive_error_with_googles_message(self):
        self.fake.on("GET", FILES + "/sheet1", (200, SHEET))
        self.fake.on("GET", FILES + "/sheet1/export",
                     google_error(403, "exportSizeLimitExceeded", "This file is too large to be exported."))
        error = self.assertBackendError("DRIVE_ERROR", self.client.download_xlsx, "sheet1")
        self.assertIn("too large", error.message)


class RetryTest(DriveClientTestCase):
    def test_retries_503_with_growing_backoff_then_succeeds(self):
        self.fake.on("GET", FILES, google_error(503, "backendError"), google_error(503, "backendError"),
                     (200, {"files": [SHEET]}))
        self.assertEqual(self.client.list_sheets(), [SHEET])
        self.assertEqual(self.sleeps, list(BACKOFF_SECONDS))

    def test_retries_429(self):
        self.fake.on("GET", FILES, google_error(429, "rateLimitExceeded"), (200, {"files": []}))
        self.assertEqual(self.client.list_sheets(), [])

    def test_retries_403_rate_limit(self):
        self.fake.on("GET", FILES, google_error(403, "userRateLimitExceeded"), (200, {"files": []}))
        self.assertEqual(self.client.list_sheets(), [])

    def test_gives_up_after_max_attempts_with_drive_error(self):
        self.fake.on("GET", FILES, google_error(503, "backendError", "Service Unavailable"))
        self.assertBackendError("DRIVE_ERROR", self.client.list_sheets)
        self.assertEqual(len(self.fake.requests_to(FILES)), len(BACKOFF_SECONDS) + 1)

    def test_404_is_not_retried(self):
        self.fake.on("GET", FILES + "/nope", google_error(404, "notFound"))
        self.assertBackendError("FILE_NOT_SHARED", self.client.get_file, "nope")
        self.assertEqual(len(self.fake.requests_to(FILES + "/nope")), 1)
        self.assertEqual(self.sleeps, [])

    def test_token_endpoint_5xx_is_retried(self):
        self.fake.on("POST", TOKEN_PATH, (503, {"error": "backendError"}), TOKEN_OK)
        self.fake.on("GET", FILES, (200, {"files": []}))
        self.assertEqual(self.client.list_sheets(), [])


class NetworkTest(unittest.TestCase):
    def test_connection_refused_is_network_error_after_retries(self):
        with socket.socket() as sock:  # свободный порт, на котором никто не слушает
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        sleeps: list = []
        key = ServiceAccountKey.from_json(json.dumps(service_account_json()))
        client = DriveClient(key, api_base=f"http://127.0.0.1:{port}/drive/v3",
                             token_uri=f"http://127.0.0.1:{port}/token", sleep=sleeps.append)
        with self.assertRaises(BackendError) as ctx:
            client.list_sheets()
        self.assertEqual(ctx.exception.code, "NETWORK_ERROR")
        self.assertIn("интернет", ctx.exception.message)
        self.assertEqual(sleeps, list(BACKOFF_SECONDS))


if __name__ == "__main__":
    unittest.main()
