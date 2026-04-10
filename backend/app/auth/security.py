import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(payload: dict) -> str:
    to_encode = payload.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """Decode and verify JWT. Raises jose.JWTError on invalid/expired tokens."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])


def generate_raw_token() -> str:
    """Generate 256-bit URL-safe random token for one-time use."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """SHA-256 hash of a raw token for DB storage (ADR-003)."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def tokens_equal(incoming_hash: str, stored_hash: str) -> bool:
    """Timing-safe comparison of two token hashes (ADR-003)."""
    return hmac.compare_digest(incoming_hash, stored_hash)
