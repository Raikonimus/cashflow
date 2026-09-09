from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, Numeric
from sqlmodel import Field, SQLModel, UniqueConstraint


def utcnow() -> datetime:
    return datetime.now(UTC)


class ImportStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ImportRun(SQLModel, table=True):
    __tablename__ = "import_runs"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    account_id: UUID = Field(foreign_key="accounts.id", index=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    user_id: UUID = Field(foreign_key="users.id")
    filename: str = Field(max_length=255)
    row_count: int = Field(default=0)
    skipped_count: int = Field(default=0)
    error_count: int = Field(default=0)
    status: str = Field(default=ImportStatus.pending.value, max_length=20)
    error_details: Any = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = Field(default=None)


class JournalLine(SQLModel, table=True):
    __tablename__ = "journal_lines"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    account_id: UUID = Field(foreign_key="accounts.id", index=True)
    import_run_id: UUID = Field(foreign_key="import_runs.id", index=True)
    partner_id: UUID | None = Field(default=None, foreign_key="partners.id", index=True)
    valuta_date: str = Field(max_length=10)  # stored as ISO 8601 string DATE
    booking_date: str = Field(max_length=10)  # stored as ISO 8601 string DATE
    amount: Decimal = Field(sa_column=Column(Numeric(15, 2), nullable=False))
    currency: str = Field(default="EUR", max_length=3)
    text: str | None = Field(default=None, max_length=1000)
    partner_name_raw: str | None = Field(default=None, max_length=500)
    partner_iban_raw: str | None = Field(default=None, max_length=34)
    partner_account_raw: str | None = Field(default=None, max_length=50)  # Kontonummer
    partner_blz_raw: str | None = Field(default=None, max_length=20)  # Bankleitzahl
    partner_bic_raw: str | None = Field(default=None, max_length=11)  # BIC/SWIFT
    unmapped_data: Any = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=utcnow)


class JournalLineSplit(SQLModel, table=True):
    __tablename__ = "journal_line_splits"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    journal_line_id: UUID = Field(foreign_key="journal_lines.id", index=True)
    service_id: UUID = Field(foreign_key="services.id", index=True)
    amount: Decimal = Field(sa_column=Column(Numeric(15, 2), nullable=False))
    assignment_mode: str = Field(max_length=20)  # 'auto' | 'manual'
    amount_consistency_ok: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ReviewItem(SQLModel, table=True):
    __tablename__ = "review_items"
    __table_args__ = (
        UniqueConstraint(
            "journal_line_id",
            "item_type",
            name="uq_review_items_journal_line_item_type",
        ),
        UniqueConstraint(
            "service_id", "item_type", name="uq_review_items_service_item_type"
        ),
    )

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    item_type: str = Field(max_length=50)
    journal_line_id: UUID | None = Field(
        default=None, foreign_key="journal_lines.id", index=True
    )
    service_id: UUID | None = Field(default=None, foreign_key="services.id", index=True)
    context: Any = Field(default=None, sa_column=Column(JSON, nullable=True))
    status: str = Field(default="open", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    resolved_by: UUID | None = Field(default=None, foreign_key="users.id")
    resolved_at: datetime | None = Field(default=None)
