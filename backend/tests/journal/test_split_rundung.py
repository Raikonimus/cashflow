"""Rundung beim Aufteilen einer Buchung auf mehrere Leistungen.

Hintergrund: `_round_money` in `app/services/service.py` wurde mit Befund A2-2 auf
ROUND_HALF_UP festgelegt, weil `quantize()` ohne `rounding=` ROUND_HALF_EVEN aus dem
Kontext erbt und damit eine andere Zahl liefert als die Anzeige.

Der gleichmaessig teilende Zweig hat heute keinen Aufrufer — alle vier Aufrufer von
`_replace_splits` uebergeben genau eine Leistung, und bei count == 1 wird das gerundete
Ergebnis mit null multipliziert. Der Zweig ist trotzdem vorhanden und soll stimmen,
sobald ihn jemand erreicht. Deshalb wird er hier direkt angesteuert: Ohne diesen Test
liesse sich der Rundungsmodus zurueckdrehen, ohne dass irgendetwas rot wird.
"""

from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.models import UserRole
from app.imports.models import JournalLineSplit, utcnow
from app.services.models import Service
from app.services.service import ServiceManagementService
from tests.journal import (
    create_account_db,
    create_import_run_db,
    create_journal_line_db,
    create_mandant,
    create_partner_db,
    create_user,
)

# 10,05 € auf zwei Leistungen ergibt 5,025 € — genau der halbe Cent, an dem sich die
# beiden Rundungsarten unterscheiden: kaufmaennisch 5,03, bankuebliche 5,02.
BETRAG = Decimal("10.05")


async def _service(session: AsyncSession, partner_id, name: str) -> Service:
    now = utcnow()
    service = Service(
        partner_id=partner_id,
        name=name,
        service_type="unknown",
        tax_rate=Decimal("0.00"),
        created_at=now,
        updated_at=now,
    )
    session.add(service)
    await session.commit()
    await session.refresh(service)
    return service


@pytest.mark.asyncio
class TestSplitRundung:
    async def test_halber_cent_wird_kaufmaennisch_gerundet(
        self, db_session: AsyncSession
    ):
        # Die beiden Modi sind an dieser Stelle wirklich verschieden — sonst prueft
        # der Test nichts.
        assert (BETRAG / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != (
            BETRAG / 2
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

        user = await create_user(db_session, "split@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        account = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
        partner = await create_partner_db(db_session, mandant.id, "Lieferant")
        line = await create_journal_line_db(
            db_session, account.id, run.id, partner_id=partner.id, amount=BETRAG
        )
        erste = await _service(db_session, partner.id, "Erste")
        zweite = await _service(db_session, partner.id, "Zweite")

        await ServiceManagementService(db_session)._replace_splits(
            line, [erste.id, zweite.id], "manual"
        )
        await db_session.commit()

        splits = (
            await db_session.exec(
                select(JournalLineSplit).where(
                    JournalLineSplit.journal_line_id == line.id
                )
            )
        ).all()
        betraege = {split.service_id: Decimal(str(split.amount)) for split in splits}

        assert betraege[erste.id] == Decimal("5.03")  # nicht 5.02 (ROUND_HALF_EVEN)
        assert betraege[zweite.id] == Decimal("5.02")

    async def test_die_teile_ergeben_wieder_das_ganze(self, db_session: AsyncSession):
        """Die Rundung darf keinen Cent erzeugen oder verschlucken."""
        user = await create_user(db_session, "split2@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        account = await create_account_db(db_session, mandant.id)
        run = await create_import_run_db(db_session, account.id, mandant.id, user.id)
        partner = await create_partner_db(db_session, mandant.id, "Lieferant")
        line = await create_journal_line_db(
            db_session, account.id, run.id, partner_id=partner.id, amount=BETRAG
        )
        dienste = [
            (await _service(db_session, partner.id, f"Leistung {i}")).id
            for i in range(3)
        ]

        await ServiceManagementService(db_session)._replace_splits(
            line, dienste, "manual"
        )
        await db_session.commit()

        splits = (
            await db_session.exec(
                select(JournalLineSplit).where(
                    JournalLineSplit.journal_line_id == line.id
                )
            )
        ).all()

        assert len(splits) == 3
        assert sum((Decimal(str(s.amount)) for s in splits), Decimal("0")) == BETRAG
