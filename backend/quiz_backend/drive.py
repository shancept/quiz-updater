"""Доступ к Google Drive от имени сервисного аккаунта (только чтение).

Зависимости — только stdlib (urllib) и pure-Python `rsa`/`pyasn1` для подписи JWT (RS256):
бэкенд работает на системном /usr/bin/python3 3.9 (LibreSSL), пользователю ничего ставить не нужно.
"""
from __future__ import annotations

import base64
import http.client
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, quote, urlencode, urlparse

import rsa

from .errors import BackendError

SCOPE = "https://www.googleapis.com/auth/drive.readonly"
AUDIENCE = "https://oauth2.googleapis.com/token"
TOKEN_URI = AUDIENCE
API_BASE = "https://www.googleapis.com/drive/v3"
JWT_LIFETIME_SECONDS = 3600

SHEETS_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FILE_FIELDS = "id,name,mimeType,modifiedTime"

REQUEST_TIMEOUT = 10
# Пауза перед 2-й и 3-й попыткой; всего попыток на 1 больше. Ведущий ждёт ответа
# между раундами, поэтому ретраев мало: хватает на кратковременный сбой, не на простой.
BACKOFF_SECONDS = (1.0, 2.0)
MAX_LIST_PAGES = 20

DEFAULT_SUPPORT_DIR = os.path.expanduser("~/Library/Application Support/QuizUpdater")
KEY_FILENAME = "service-account.json"
SUPPORT_DIR = DEFAULT_SUPPORT_DIR  # модульная переменная, чтобы тесты могли подменить каталог

_RATE_LIMIT_REASONS = ("rateLimitExceeded", "userRateLimitExceeded")
_NOT_SHARED_REASONS = ("notFound", "forbidden", "insufficientFilePermissions")

_LINK_HOSTS = ("docs.google.com", "drive.google.com")
# /d/<id>/ — но не /d/e/<токен публикации>/, это не ID файла.
_LINK_ID_IN_PATH = re.compile(r"/d/(?!e/)([A-Za-z0-9_-]+)")
_LINK_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def parse_drive_link(text: str) -> str:
    """Достаёт ID файла из ссылки Google Drive / Google Sheets; иначе INVALID_LINK."""
    invalid = BackendError(
        "INVALID_LINK",
        "Это не похоже на ссылку на файл Google Drive. Скопируйте ссылку на таблицу "
        "из адресной строки браузера или через «Поделиться → Копировать ссылку».",
    )
    text = text.strip()
    if not text:
        raise invalid
    if "://" not in text:
        text = "https://" + text

    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in _LINK_HOSTS:
        raise invalid

    match = _LINK_ID_IN_PATH.search(parsed.path)
    if match:
        return match.group(1)
    ids = parse_qs(parsed.query).get("id", [])
    if ids and _LINK_ID_PATTERN.match(ids[0]):
        return ids[0]
    raise invalid


# --- Ключ сервисного аккаунта и подпись JWT -----------------------------------------


def _der_read(data: bytes, pos: int):
    """Читает один DER TLV с позиции pos → (tag, начало содержимого, длина содержимого)."""
    tag = data[pos]
    length = data[pos + 1]
    pos += 2
    if length & 0x80:
        count = length & 0x7F
        length = int.from_bytes(data[pos:pos + count], "big")
        pos += count
    if pos + length > len(data):
        raise ValueError("DER обрезан")
    return tag, pos, length


