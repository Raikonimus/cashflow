"""
Security-focused tests – injection, timing, token tampering, enumeration.
"""
import asyncio
import time

import pytest

from tests.auth.conftest import create_user


class TestEmailEnumeration:
    async def test_forgot_password_same_response_for_known_and_unknown(
        self, client, db_session
    ):
        """Same message regardless of whether the email is registered."""
        await create_user(db_session)

        resp_known = await client.post(
            "/api/v1/auth/forgot-password", json={"email": "test@example.com"}
        )
        resp_unknown = await client.post(
            "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
        )
        assert resp_known.status_code == resp_unknown.status_code == 200
        assert resp_known.json()["message"] == resp_unknown.json()["message"]


class TestSqlInjection:
    async def test_sql_injection_in_email_field(self, client, db_session):
        await create_user(db_session)
        # Should return 422 (invalid email) or 401, never 200/500
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "' OR 1=1 --", "password": "anything"},
        )
        assert resp.status_code in (401, 422)

    async def test_sql_injection_in_password_field(self, client, db_session):
        await create_user(db_session)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "' OR '1'='1"},
        )
        assert resp.status_code == 401  # must not bypass auth


class TestTokenTampering:
    async def test_modified_role_in_token_is_rejected(self, client, db_session):
        """A token with a modified payload must be rejected (signature mismatch)."""
        import base64, json

        await create_user(db_session)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "secret123"},
        )
        token = resp.json()["access_token"]
        header, payload_b64, sig = token.split(".")

        # Decode, elevate role, re-encode (without correct signature)
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        payload["role"] = "admin"
        new_payload = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        )
        tampered_token = f"{header}.{new_payload}.{sig}"

        result = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_token}"}
        )
        assert result.status_code == 401


class TestPasswordValidation:
    async def test_short_password_returns_422(self, client, db_session):
        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "whatever", "password": "short"},
        )
        assert resp.status_code == 422

    async def test_empty_password_returns_422(self, client, db_session):
        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "whatever", "password": ""},
        )
        assert resp.status_code == 422
