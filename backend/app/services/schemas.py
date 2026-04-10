from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.services.models import KeywordTargetType, ServiceMatcherType, ServiceType


class ServiceMatcherResponse(BaseModel):
    id: UUID
    pattern: str
    pattern_type: ServiceMatcherType
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ServiceResponse(BaseModel):
    id: UUID
    partner_id: UUID
    name: str
    description: str | None
    service_type: ServiceType
    tax_rate: Decimal
    valid_from: date | None
    valid_to: date | None
    is_base_service: bool
    service_type_manual: bool
    tax_rate_manual: bool
    created_at: datetime
    updated_at: datetime
    matchers: list[ServiceMatcherResponse] = []


class CreateServiceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    service_type: ServiceType = ServiceType.unknown
    tax_rate: Decimal = Field(default=Decimal("20.00"), ge=Decimal("0.00"), le=Decimal("100.00"))
    valid_from: date | None = None
    valid_to: date | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "CreateServiceRequest":
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must be before or equal to valid_to")
        return self


class UpdateServiceRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    service_type: ServiceType | None = None
    tax_rate: Decimal | None = Field(default=None, ge=Decimal("0.00"), le=Decimal("100.00"))
    valid_from: date | None = None
    valid_to: date | None = None
    service_type_manual: bool | None = None
    tax_rate_manual: bool | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "UpdateServiceRequest":
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must be before or equal to valid_to")
        return self


class CreateServiceMatcherRequest(BaseModel):
    pattern: str = Field(min_length=1, max_length=500)
    pattern_type: ServiceMatcherType


class UpdateServiceMatcherRequest(BaseModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=500)
    pattern_type: ServiceMatcherType | None = None


class ServiceTypeKeywordResponse(BaseModel):
    id: UUID
    mandant_id: UUID | None
    pattern: str
    pattern_type: ServiceMatcherType
    target_service_type: KeywordTargetType
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SystemServiceTypeKeywordResponse(BaseModel):
    pattern: str
    pattern_type: ServiceMatcherType
    target_service_type: KeywordTargetType


class ServiceTypeKeywordListResponse(BaseModel):
    items: list[ServiceTypeKeywordResponse]
    system_defaults: list[SystemServiceTypeKeywordResponse]


class CreateServiceTypeKeywordRequest(BaseModel):
    pattern: str = Field(min_length=1, max_length=500)
    pattern_type: ServiceMatcherType
    target_service_type: KeywordTargetType


class UpdateServiceTypeKeywordRequest(BaseModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=500)
    pattern_type: ServiceMatcherType | None = None
    target_service_type: KeywordTargetType | None = None
