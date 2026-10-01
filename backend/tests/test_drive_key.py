from __future__ import annotations

import base64
import json
import unittest

from quiz_backend.drive import AUDIENCE, SCOPE, ServiceAccountKey, build_jwt
from quiz_backend.errors import BackendError

from .helpers import TEST_EMAIL, key_material, openssl_verifies, service_account_json


def _b64url_decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


class ServiceAccountKeyTest(unittest.TestCase):
    def assertKeyInvalid(self, text: str, fragment: str = None) -> None:
        with self.assertRaises(BackendError) as ctx:
            ServiceAccountKey.from_json(text)
        self.assertEqual(ctx.exception.code, "DRIVE_KEY_INVALID")
        if fragment:
            self.assertIn(fragment, ctx.exception.message)

    def test_loads_client_email(self):
        key = ServiceAccountKey.from_json(json.dumps(service_account_json()))
        self.assertEqual(key.client_email, TEST_EMAIL)

    def test_not_json(self):
        self.assertKeyInvalid("это не json", "JSON")

    def test_oauth_client_secret_is_not_a_service_account_key(self):
        text = json.dumps({"installed": {"client_id": "x", "client_secret": "y"}})
        self.assertKeyInvalid(text, "сервисного аккаунта")

    def test_missing_private_key(self):
        data = service_account_json()
        del data["private_key"]
        self.assertKeyInvalid(json.dumps(data), "private_key")

    def test_missing_client_email(self):
        data = service_account_json()
        del data["client_email"]
        self.assertKeyInvalid(json.dumps(data), "client_email")

    def test_garbage_private_key(self):
        data = service_account_json(private_key="-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n")
        self.assertKeyInvalid(json.dumps(data))


class BuildJwtTest(unittest.TestCase):
    NOW = 1_700_000_000

    def _split(self, jwt: str):
        header, claims, signature = jwt.split(".")
        return header, claims, signature

    def _jwt_for(self, private_pem: str) -> str:
        key = ServiceAccountKey.from_json(json.dumps(service_account_json(private_key=private_pem)))
        return build_jwt(key, now=self.NOW)

    def test_header_and_claims(self):
        jwt = self._jwt_for(key_material()["pkcs8"])
        header, claims, _ = self._split(jwt)
        self.assertEqual(json.loads(_b64url_decode(header)), {"alg": "RS256", "typ": "JWT"})
        self.assertEqual(
            json.loads(_b64url_decode(claims)),
            {"iss": TEST_EMAIL, "scope": SCOPE, "aud": AUDIENCE, "iat": self.NOW, "exp": self.NOW + 3600},
        )

    def test_scope_is_read_only(self):
        self.assertEqual(SCOPE, "https://www.googleapis.com/auth/drive.readonly")

    def test_pkcs8_signature_is_verified_by_openssl(self):
        jwt = self._jwt_for(key_material()["pkcs8"])
        header, claims, signature = self._split(jwt)
        self.assertTrue(
            openssl_verifies(key_material()["public"], f"{header}.{claims}".encode(), _b64url_decode(signature))
        )

    def test_pkcs1_signature_is_verified_by_openssl(self):
        jwt = self._jwt_for(key_material()["pkcs1"])
        header, claims, signature = self._split(jwt)
        self.assertTrue(
            openssl_verifies(key_material()["public"], f"{header}.{claims}".encode(), _b64url_decode(signature))
        )

    def test_jwt_is_url_safe_without_padding(self):
        jwt = self._jwt_for(key_material()["pkcs8"])
        self.assertNotRegex(jwt, r"[+/=\s]")


if __name__ == "__main__":
    unittest.main()
