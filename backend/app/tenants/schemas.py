from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ─── Mandant ────────────────────────────────────────────────────────────────

class CreateMandantRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class UpdateMandantRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)


class MandantResponse(BaseModel):
    id: UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


CleanupMode = Literal["delete_mandant", "delete_data", "selected"]
CleanupScope = Literal["journal_data", "partner_service_data", "audit_data", "review_data"]


class CleanupPreviewItem(BaseModel):
    key: str
    label: str
    count: int


class CleanupPreviewSection(BaseModel):
    key: str
    label: str
    description: str
    items: list[CleanupPreviewItem]


class MandantCleanupPreviewResponse(BaseModel):
    mandant_id: UUID
    mandant_name: str
    delete_mandant: CleanupPreviewSection
    delete_data: CleanupPreviewSection
    selectable_sections: list[CleanupPreviewSection]


class ExecuteMandantCleanupRequest(BaseModel):
    mode: CleanupMode
    scopes: list[CleanupScope] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scopes(self) -> "ExecuteMandantCleanupRequest":
        if self.mode == "selected" and not self.scopes:
            raise ValueError("scopes is required when mode is 'selected'")
        if self.mode != "selected" and self.scopes:
            raise ValueError("scopes is only allowed when mode is 'selected'")
        return self


class ExecuteMandantCleanupResponse(BaseModel):
    mode: CleanupMode
    deleted_mandant: bool
    executed_sections: list[str]
    items: list[CleanupPreviewItem]


# ─── Account ─────────────────────────────────────────────────────────────────

class CreateAccountRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    iban: Optional[str] = Field(default=None, max_length=34)
    currency: str = Field(default="EUR", max_length=3)


class UpdateAccountRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    iban: Optional[str] = Field(default=None, max_length=34)
    is_active: Optional[bool] = None


class AccountResponse(BaseModel):
    id: UUID
    mandant_id: UUID
    name: str
    iban: Optional[str] = None
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    has_column_mapping: bool = False

    model_config = {"from_attributes": True}


# ─── ColumnMappingConfig ─────────────────────────────────────────────────────

# Erlaubte Zielfelder für eine CSV-Spalte
ColumnTarget = Literal[
    "valuta_date",
    "booking_date",
    "amount",
    "currency",
    "partner_iban",
    "partner_name",
    "partner_account",
    "partner_blz",
    "partner_bic",
    "description",
    "unused",
]

REQUIRED_TARGETS = {"valuta_date", "booking_date", "amount"}


class ColumnAssignment(BaseModel):
    """Zuordnung einer einzelnen CSV-Spalte zu einem Zielfeld."""
    source: str = Field(min_length=1, max_length=200, description="Name der CSV-Spalte")
    target: ColumnTarget = Field(description="Zielfeld (oder 'unused')")
    sort_order: int = Field(ge=0, description="Reihenfolge bei Mehrfach-Belegung desselben Zielfelds")
    duplicate_check: bool = Field(
        default=False,
        description="Wenn true, wird diese CSV-Spalte für die Dublettenprüfung verwendet.",
    )


class ColumnMappingRequest(BaseModel):
    # ── Neue Assignment-basierte Konfiguration ──────────────────────────────
    # Wenn angegeben, übersteuert diese Liste die sechs Legacy-Felder unten.
    # Jede CSV-Spalte muss exakt einmal vorkommen.
    column_assignments: Optional[list[ColumnAssignment]] = None

    # ── Legacy-Felder (rückwärtskompatibel) ────────────────────────────────
    valuta_date_col: Optional[str] = Field(default=None, max_length=100)
    booking_date_col: Optional[str] = Field(default=None, max_length=100)
    amount_col: Optional[str] = Field(default=None, max_length=100)
    partner_iban_col: Optional[str] = Field(default=None, max_length=100)
    partner_name_col: Optional[str] = Field(default=None, max_length=100)
    description_col: Optional[str] = Field(default=None, max_length=100)

    # ── Parser-Konfiguration ────────────────────────────────────────────────
    decimal_separator: str = Field(default=",", max_length=1)
    date_format: str = Field(default="%d.%m.%Y", max_length=50)
    encoding: str = Field(default="utf-8", max_length=20)
    delimiter: str = Field(default=";", max_length=5)
    skip_rows: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def check_required_fields(self) -> "ColumnMappingRequest":
        if self.column_assignments is not None:
            targets = {a.target for a in self.column_assignments}
            missing = REQUIRED_TARGETS - targets
            if missing:
                raise ValueError(
                    f"Fehlende Pflichtfelder in column_assignments: {sorted(missing)}"
                )
            if not any(a.duplicate_check for a in self.column_assignments):
                raise ValueError(
                    "Mindestens eine CSV-Spalte muss für die Dublettenprüfung ausgewählt sein"
                )
        else:
            if not self.valuta_date_col:
                raise ValueError("valuta_date_col ist Pflichtfeld (oder column_assignments verwenden)")
            if not self.booking_date_col:
                raise ValueError("booking_date_col ist Pflichtfeld (oder column_assignments verwenden)")
            if not self.amount_col:
                raise ValueError("amount_col ist Pflichtfeld (oder column_assignments verwenden)")
        return self


class ColumnMappingResponse(BaseModel):
    id: UUID
    account_id: UUID
    column_assignments: Optional[list[ColumnAssignment]] = None
    valuta_date_col: Optional[str] = None
    booking_date_col: Optional[str] = None
    amount_col: Optional[str] = None
    partner_iban_col: Optional[str] = None
    partner_name_col: Optional[str] = None
    description_col: Optional[str] = None
    decimal_separator: str
    date_format: str
    encoding: str
    delimiter: str
    skip_rows: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── CSV-Vorschau ─────────────────────────────────────────────────────────────

class CsvPreviewResponse(BaseModel):
    """Gibt die erkannten Spaltennamen und Beispielzeilen aus dem CSV-Header zurück."""
    columns: list[str]
    detected_delimiter: str | None = None
    detected_encoding: str | None = None
    sample_rows: list[dict[str, str]] = []


# ─── Remapping ───────────────────────────────────────────────────────────────

class RemappingTriggerResponse(BaseModel):
    message: str
    account_id: UUID


# ─── Excluded Identifiers ─────────────────────────────────────────────────────

class ExcludedIdentifierCreate(BaseModel):
    identifier_type: Literal["iban", "account_number"]
    value: str = Field(min_length=1, max_length=50)
    label: Optional[str] = Field(default=None, max_length=255)


class ExcludedIdentifierResponse(BaseModel):
    id: UUID
    account_id: UUID
    identifier_type: str
    value: str
    label: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApplyExcludedResponse(BaseModel):
    affected: int
    message: str