def _pkcs1_der_from_pem(pem: str) -> bytes:
    """Возвращает DER ключа в формате PKCS#1 из PEM (PKCS#8 или PKCS#1).

    Google выдаёт ключи сервисных аккаунтов в PKCS#8 («BEGIN PRIVATE KEY»), а `rsa` читает
    только PKCS#1, поэтому из обёртки PKCS#8 достаётся вложенный OCTET STRING.
    """
    lines = [line.strip() for line in pem.strip().splitlines()]
    if not lines or not lines[0].startswith("-----BEGIN ") or not lines[-1].startswith("-----END "):
        raise ValueError("нет PEM-заголовка")
    der = base64.b64decode("".join(lines[1:-1]), validate=True)
    if lines[0] == "-----BEGIN RSA PRIVATE KEY-----":
        return der
    if lines[0] != "-----BEGIN PRIVATE KEY-----":
        raise ValueError("неизвестный тип ключа: " + lines[0])

    tag, pos, _ = _der_read(der, 0)  # PrivateKeyInfo ::= SEQUENCE
    if tag != 0x30:
        raise ValueError("ожидалась SEQUENCE")
    tag, pos, length = _der_read(der, pos)  # version INTEGER
    if tag != 0x02:
        raise ValueError("ожидался INTEGER")
    pos += length
    tag, pos, length = _der_read(der, pos)  # privateKeyAlgorithm SEQUENCE
    if tag != 0x30:
        raise ValueError("ожидалась SEQUENCE")
    pos += length
    tag, pos, length = _der_read(der, pos)  # privateKey OCTET STRING (внутри — PKCS#1)
    if tag != 0x04:
        raise ValueError("ожидался OCTET STRING")
    return der[pos:pos + length]


class ServiceAccountKey:
    """JSON-ключ сервисного аккаунта Google: адрес робота + приватный ключ для подписи."""

    def __init__(self, client_email: str, private_key: "rsa.PrivateKey") -> None:
        self.client_email = client_email
        self._private_key = private_key

    @classmethod
    def from_json(cls, text: str) -> "ServiceAccountKey":
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise BackendError("DRIVE_KEY_INVALID", f"Файл ключа не является корректным JSON: {exc}") from exc
        if not isinstance(data, dict) or data.get("type") != "service_account":
            raise BackendError(
                "DRIVE_KEY_INVALID",
                "Это не ключ сервисного аккаунта: в JSON ожидается \"type\": \"service_account\". "
                "Нужен ключ из Google Cloud Console → IAM и администрирование → Сервисные аккаунты → Ключи.",
            )
        for field in ("client_email", "private_key"):
            if not isinstance(data.get(field), str) or not data[field]:
                raise BackendError("DRIVE_KEY_INVALID", f"В ключе сервисного аккаунта нет поля {field}")
        try:
            private_key = rsa.PrivateKey.load_pkcs1(_pkcs1_der_from_pem(data["private_key"]), format="DER")
        except Exception as exc:  # noqa: BLE001 - любой сбой разбора = ключ непригоден
            raise BackendError(
                "DRIVE_KEY_INVALID", f"Не удалось прочитать private_key из файла ключа: {exc}"
            ) from exc
        return cls(data["client_email"], private_key)

    def sign(self, message: bytes) -> bytes:
        """RSASSA-PKCS1-v1_5 + SHA-256 (RS256)."""
        return rsa.sign(message, self._private_key, "SHA-256")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def build_jwt(key: ServiceAccountKey, now: int = None, audience: str = AUDIENCE) -> str:
    """Собирает подписанный JWT-assertion для обмена на access token (scope — только чтение)."""
    issued_at = int(time.time()) if now is None else now
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": key.client_email,
        "scope": SCOPE,
        "aud": audience,
        "iat": issued_at,
        "exp": issued_at + JWT_LIFETIME_SECONDS,
    }
    signing_input = ".".join(
        _b64url(json.dumps(part, separators=(",", ":")).encode("utf-8")) for part in (header, claims)
    )
    return signing_input + "." + _b64url(key.sign(signing_input.encode("ascii")))


# --- HTTP-клиент Drive API ------------------------------------------------------------


class _HttpError(Exception):
    """Ответ Google с кодом ошибки; внутренний тип, наружу уходит BackendError."""

    def __init__(self, status: int, body: bytes) -> None:
        super().__init__(status)
        self.status = status
        self.reason, self.message = self._parse(body)
        self.service_disabled = b"SERVICE_DISABLED" in body

    @staticmethod
    def _parse(body: bytes) -> tuple:
        try:
            data = json.loads(body)
        except ValueError:
            return "", body[:200].decode("utf-8", errors="replace")
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):  # формат Drive API
            errors = error.get("errors") or []
            first = errors[0] if errors and isinstance(errors[0], dict) else {}
            return first.get("reason", ""), error.get("message", "")
        if isinstance(error, str):  # формат token endpoint: {"error", "error_description"}
            return error, data.get("error_description", "")
        return "", ""

    @property
    def is_transient(self) -> bool:
        return self.status in (429, 500, 502, 503, 504) or (
            self.status == 403 and self.reason in _RATE_LIMIT_REASONS
        )


