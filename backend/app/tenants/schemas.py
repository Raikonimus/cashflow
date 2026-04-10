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
    iban: Optional[str]
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
    valuta_date_col: Optional[str]
    booking_date_col: Optional[str]
    amount_col: Optional[str]
    partner_iban_col: Optional[str]
    partner_name_col: Optional[str]
    description_col: Optional[str]
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
    label: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ApplyExcludedResponse(BaseModel):
    affected: int
    message: str
