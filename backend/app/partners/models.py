from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel, UniqueConstraint


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Partner(SQLModel, table=True):
    __tablename__ = "partners"
    __table_args__ = (UniqueConstraint("mandant_id", "name", name="uq_partners_mandant_name"),)

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    name: str = Field(max_length=255)
    display_name: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PartnerIban(SQLModel, table=True):
    __tablename__ = "partner_ibans"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    partner_id: UUID = Field(foreign_key="partners.id", index=True)
    iban: str = Field(max_length=34, unique=True)
    created_at: datetime = Field(default_factory=utcnow)


class PartnerAccount(SQLModel, table=True):
    """BLZ + Kontonummer als zusätzlicher Partner-Identifier (neben IBAN)."""
    __tablename__ = "partner_accounts"
    __table_args__ = (
        UniqueConstraint("blz", "account_number", name="uq_partner_accounts_blz_account"),
    )

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    partner_id: UUID = Field(foreign_key="partners.id", index=True)
    blz: Optional[str] = Field(default=None, max_length=20)      # Bankleitzahl (optional)
    account_number: str = Field(max_length=50)                    # Kontonummer
    bic: Optional[str] = Field(default=None, max_length=11)      # BIC/SWIFT (optional, zur Ergänzung)
    created_at: datetime = Field(default_factory=utcnow)


class PartnerName(SQLModel, table=True):
    __tablename__ = "partner_names"
    __table_args__ = (UniqueConstraint("partner_id", "name", name="uq_partner_names_partner_name"),)

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    partner_id: UUID = Field(foreign_key="partners.id", index=True)
    name: str = Field(max_length=255)
    created_at: datetime = Field(default_factory=utcnow)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    mandant_id: Optional[UUID] = Field(default=None, foreign_key="mandants.id", index=True)
    event_type: str = Field(max_length=100)
    actor_id: UUID = Field(foreign_key="users.id")
    payload: Any = Field(default={}, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utcnow)
