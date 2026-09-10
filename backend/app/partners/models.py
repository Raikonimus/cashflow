from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel, UniqueConstraint


def utcnow() -> datetime:
    return datetime.now(UTC)


class Partner(SQLModel, table=True):
    __tablename__ = "partners"
    __table_args__ = (
        UniqueConstraint("mandant_id", "name", name="uq_partners_mandant_name"),
    )

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    name: str = Field(max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)
    manual_assignment: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PartnerIban(SQLModel, table=True):
    """Eine IBAN eines Partners — eindeutig **je Mandant**, nicht global.

    Die Eindeutigkeit war bis 2026-09-10 global (ADR-008). Das ergab einen blinden
    Fleck: Registrierte Mandant A eine IBAN, uebersprang der Import sie fuer Mandant B
    stillschweigend, und B wurde ueber diese IBAN nie erkannt (Befund A1-3). ADR-018
    kehrt die Regel um; Migration 029 traegt die Spalte nach.

    ``mandant_id`` steht auch am Partner und ist hier eine Kopie. Ohne sie liesse sich
    die Eindeutigkeit nicht in der Datenbank ausdruecken — ein ``UNIQUE`` ueber eine
    Fremdtabelle gibt es nicht. Die Kopie kann nur auseinanderlaufen, wenn ein Partner
    den Mandanten wechselt, und das tut kein Pfad im System.
    """

    __tablename__ = "partner_ibans"
    __table_args__ = (
        UniqueConstraint("mandant_id", "iban", name="uq_partner_ibans_mandant_iban"),
    )

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    partner_id: UUID = Field(foreign_key="partners.id", index=True)
    iban: str = Field(max_length=34)
    created_at: datetime = Field(default_factory=utcnow)


class PartnerAccount(SQLModel, table=True):
    """BLZ + Kontonummer als zusätzlicher Partner-Identifier (neben IBAN).

    Eindeutig **je Mandant**, aus demselben Grund wie bei ``PartnerIban`` — siehe dort
    und ADR-018.

    Zu beachten: ``blz`` ist nullbar, und in SQL kollidieren NULL-Werte nicht. Zwei
    Zeilen mit derselben Kontonummer und ohne BLZ sind deshalb erlaubt. Das war vor der
    Umstellung schon so und ist hier nicht Gegenstand.
    """

    __tablename__ = "partner_accounts"
    __table_args__ = (
        UniqueConstraint(
            "mandant_id",
            "blz",
            "account_number",
            name="uq_partner_accounts_mandant_blz_account",
        ),
    )

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    partner_id: UUID = Field(foreign_key="partners.id", index=True)
    blz: str | None = Field(default=None, max_length=20)  # Bankleitzahl (optional)
    account_number: str = Field(max_length=50)  # Kontonummer
    bic: str | None = Field(
        default=None, max_length=11
    )  # BIC/SWIFT (optional, zur Ergänzung)
    created_at: datetime = Field(default_factory=utcnow)


class PartnerName(SQLModel, table=True):
    __tablename__ = "partner_names"
    __table_args__ = (
        UniqueConstraint("partner_id", "name", name="uq_partner_names_partner_name"),
    )

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    partner_id: UUID = Field(foreign_key="partners.id", index=True)
    name: str = Field(max_length=255)
    created_at: datetime = Field(default_factory=utcnow)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID | None = Field(default=None, foreign_key="mandants.id", index=True)
    event_type: str = Field(max_length=100)
    actor_id: UUID = Field(foreign_key="users.id")
    payload: Any = Field(default={}, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utcnow)
