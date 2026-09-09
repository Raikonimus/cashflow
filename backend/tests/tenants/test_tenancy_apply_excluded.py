"""Mandantentrennung des Endpunkts `excluded-identifiers/apply`.

Gleiches Muster wie bei den Import-Endpunkten: `require_mandant_access` prueft die
`mandant_id` aus dem Pfad, nicht die `account_id`. Dieser Pfad *schreibt* — er ordnet
Buchungszeilen neu zu. Ohne Pruefung des Kontos wuerden fremde Buchungen umgeschrieben.
"""

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import UserRole
from app.imports.models import ImportRun, JournalLine, utcnow
from app.partners.models import Partner, PartnerIban
from app.tenants.models import Account, AccountExcludedIdentifier
from tests.tenants.conftest import (  # noqa: F401
    assign_user_to_mandant,
    create_mandant,
    create_user,
    get_auth_token,
)


async def create_account_db(
    session: AsyncSession, mandant_id, name: str = "Konto"
) -> Account:
    now = utcnow()
    account = Account(
        mandant_id=mandant_id, name=name, currency="EUR", created_at=now, updated_at=now
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


IBAN = "DE89370400440532013000"


async def test_fremdes_konto_kann_nicht_neu_zugeordnet_werden(
    db_session: AsyncSession, client: AsyncClient
):
    eigener = await create_mandant(db_session, name="Mandant A")
    fremder = await create_mandant(db_session, name="Mandant B")
    nutzer = await create_user(
        db_session, email="a@example.com", role=UserRole.accountant
    )
    await assign_user_to_mandant(db_session, nutzer, eigener)

    fremdes_konto = await create_account_db(db_session, fremder.id, name="Konto B")
    now = utcnow()
    fremder_partner = Partner(
        mandant_id=fremder.id,
        name="Partner B",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(fremder_partner)
    await db_session.flush()
    db_session.add(
        PartnerIban(partner_id=fremder_partner.id, iban=IBAN, created_at=now)
    )
    lauf = ImportRun(
        account_id=fremdes_konto.id,
        mandant_id=fremder.id,
        user_id=nutzer.id,
        filename="b.csv",
        status="completed",
        created_at=now,
    )
    db_session.add(lauf)
    await db_session.flush()
    zeile = JournalLine(
        account_id=fremdes_konto.id,
        import_run_id=lauf.id,
        partner_id=fremder_partner.id,
        valuta_date="2026-01-02",
        booking_date="2026-01-02",
        amount=-100,
        currency="EUR",
        text="Zahlung",
        partner_iban_raw=IBAN,
        created_at=now,
    )
    db_session.add(zeile)
    db_session.add(
        AccountExcludedIdentifier(
            account_id=fremdes_konto.id,
            identifier_type="iban",
            value=IBAN,
            created_at=now,
        )
    )
    await db_session.commit()
    await db_session.refresh(zeile)
    zeile_id = zeile.id
    partner_vorher = zeile.partner_id

    token = await get_auth_token(client, nutzer)
    resp = await client.post(
        f"/api/v1/mandants/{eigener.id}/accounts/{fremdes_konto.id}"
        f"/excluded-identifiers/apply",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code in (
        403,
        404,
    ), f"Fremdes Konto wurde verarbeitet: {resp.status_code} {resp.text}"

    danach = (
        await db_session.exec(select(JournalLine).where(JournalLine.id == zeile_id))
    ).first()
    assert danach is not None
    assert (
        danach.partner_id == partner_vorher
    ), "Die Buchungszeile eines fremden Mandanten wurde umgeschrieben."
