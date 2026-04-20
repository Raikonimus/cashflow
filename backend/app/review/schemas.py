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


class AdjustReviewRequest(BaseModel):
    service_id: UUID | None = None
    service_type: ServiceType | None = None
    tax_rate: Decimal | None = Field(default=None, ge=Decimal("0.00"), le=Decimal("100.00"))
    erfolgsneutral: bool | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "AdjustReviewRequest":
        if self.service_id is not None and (self.service_type is not None or self.tax_rate is not None or self.erfolgsneutral is not None):
            raise ValueError("service_id cannot be combined with service_type, tax_rate or erfolgsneutral")
        if self.service_id is None and self.service_type is None:
            raise ValueError("either service_id or service_type must be provided")
        return self
