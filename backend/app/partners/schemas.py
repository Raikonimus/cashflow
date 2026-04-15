from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.models import ServiceType


# ─── Partner ──────────────────────────────────────────────────────────────────

class CreatePartnerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    iban: Optional[str] = Field(default=None, max_length=34)


class PartnerIbanResponse(BaseModel):
    id: UUID
    iban: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PartnerAccountResponse(BaseModel):
    id: UUID
    blz: str | None
    account_number: str
    bic: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PartnerNameResponse(BaseModel):
    id: UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PartnerListItem(BaseModel):
    id: UUID
    name: str
    display_name: str | None = None
    is_active: bool
    service_types: list[ServiceType] = Field(default_factory=list)
    iban_count: int
    name_count: int
    journal_line_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PartnerDetailResponse(BaseModel):
    id: UUID
    mandant_id: UUID
    name: str
    display_name: str | None = None
    is_active: bool
    ibans: list[PartnerIbanResponse]
    accounts: list[PartnerAccountResponse]
    names: list[PartnerNameResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedPartnersResponse(BaseModel):
    items: list[PartnerListItem]
    total: int
    page: int
    size: int
    pages: int


class PartnerNeighbor(BaseModel):
    id: UUID
    name: str

    model_config = {"from_attributes": True}


class PartnerNeighborsResponse(BaseModel):
    prev: PartnerNeighbor | None = None
    next: PartnerNeighbor | None = None


# ─── IBAN ─────────────────────────────────────────────────────────────────────

class UpdatePartnerRequest(BaseModel):
    display_name: str | None = None  # leer/None löscht den Anzeigenamen


class AddIbanRequest(BaseModel):
    iban: str = Field(min_length=15, max_length=34)


# ─── Account (BLZ + Kontonummer) ──────────────────────────────────────────────

class AddAccountRequest(BaseModel):
    account_number: str = Field(min_length=1, max_length=50)
    blz: str | None = Field(default=None, max_length=20)
    bic: str | None = Field(default=None, max_length=11)


class AccountPreviewLineItem(BaseModel):
    journal_line_id: UUID
    partner_name_raw: str | None
    current_partner_name: str | None
    booking_date: str
    valuta_date: str
    amount: Decimal
    currency: str
    text: str | None
    already_assigned: bool = False


class AccountPreviewResponse(BaseModel):
    matched_lines: list[AccountPreviewLineItem]
    total: int


# ─── Name ─────────────────────────────────────────────────────────────────────

class AddNameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


# ─── Merge ────────────────────────────────────────────────────────────────────

class MergeRequest(BaseModel):
    source_partner_id: UUID
    target_partner_id: UUID


class MergeResponse(BaseModel):
    target: PartnerDetailResponse
    lines_reassigned: int
    audit_log_id: UUID


# ─── Audit Log ────────────────────────────────────────────────────────────────

class AuditLogEntryResponse(BaseModel):
    id: UUID
    event_type: str
    actor_id: UUID
    payload: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedAuditLogResponse(BaseModel):
    items: list[AuditLogEntryResponse]
    total: int
    page: int
    size: int
    pages: int
