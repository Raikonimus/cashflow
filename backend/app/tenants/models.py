from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column
from sqlalchemy import JSON as SAJSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Mandant(SQLModel, table=True):
    """Full Mandant entity. Stub was introduced in Bolt 001 (auth/models.py)."""

    __tablename__ = "mandants"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=255)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Account(SQLModel, table=True):
    __tablename__ = "accounts"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    name: str = Field(max_length=255)
    iban: Optional[str] = Field(default=None, max_length=34, nullable=True)
    currency: str = Field(max_length=3, default="EUR")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class AccountExcludedIdentifier(SQLModel, table=True):
    """IBAN oder Kontonummer, die für dieses Konto NICHT zur Partneridentifikation verwendet werden darf."""

    __tablename__ = "account_excluded_identifiers"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    account_id: UUID = Field(foreign_key="accounts.id", index=True)
    identifier_type: str = Field(max_length=20)  # "iban" | "account_number"
    value: str = Field(max_length=50)
    label: Optional[str] = Field(default=None, max_length=255)
    created_at: datetime = Field(default_factory=utcnow)


class ColumnMappingConfig(SQLModel, table=True):
    __tablename__ = "column_mapping_configs"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    account_id: UUID = Field(foreign_key="accounts.id", unique=True)
    valuta_date_col: str = Field(max_length=100)
    booking_date_col: str = Field(max_length=100)
    amount_col: str = Field(max_length=100)
    partner_iban_col: Optional[str] = Field(default=None, max_length=100)
    partner_name_col: Optional[str] = Field(default=None, max_length=100)
    description_col: Optional[str] = Field(default=None, max_length=100)
    # JSON list of {source, target, sort_order} – wenn gesetzt, übersteuert die Legacy-Felder oben
    column_assignments: Optional[Any] = Field(default=None, sa_column=Column(SAJSON, nullable=True))
    decimal_separator: str = Field(max_length=1, default=",")
    date_format: str = Field(default="%d.%m.%Y")
    encoding: str = Field(max_length=20, default="utf-8")
    delimiter: str = Field(max_length=5, default=";")
    skip_rows: int = Field(default=0)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
