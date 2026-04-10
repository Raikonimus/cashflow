"""
Unit tests – security.py (hashing, JWT, token utilities)
"""
import time

import pytest
from jose import jwt

from app.auth.security import (
    create_access_token,
    decode_access_token,
    generate_raw_token,
    hash_password,
    hash_token,
    tokens_equal,
    verify_password,
)
from app.core.config import settings


class TestPasswordHashing:
    def test_hash_roundtrip(self):
        plain = "MyPassword123"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt uses random salt


class TestJwt:
    def test_create_and_decode(self):
        payload = {"sub": "user-id-123", "role": "accountant", "mandant_id": None}
        token = create_access_token(payload)
        decoded = decode_access_token(token)
        assert decoded["sub"] == "user-id-123"
        assert decoded["role"] == "accountant"

    def test_expired_token_raises(self):
        from datetime import datetime, timedelta, timezone
        from jose import JWTError

        expired = jwt.encode(
            {"sub": "x", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
            settings.jwt_secret_key,
            algorithm="HS256",
        )
        with pytest.raises(JWTError):
            decode_access_token(expired)

    def test_tampered_token_raises(self):
        from jose import JWTError

        token = create_access_token({"sub": "x"})
        with pytest.raises(JWTError):
            decode_access_token(token + "tampered")


class TestTokenUtils:
    def test_hash_token_is_64_hex_chars(self):
        raw = generate_raw_token()
        h = hash_token(raw)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_tokens_equal_matches(self):
        raw = generate_raw_token()
        h = hash_token(raw)
        incoming = hash_token(raw)
        assert tokens_equal(incoming, h)

    def test_tokens_equal_rejects_different(self):
        h1 = hash_token(generate_raw_token())
        h2 = hash_token(generate_raw_token())
        assert not tokens_equal(h1, h2)

    def test_generate_raw_token_uniqueness(self):
        tokens = {generate_raw_token() for _ in range(100)}
        assert len(tokens) == 100