class DriveClient:
    """Минимальный клиент Drive API v3 (только чтение): список таблиц, метаданные, выгрузка xlsx."""

    def __init__(self, key: ServiceAccountKey, api_base: str = API_BASE, token_uri: str = TOKEN_URI,
                 sleep=time.sleep) -> None:
        self.client_email = key.client_email
        self._key = key
        self._api_base = api_base
        self._token_uri = token_uri
        self._sleep = sleep
        self._access_token = None

    # -- транспорт --

    def _send(self, request: urllib.request.Request) -> bytes:
        attempts = len(BACKOFF_SECONDS) + 1
        for attempt in range(attempts):
            last = attempt == attempts - 1
            try:
                with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:  # раньше OSError: HTTPError — его наследник
                error = _HttpError(exc.code, exc.read())
                if last or not error.is_transient:
                    raise error from None
            except (OSError, http.client.HTTPException):
                if last:
                    raise BackendError(
                        "NETWORK_ERROR",
                        "Нет связи с Google. Проверьте подключение к интернету и повторите.",
                    ) from None
            self._sleep(BACKOFF_SECONDS[attempt])
        raise AssertionError("недостижимо")  # pragma: no cover

    def _get_token(self) -> str:
        if self._access_token is None:
            form = urlencode({
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": build_jwt(self._key),
            }).encode("ascii")
            request = urllib.request.Request(
                self._token_uri, data=form, method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            try:
                payload = json.loads(self._send(request))
            except _HttpError as exc:
                if exc.status in (400, 401, 403):
                    detail = exc.message or exc.reason
                    raise BackendError(
                        "DRIVE_AUTH_FAILED",
                        f"Google не принял ключ сервисного аккаунта ({detail}). Возможно, ключ удалён или "
                        "отозван — создайте новый и подключите заново. Также проверьте дату и время на этом Mac.",
                    ) from None
                raise self._generic_error(exc) from None
            except ValueError as exc:
                raise BackendError("DRIVE_ERROR", "Google вернул некорректный ответ при авторизации") from exc
            self._access_token = payload["access_token"]
        return self._access_token

    def _request(self, path: str, params: dict, file_scope: bool = False) -> bytes:
        request = urllib.request.Request(
            f"{self._api_base}{path}?{urlencode(params)}",
            headers={"Authorization": f"Bearer {self._get_token()}"},
        )
        try:
            return self._send(request)
        except _HttpError as exc:
            raise self._translate(exc, file_scope) from None

    def _request_json(self, path: str, params: dict, file_scope: bool = False) -> dict:
        raw = self._request(path, params, file_scope)
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise BackendError("DRIVE_ERROR", "Google Drive вернул некорректный ответ") from exc

    # -- перевод ошибок в понятные сообщения --

    @staticmethod
    def _generic_error(exc: _HttpError) -> BackendError:
        return BackendError(
            "DRIVE_ERROR", f"Google Drive вернул ошибку {exc.status}: {exc.message or exc.reason or 'без описания'}"
        )

    def _translate(self, exc: _HttpError, file_scope: bool) -> BackendError:
        if exc.status == 401:
            return BackendError(
                "DRIVE_AUTH_FAILED",
                "Google Drive отклонил авторизацию (401). Подключите ключ сервисного аккаунта заново.",
            )
        if exc.status == 403 and (exc.reason == "accessNotConfigured" or exc.service_disabled):
            return BackendError(
                "DRIVE_AUTH_FAILED",
                "В проекте Google Cloud не включён Google Drive API. Включите его "
                "(APIs & Services → Library → Google Drive API) и повторите.",
            )
        if file_scope and (exc.status == 404 or (exc.status == 403 and exc.reason in _NOT_SHARED_REASONS)):
            return BackendError(
                "FILE_NOT_SHARED",
                "У QuizUpdater нет доступа к этой таблице. В Google Drive нажмите «Поделиться» и дайте доступ "
                f"«Читатель» адресу робота: {self.client_email}",
                clientEmail=self.client_email,
            )
        return self._generic_error(exc)

    # -- публичный API --

    def list_sheets(self) -> list:
        """Google Sheets и .xlsx, доступные роботу, свежие (по modifiedTime) первыми."""
        query = (
            f"trashed = false and (mimeType = '{SHEETS_MIME}' or mimeType = '{XLSX_MIME}')"
        )
        files: list = []
        page_token = None
        for _ in range(MAX_LIST_PAGES):
            params = {
                "q": query,
                "orderBy": "modifiedTime desc",
                "fields": f"nextPageToken,files({FILE_FIELDS})",
                "pageSize": "1000",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page_token:
                params["pageToken"] = page_token
            page = self._request_json("/files", params)
            files.extend(page.get("files", []))
            page_token = page.get("nextPageToken")
            if not page_token:
                break
        return files

    def get_file(self, file_id: str) -> dict:
        return self._request_json(
            f"/files/{quote(file_id, safe='')}",
            {"fields": FILE_FIELDS, "supportsAllDrives": "true"},
            file_scope=True,
        )

    def get_sheet(self, file_id: str) -> dict:
        """Метаданные файла; EXCEL_BAD_FORMAT, если это не Google-таблица и не .xlsx."""
        meta = self.get_file(file_id)
        if meta.get("mimeType") not in (SHEETS_MIME, XLSX_MIME):
            raise BackendError(
                "EXCEL_BAD_FORMAT",
                f"«{meta.get('name', file_id)}» — не таблица (тип файла: {meta.get('mimeType')}). "
                "Выберите Google-таблицу или файл .xlsx.",
            )
        return meta

    def download_xlsx(self, file_id: str) -> tuple:
        """Скачивает таблицу заново (без кэша) → (метаданные, байты .xlsx)."""
        meta = self.get_sheet(file_id)
        quoted = quote(file_id, safe="")
        if meta["mimeType"] == SHEETS_MIME:
            data = self._request(f"/files/{quoted}/export", {"mimeType": XLSX_MIME}, file_scope=True)
        else:
            data = self._request(f"/files/{quoted}", {"alt": "media", "supportsAllDrives": "true"}, file_scope=True)
        return meta, data


# --- Ключ на диске: подключение Drive на этом Mac --------------------------------------


def key_path() -> str:
    return os.path.join(SUPPORT_DIR, KEY_FILENAME)


def is_connected() -> bool:
    return os.path.exists(key_path())


def read_key_file(path: str) -> ServiceAccountKey:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, ValueError) as exc:
        raise BackendError("DRIVE_KEY_INVALID", f"Не удалось прочитать файл ключа: {exc}") from exc
    return ServiceAccountKey.from_json(text)


def load_installed_key() -> ServiceAccountKey:
    if not is_connected():
        raise BackendError(
            "DRIVE_NOT_CONNECTED",
            "Google Drive не подключён. Нажмите «Подключить Google Drive…» и выберите JSON-ключ "
            "сервисного аккаунта.",
        )
    return read_key_file(key_path())


def install_key(source_path: str) -> None:
    """Копирует ключ в каталог приложения (права 0600, каталог 0700), атомарно заменяя прежний."""
    destination = key_path()
    try:
        if os.path.exists(destination) and os.path.samefile(source_path, destination):
            return
        os.makedirs(SUPPORT_DIR, exist_ok=True)
        os.chmod(SUPPORT_DIR, 0o700)
        fd, tmp_path = tempfile.mkstemp(dir=SUPPORT_DIR, prefix=".key-")  # mkstemp создаёт файл с 0600
        try:
            with os.fdopen(fd, "wb") as out, open(source_path, "rb") as src:
                out.write(src.read())
            os.replace(tmp_path, destination)
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    except OSError as exc:
        raise BackendError("DRIVE_ERROR", f"Не удалось сохранить ключ в {SUPPORT_DIR}: {exc}") from exc


def client_for(key: ServiceAccountKey) -> DriveClient:
    # Адреса читаются из модуля в момент вызова (а не при импорте) — тесты подменяют их на фейк.
    return DriveClient(key, api_base=API_BASE, token_uri=TOKEN_URI)


def installed_client() -> DriveClient:
    return client_for(load_installed_key())
