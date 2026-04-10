from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, Numeric
from sqlmodel import Field, SQLModel, UniqueConstraint


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ServiceType(str, Enum):
    customer = "customer"
    supplier = "supplier"
    employee = "employee"
    authority = "authority"
    unknown = "unknown"


class ServiceMatcherType(str, Enum):
    string = "string"
    regex = "regex"


class KeywordTargetType(str, Enum):
    employee = "employee"
    authority = "authority"


BASE_SERVICE_NAME = "Basisleistung"


class Service(SQLModel, table=True):
    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("partner_id", "name", name="uq_services_partner_name"),
    )

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    partner_id: UUID = Field(foreign_key="partners.id", index=True)
    name: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    service_type: str = Field(default=ServiceType.unknown.value, max_length=20)
    tax_rate: Decimal = Field(default=Decimal("20.00"), sa_column=Column(Numeric(5, 2), nullable=False))
    valid_from: date | None = Field(default=None)
    valid_to: date | None = Field(default=None)
    is_base_service: bool = Field(default=False)
    service_type_manual: bool = Field(default=False)
    tax_rate_manual: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ServiceMatcher(SQLModel, table=True):
    __tablename__ = "service_matchers"
    __table_args__ = (
        UniqueConstraint("service_id", "pattern", "pattern_type", name="uq_service_matchers_service_pattern"),
    )

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    service_id: UUID = Field(foreign_key="services.id", index=True)
    pattern: str = Field(max_length=500)
    pattern_type: str = Field(max_length=10)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ServiceTypeKeyword(SQLModel, table=True):
    __tablename__ = "service_type_keywords"
    __table_args__ = (
        UniqueConstraint(
            "mandant_id",
            "pattern",
            "pattern_type",
            "target_service_type",
            name="uq_service_type_keywords_scope_pattern",
        ),
    )

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID | None = Field(default=None, foreign_key="mandants.id", index=True)
    pattern: str = Field(max_length=500)
    pattern_type: str = Field(max_length=10)
    target_service_type: str = Field(max_length=20)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
