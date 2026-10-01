"""Общие помощники тестов. Секретов в репозитории нет: RSA-ключ генерируется на лету."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

TEST_EMAIL = "robot@test-project.iam.gserviceaccount.com"

_material_cache: dict = {}


def _openssl() -> str:
    path = "/usr/bin/openssl" if os.path.exists("/usr/bin/openssl") else shutil.which("openssl")
    if not path:
        raise RuntimeError("Для тестов нужен openssl")
    return path


def _run(args: list, input_bytes: bytes = None) -> bytes:
    return subprocess.run(
        [_openssl()] + args, input=input_bytes, check=True, capture_output=True
    ).stdout


def key_material() -> dict:
    """Возвращает {"pkcs8": PEM, "pkcs1": PEM, "public": PEM}; ключ генерируется один раз на процесс."""
    if not _material_cache:
        pkcs8 = _run(["genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"])
        public = _run(["rsa", "-pubout"], pkcs8)
        pkcs1 = _run(["rsa"], pkcs8)  # LibreSSL отдаёт PKCS#1; OpenSSL 3 — PKCS#8
        if b"BEGIN RSA PRIVATE KEY" not in pkcs1:
            pkcs1 = _run(["rsa", "-traditional"], pkcs8)
        _material_cache.update(
            pkcs8=pkcs8.decode(), pkcs1=pkcs1.decode(), public=public.decode()
        )
    return _material_cache


def service_account_json(email: str = TEST_EMAIL, private_key: str = None) -> dict:
    return {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "0123456789abcdef",
        "private_key": private_key if private_key is not None else key_material()["pkcs8"],
        "client_email": email,
        "client_id": "1234567890",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def openssl_verifies(public_pem: str, message: bytes, signature: bytes) -> bool:
    """Независимая проверка RS256-подписи самим openssl (SHA-256, PKCS#1 v1.5)."""
    with tempfile.TemporaryDirectory() as tmp:
        files = {"pub.pem": public_pem.encode(), "msg.bin": message, "sig.bin": signature}
        for name, content in files.items():
            with open(os.path.join(tmp, name), "wb") as fh:
                fh.write(content)
        result = subprocess.run(
            [_openssl(), "dgst", "-sha256", "-verify", os.path.join(tmp, "pub.pem"),
             "-signature", os.path.join(tmp, "sig.bin"), os.path.join(tmp, "msg.bin")],
            capture_output=True,
        )
        return result.returncode == 0
