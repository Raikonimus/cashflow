"""Mandantentrennung des Endpunkts `excluded-identifiers/apply`.

Gleiches Muster wie bei den Import-Endpunkten: `require_mandant_access` prueft die
`mandant_id` aus dem Pfad, nicht die `account_id`. Dieser Pfad *schreibt* — er ordnet
Buchungszeilen neu zu. Ohne Pruefung des Kontos wuerden fremde Buchungen umgeschrieben.

Die zwei Mandanten kommen seit Stufe 0 des Mandantenfaehigkeitsplans aus der
gemeinsamen Fixture in `tests/conftest.py`; nur die ausgeschlossene Kennung legt dieser
Test selbst an, weil sie sein eigentlicher Gegenstand ist.
"""

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.imports.models import JournalLine, utcnow
from app.tenants.models import AccountExcludedIdentifier
from tests.conftest import AnmeldeHelfer, ZweiMandanten


async def _schliesse_iban_aus(
    session: AsyncSession, konto_id, iban: str
) -> AccountExcludedIdentifier:
    """Markiert eine IBAN fuer ein Konto als nicht zur Partnererkennung geeignet.

    Das ist die Voraussetzung dafuer, dass `apply` ueberhaupt etwas zu tun hat: Der
    Endpunkt loest genau die Partnerzuordnungen wieder auf, die auf einer
    ausgeschlossenen Kennung beruhen.
    """
    eintrag = AccountExcludedIdentifier(
        account_id=konto_id,
        identifier_type="iban",
        value=iban,
        created_at=utcnow(),
    )
    session.add(eintrag)
    await session.commit()
    await session.refresh(eintrag)
    return eintrag


async def test_fremdes_konto_kann_nicht_neu_zugeordnet_werden(
    db_session: AsyncSession,
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
):
    """Eigene mandant_id im Pfad, fremdes Konto — und die fremden Zeilen bleiben, wie sie sind.

    Der zweite Teil ist der wichtigere: Ein 403 allein sagt nicht, dass nichts
    geschrieben wurde. Der Endpunkt koennte die Zuordnung aufloesen und *danach*
    scheitern.
    """
    await _schliesse_iban_aus(
        db_session, zwei_mandanten.b.konto.id, zwei_mandanten.b.iban
    )

    fremde_zeile = zwei_mandanten.b.zeilen[0]
    zeile_id = fremde_zeile.id
    partner_vorher = fremde_zeile.partner_id
    assert partner_vorher is not None, "Die Fixture muesste einen Partner gesetzt haben"

    header = await anmelden(zwei_mandanten.nutzer_a)
    resp = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/accounts/{zwei_mandanten.b.konto.id}/excluded-identifiers/apply",
        headers=header,
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


async def test_eigenes_konto_wird_verarbeitet(
    db_session: AsyncSession,
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
):
    """Gegenprobe: Auf dem eigenen Konto tut derselbe Aufruf seine Arbeit.

    Ohne diese Haelfte wuerde der Test oben auch dann gruen bleiben, wenn der Endpunkt
    grundsaetzlich verweigert — und die Mandantentrennung waere nicht belegt, sondern
    nur die Unerreichbarkeit des Endpunkts.
    """
    await _schliesse_iban_aus(
        db_session, zwei_mandanten.a.konto.id, zwei_mandanten.a.iban
    )

    header = await anmelden(zwei_mandanten.nutzer_a)
    resp = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/accounts/{zwei_mandanten.a.konto.id}/excluded-identifiers/apply",
        headers=header,
    )

    assert resp.status_code == 200, f"{resp.status_code} {resp.text}"
