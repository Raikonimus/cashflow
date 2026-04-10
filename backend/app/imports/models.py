from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON, Numeric
from sqlmodel import Field, SQLModel, UniqueConstraint


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImportStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ImportRun(SQLModel, table=True):
    __tablename__ = "import_runs"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
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
    completed_at: Optional[datetime] = Field(default=None)


class JournalLine(SQLModel, table=True):
    __tablename__ = "journal_lines"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    account_id: UUID = Field(foreign_key="accounts.id", index=True)
    import_run_id: UUID = Field(foreign_key="import_runs.id", index=True)
    partner_id: Optional[UUID] = Field(default=None, foreign_key="partners.id", index=True)
    service_id: Optional[UUID] = Field(default=None, foreign_key="services.id", index=True)
    service_assignment_mode: Optional[str] = Field(default=None, max_length=20)
    valuta_date: str = Field(max_length=10)   # stored as ISO 8601 string DATE
    booking_date: str = Field(max_length=10)  # stored as ISO 8601 string DATE
    amount: Decimal = Field(sa_column=Column(Numeric(15, 2), nullable=False))
    currency: str = Field(default="EUR", max_length=3)
    text: Optional[str] = Field(default=None, max_length=1000)
    partner_name_raw: Optional[str] = Field(default=None, max_length=500)
    partner_iban_raw: Optional[str] = Field(default=None, max_length=34)
    partner_account_raw: Optional[str] = Field(default=None, max_length=50)  # Kontonummer
    partner_blz_raw: Optional[str] = Field(default=None, max_length=20)      # Bankleitzahl
    partner_bic_raw: Optional[str] = Field(default=None, max_length=11)      # BIC/SWIFT
    unmapped_data: Any = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=utcnow)


class ReviewItem(SQLModel, table=True):
    __tablename__ = "review_items"
    __table_args__ = (
        UniqueConstraint("journal_line_id", "item_type", name="uq_review_items_journal_line_item_type"),
        UniqueConstraint("service_id", "item_type", name="uq_review_items_service_item_type"),
    )

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    item_type: str = Field(max_length=50)
    journal_line_id: Optional[UUID] = Field(default=None, foreign_key="journal_lines.id", index=True)
    service_id: Optional[UUID] = Field(default=None, foreign_key="services.id", index=True)
    context: Any = Field(default=None, sa_column=Column(JSON, nullable=True))
    status: str = Field(default="open", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    resolved_by: Optional[UUID] = Field(default=None, foreign_key="users.id")
    resolved_at: Optional[datetime] = Field(default=None)
