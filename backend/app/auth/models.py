from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

# Mandant is defined in tenants module (Bolt 003). Re-exported here for
# backward compatibility with auth services that import from app.auth.models.
from app.tenants.models import Mandant as Mandant  # noqa: F401


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserRole(str, Enum):
    admin = "admin"
    mandant_admin = "mandant_admin"
    accountant = "accountant"
    viewer = "viewer"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=254)
    # Nullable until invitation is accepted (story 006-user-invitation)
    password_hash: Optional[str] = Field(default=None)
    # Stored as VARCHAR – enum validation in schemas layer
    role: str = Field(default=UserRole.viewer.value, max_length=50)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class MandantUser(SQLModel, table=True):
    __tablename__ = "mandant_users"

    mandant_id: UUID = Field(foreign_key="mandants.id", primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", primary_key=True)
    created_at: datetime = Field(default_factory=utcnow)


class PasswordResetToken(SQLModel, table=True):
    __tablename__ = "password_reset_tokens"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    # SHA-256 hash of the raw token – never store raw token (ADR-003)
    token_hash: str = Field(index=True, max_length=64)
    expires_at: datetime
    used_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)


class UserInvitation(SQLModel, table=True):
    __tablename__ = "user_invitations"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    # SHA-256 hash of the raw token – never store raw token (ADR-003)
    token_hash: str = Field(index=True, max_length=64)
    expires_at: datetime
    accepted_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
