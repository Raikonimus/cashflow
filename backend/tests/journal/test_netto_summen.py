"""Konsistenz der ausgewiesenen Nettosummen.

Netto entsteht als ``brutto / (1 + Steuersatz/100)`` und hat damit fast immer mehr
als zwei Nachkommastellen. Gerundet wird erst bei der Ausgabe. Dadurch kann die
Summe der angezeigten Monatswerte von der angezeigten Jahressumme abweichen —
und tut es auch.
"""
from decimal import Decimal

from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import UserRole
from app.imports.models import JournalLineSplit
from app.journal.service import JournalService
from app.services.models import Service
from tests.journal import (  # noqa: F401
    assign_user_to_mandant,
    client,
    create_account_db,
    create_import_run_db,
    create_journal_line_db,
    create_mandant,
    create_partner_db,
    create_user,
    db_session,
    setup_db,
    utcnow,
)

MONATE = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


async def _matrix_mit_gleichem_monatsbetrag(
    db_session: AsyncSession, brutto: str, steuersatz: str
):
    """Zwoelf gleiche Monatsbuchungen auf einer Leistung — der einfachste Fall."""
    user = await create_user(db_session, "netto@test.com", UserRole.viewer)
    mandant = await create_mandant(db_session)
    await assign_user_to_mandant(db_session, user, mandant)
    account = await create_account_db(db_session, mandant.id)
    run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
    partner = await create_partner_db(db_session, mandant.id, "Lieferant")
    service = Service(
        partner_id=partner.id,
        name="Miete",
        service_type="supplier",
        tax_rate=steuersatz,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db_session.add(service)
    await db_session.commit()
    await db_session.refresh(service)

    for monat in range(1, 13):
        line = await create_journal_line_db(
            db_session,
            account.id,
            run.id,
            partner_id=partner.id,
            valuta_date=f"2025-{monat:02d}-15",
            amount=Decimal(brutto),
        )
        db_session.add(
            JournalLineSplit(
                journal_line_id=line.id,
                service_id=service.id,
                amount=line.amount,
                assignment_mode="auto",
                amount_consistency_ok=False,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
    await db_session.commit()

    return await JournalService(db_session).get_income_expense_matrix(mandant.id, 2025)


def _zeile(matrix):
    for section in matrix.sections.values():
        for gruppe in section.groups:
            for row in gruppe.services:
                if row.service_name == "Miete":
                    return row
    raise AssertionError("Leistung nicht in der Matrix")


async def test_brutto_addiert_sich_zur_jahressumme(db_session: AsyncSession):
    """Die Gegenprobe: brutto ist zweistellig und geht glatt auf."""
    matrix = await _matrix_mit_gleichem_monatsbetrag(db_session, "100.00", "20.00")
    row = _zeile(matrix)

    monate = sum(Decimal(getattr(row.cells, m).gross) for m in MONATE)
    assert monate == Decimal(row.cells.year_total.gross) == Decimal("1200.00")


async def test_netto_addiert_sich_zur_jahressumme(db_session: AsyncSession):
    """12 x 100,00 brutto bei 20 %: jeder Monat 83,33 netto, die Jahreszelle 999,96.

    Nicht 1.000,00 — das waere jahresbrutto/divisor. Die Jahreszelle ist bewusst die
    Summe der angezeigten Monate, damit die Spalte aufgeht und der Excel-Export,
    der die Monate per Formel summiert, dasselbe Ergebnis liefert.
    """
    matrix = await _matrix_mit_gleichem_monatsbetrag(db_session, "100.00", "20.00")
    row = _zeile(matrix)

    monate = sum(Decimal(getattr(row.cells, m).net) for m in MONATE)
    jahr = Decimal(row.cells.year_total.net)

    assert monate == jahr, (
        f"Monate summieren sich auf {monate}, die Jahreszelle zeigt {jahr} "
        f"— Differenz {monate - jahr}"
    )
