from decimal import Decimal
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


# ─── Journal Lines ────────────────────────────────────────────────────────────

class JournalLineResponse(BaseModel):
    id: UUID
    account_id: UUID
    import_run_id: UUID
    partner_id: Optional[UUID]
    service_id: Optional[UUID] = None
    service_name: Optional[str] = None
    service_assignment_mode: Optional[str] = None
    partner_name: Optional[str] = None
    valuta_date: str
    booking_date: str
    amount: Decimal
    currency: str
    text: Optional[str]
    partner_name_raw: Optional[str]
    partner_iban_raw: Optional[str]
    partner_account_raw: Optional[str] = None
    partner_blz_raw: Optional[str] = None
    partner_bic_raw: Optional[str] = None
    unmapped_data: Optional[Any] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedJournalResponse(BaseModel):
    items: list[JournalLineResponse]
    total: int
    page: int
    size: int
    pages: int


class JournalYearsResponse(BaseModel):
    years: list[int]


# ─── Bulk-Assign ──────────────────────────────────────────────────────────────

class BulkAssignRequest(BaseModel):
    line_ids: list[UUID]
    partner_id: UUID


class AssignServiceRequest(BaseModel):
    service_id: UUID


SORTABLE_COLUMNS = {"valuta_date", "booking_date", "amount", "partner_name", "text", "service_name"}


class BulkAssignResponse(BaseModel):
    assigned: int
    skipped: int
