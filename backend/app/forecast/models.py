from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, Numeric
from sqlmodel import Field, SQLModel, UniqueConstraint


def utcnow() -> datetime:
    return datetime.now(UTC)


class ForecastMode(StrEnum):
    #: Der Profiler bestimmt die Regel; Modifikatoren gelten trotzdem.
    auto = "auto"
    #: Regeltyp und Parameter sind von Hand gesetzt.
    manual = "manual"
    #: Diese Leistung wird nicht prognostiziert.
    off = "off"


class ServiceForecastRule(SQLModel, table=True):
    """Übersteuerung der automatisch erkannten Prognoseregel — eine je Leistung.

    Fehlt der Eintrag, gilt `auto` ohne Modifikatoren. Gültigkeitsgrenzen stehen bewusst
    nicht hier, sondern als `valid_from`/`valid_to` an der Leistung selbst; der Profiler
    wertet sie ohnehin aus.
    """

    __tablename__ = "service_forecast_rules"
    __table_args__ = (
        UniqueConstraint("service_id", name="uq_service_forecast_rules_service"),
    )

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    service_id: UUID = Field(foreign_key="services.id", index=True)
    mode: str = Field(default=ForecastMode.auto.value, max_length=10)
    #: Nur bei mode='manual' ausgewertet.
    rule_type: str | None = Field(default=None, max_length=30)
    #: Parameter des Regeltyps, siehe app/forecast/rules.py.
    params: Any = Field(default=None, sa_column=Column(JSON, nullable=True))
    #: Prozentuale Anpassung: +3 für eine Indexierung, -30 für einen Sicherheitsabschlag.
    adjustment_pct: Decimal = Field(
        default=Decimal("0.00"),
        sa_column=Column(Numeric(6, 2), nullable=False, server_default="0"),
    )
    #: Zahlungsverzug in vollen Monaten — feiner geht das Monatsraster nicht her.
    shift_months: int = Field(default=0)
    updated_by: UUID | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ForecastPlannedItem(SQLModel, table=True):
    """Ein bekannter Betrag in einem künftigen Monat einer Leistung.

    Der Posten ersetzt für diesen Monat die Schätzung: Bekanntes schlägt Geschätztes.
    Er wird weder mit Modifikatoren noch mit einer Szenario-Bandbreite versehen — der
    Betrag ist ja bekannt und nicht geschätzt.

    Planposten hängen immer an einer Leistung. Freie Positionen ohne Leistung bräuchten
    eine synthetische Zeile in der Matrix und sind bewusst zurückgestellt.
    """

    __tablename__ = "forecast_planned_items"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    service_id: UUID = Field(foreign_key="services.id", index=True)
    period: str = Field(max_length=7, index=True)  # "YYYY-MM"
    amount: Decimal = Field(sa_column=Column(Numeric(15, 2), nullable=False))
    note: str | None = Field(default=None, max_length=500)
    created_by: UUID | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ForecastSnapshot(SQLModel, table=True):
    """Eingefrorene Liquiditätsprognose zu einem Stichtag — die Planseite von Plan/Ist.

    Prognosewerte werden sonst bewusst nie gespeichert. Hier ist es der Zweck: Nur wenn
    festgehalten ist, was am 15.03. für den Juni erwartet wurde, lässt sich später
    beurteilen, ob die Prognose etwas taugte. Ein Snapshot ist deshalb unveränderlich.

    Festgehalten wird die Monatsebene (Ein-, Auszahlungen, Endsaldo), nicht die einzelne
    Leistung: Verglichen wird gegen die tatsächlichen Kontobewegungen, und die lassen sich
    nur auf dieser Ebene sinnvoll gegenüberstellen.
    """

    __tablename__ = "forecast_snapshots"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    mandant_id: UUID = Field(foreign_key="mandants.id", index=True)
    label: str | None = Field(default=None, max_length=200)
    scenario: str = Field(default="expected", max_length=10)
    #: Stichtag der Prognose. Alles, was danach gebucht wurde, zählt zum Ist.
    as_of: str = Field(max_length=10)  # "YYYY-MM-DD"
    currency: str = Field(default="EUR", max_length=3)
    start_balance: Decimal = Field(sa_column=Column(Numeric(15, 2), nullable=False))
    #: [{"period", "inflow", "outflow", "net", "closing_balance"}] als Zeichenketten,
    #: damit beim Serialisieren nichts an Genauigkeit verloren geht.
    months: Any = Field(default=None, sa_column=Column(JSON, nullable=False))
    created_by: UUID | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow)
