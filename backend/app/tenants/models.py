from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON as SAJSON
from sqlalchemy import Column, Numeric
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Mandant(SQLModel, table=True):
    """Full Mandant entity. Stub was introduced in Bolt 001 (auth/models.py)."""

    __tablename__ = "mandants"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=255)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Account(SQLModel, table=True):
    __tablename__ = "accounts"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    name: str = Field(max_length=255)
    iban: str | None = Field(default=None, max_length=34, nullable=True)
    currency: str = Field(max_length=3, default="EUR")
    # Kontostand vor der ersten importierten Buchung — Basis der Liquiditätsrechnung
    opening_balance: Decimal = Field(
        default=Decimal("0.00"),
        sa_column=Column(Numeric(15, 2), nullable=False, server_default="0"),
    )
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class AccountExcludedIdentifier(SQLModel, table=True):
    """IBAN oder Kontonummer, die für dieses Konto NICHT zur Partneridentifikation verwendet werden darf."""

    __tablename__ = "account_excluded_identifiers"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    account_id: UUID = Field(foreign_key="accounts.id", index=True)
    identifier_type: str = Field(max_length=20)  # "iban" | "account_number"
    value: str = Field(max_length=50)
    label: str | None = Field(default=None, max_length=255)
    created_at: datetime = Field(default_factory=utcnow)


class ColumnMappingConfig(SQLModel, table=True):
    __tablename__ = "column_mapping_configs"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    account_id: UUID = Field(foreign_key="accounts.id", unique=True)
    valuta_date_col: str = Field(max_length=100)
    booking_date_col: str = Field(max_length=100)
    amount_col: str = Field(max_length=100)
    partner_iban_col: str | None = Field(default=None, max_length=100)
    partner_name_col: str | None = Field(default=None, max_length=100)
    description_col: str | None = Field(default=None, max_length=100)
    # JSON list of {source, target, sort_order} – wenn gesetzt, übersteuert die Legacy-Felder oben
    column_assignments: Any | None = Field(
        default=None, sa_column=Column(SAJSON, nullable=True)
    )
    decimal_separator: str = Field(max_length=1, default=",")
    date_format: str = Field(default="%d.%m.%Y")
    encoding: str = Field(max_length=20, default="utf-8")
    delimiter: str = Field(max_length=5, default=";")
    skip_rows: int = Field(default=0)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
