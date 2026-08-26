from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.services.models import ServiceType


class ReviewJournalLineSummary(BaseModel):
    id: UUID
    partner_id: UUID | None
    partner_name: str | None = None
    splits: list[dict] = []
    valuta_date: str
    booking_date: str
    amount: Decimal
    currency: str
    text: str | None
    partner_name_raw: str | None
    partner_iban_raw: str | None

    model_config = {"from_attributes": True}


class ReviewServiceSummary(BaseModel):
    id: UUID
    partner_id: UUID
    partner_name: str | None = None
    name: str
    service_type: ServiceType
    tax_rate: Decimal
    erfolgsneutral: bool = False
    valid_from: date | None
    valid_to: date | None
    service_type_manual: bool
    tax_rate_manual: bool

    model_config = {"from_attributes": True}


class ReviewItemResponse(BaseModel):
    id: UUID
    mandant_id: UUID
    item_type: str
    journal_line_id: Optional[UUID]
    service_id: Optional[UUID]
    context: Any
    status: str
    created_at: datetime
    updated_at: datetime
    resolved_by: Optional[UUID]
    resolved_at: Optional[datetime]
    journal_line: ReviewJournalLineSummary | None = None
    service: ReviewServiceSummary | None = None
    assigned_journal_lines: list[ReviewJournalLineSummary] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PaginatedReviewItemsResponse(BaseModel):
    items: list[ReviewItemResponse]
    total: int
    page: int
    size: int
    pages: int


class ReassignRequest(BaseModel):
    partner_id: UUID


class NewPartnerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ServiceSplitEntry(BaseModel):
    service_id: UUID
    amount: Decimal


class AdjustReviewRequest(BaseModel):
    service_id: UUID | None = None
    service_type: ServiceType | None = None
    tax_rate: Decimal | None = Field(default=None, ge=Decimal("0.00"), le=Decimal("100.00"))
    erfolgsneutral: bool | None = None
    splits: list[ServiceSplitEntry] | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "AdjustReviewRequest":
        has_service_id = self.service_id is not None
        has_service_type = self.service_type is not None
        has_splits = bool(self.splits)

        if has_splits and (has_service_id or has_service_type):
            raise ValueError("splits cannot be combined with service_id or service_type")
        if has_splits and len(self.splits) < 2:  # type: ignore[arg-type]
            raise ValueError("splits must contain at least 2 entries")
        if has_service_id and (has_service_type or self.tax_rate is not None or self.erfolgsneutral is not None):
            raise ValueError("service_id cannot be combined with service_type, tax_rate or erfolgsneutral")
        if not has_service_id and not has_service_type and not has_splits:
            raise ValueError("either service_id, service_type, or splits must be provided")
        return self


class UnidentifiedGroupResponse(BaseModel):
    """Eine Gruppe offener no_partner_identified-Items mit gleichem Händler-Kern."""

    key: str
    suggested_pattern: str
    suggested_partner_name: str
    line_count: int
    total_amount: Decimal
    first_date: str
    last_date: str
    sample_texts: list[str]
    item_ids: list[UUID]


class UnidentifiedGroupsResponse(BaseModel):
    groups: list[UnidentifiedGroupResponse]
    total_open: int
    grouped: int


class ResolveUnidentifiedGroupRequest(BaseModel):
    item_ids: list[UUID] = Field(min_length=1)
    pattern: str = Field(min_length=2, max_length=500)
    service_name: str = Field(min_length=1, max_length=255)
    partner_id: UUID | None = None
    partner_name: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_partner(self) -> "ResolveUnidentifiedGroupRequest":
        if self.partner_id is None and not (self.partner_name or "").strip():
            raise ValueError("Entweder partner_id oder partner_name angeben")
        return self


class ResolveUnidentifiedGroupResponse(BaseModel):
    partner_id: UUID
    partner_name: str
    service_id: UUID
    matcher_id: UUID
    resolved_items: int
    assigned_lines: int
