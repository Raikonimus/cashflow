"""Dieselbe IBAN in zwei Mandanten — Befund A1-3, behoben in Stufe 5.

Was hier geprueft wird
----------------------
Zwei Mandanten fuehren denselben Zahlungspartner mit derselben IBAN. Das ist kein
Sonderfall, sondern der Normalfall: Amazon, die Telekom und das Finanzamt haben genau
eine IBAN, und jeder Mandant zahlt an dieselbe.

Drei Zusicherungen, drei Ebenen:

1. Der Lookup bleibt im eigenen Mandanten — B findet nicht A's Partner.
2. Die Registrierung **gelingt** fuer B, obwohl A dieselbe IBAN fuehrt.
3. Der zweite Import erkennt B's Partner ueber die IBAN wieder.

Die Vorgeschichte
-----------------
Zusicherung 2 und 3 waren bis Stufe 5 als ``xfail(strict=True)`` hinterlegt. ADR-008
machte die IBAN **global** eindeutig, der Lookup filterte je Mandant — und die
Registrierung fuer B uebersprang stillschweigend, was A belegt hatte. B wurde ueber
diese IBAN nie erkannt, bei jedem Import erneut, ohne jeden Hinweis. Bemerkenswert war
die Ungleichheit: Der manuelle Weg warf 409, der Importweg schwieg.

ADR-018 kehrt die Regel um — eindeutig je Mandant. Die beiden Tests laufen seither
gruen; die Markierungen sind entfernt. Sie beschreiben jetzt die Anforderung und nicht
mehr den Mangel.

Warum diese Datei die gemeinsame Fixture aus ``tests/conftest.py`` nicht benutzt
--------------------------------------------------------------------------------
Sie braucht weder Nutzer noch Token: Die Tests rufen den Matching-Service direkt auf,
nicht die API. Der frueher genannte Grund — die Fixture gebe jedem Mandanten
absichtlich eine eigene IBAN, weil dieselbe in zwei Mandanten nach ADR-008 ein
Sonderfall sei — ist mit ADR-018 entfallen.
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.imports.matching import MatchOutcome, PartnerMatchingService
from app.imports.models import utcnow
from app.partners.models import Partner, PartnerIban
from tests.imports import (  # noqa: F401
    create_mandant,
    db_session,
    setup_db,
)

IBAN = "DE89370400440532013000"


async def _partner_mit_iban(
    session: AsyncSession, mandant_id, name: str, iban: str | None
):
    now = utcnow()
    partner = Partner(
        mandant_id=mandant_id, name=name, is_active=True, created_at=now, updated_at=now
    )
    session.add(partner)
    await session.flush()
    if iban:
        session.add(
            PartnerIban(
                mandant_id=partner.mandant_id,
                partner_id=partner.id,
                iban=iban,
                created_at=now,
            )
        )
    await session.commit()
    await session.refresh(partner)
    return partner


async def test_fremde_iban_wird_nicht_dem_falschen_mandanten_zugeordnet(
    db_session: AsyncSession,
):
    """Die Grundregel haelt: der Lookup bleibt im eigenen Mandanten."""
    fremder = await create_mandant(db_session, name="Mandant A")
    eigener = await create_mandant(db_session, name="Mandant B")
    fremder_partner = await _partner_mit_iban(db_session, fremder.id, "Amazon A", IBAN)

    svc = PartnerMatchingService(db_session)
    result = await svc.match(mandant_id=eigener.id, iban_raw=IBAN, name_raw="Amazon B")

    assert result.partner_id != fremder_partner.id
    assert result.outcome is not MatchOutcome.iban_match


async def test_iban_wird_beim_import_auch_registriert_wenn_ein_fremder_mandant_sie_hat(
    db_session: AsyncSession,
):
    """Der neue Partner von Mandant B bekommt die IBAN, obwohl A sie fuehrt.

    Sonst fiele jeder weitere Import desselben Zahlungspartners erneut auf die
    schwaechere Namenserkennung zurueck — dauerhaft und ohne jeden Hinweis. Dieser Test
    war bis Stufe 5 ein erwarteter Fehlschlag (A1-3); seit ADR-018 ist er die
    Anforderung.
    """
    fremder = await create_mandant(db_session, name="Mandant A")
    eigener = await create_mandant(db_session, name="Mandant B")
    await _partner_mit_iban(db_session, fremder.id, "Amazon A", IBAN)

    svc = PartnerMatchingService(db_session)
    result = await svc.match(mandant_id=eigener.id, iban_raw=IBAN, name_raw="Amazon B")
    await db_session.commit()

    assert result.partner_id is not None, "Fuer Mandant B wurde kein Partner angelegt"
    eigene_ibans = (
        await db_session.exec(
            select(PartnerIban).where(PartnerIban.partner_id == result.partner_id)
        )
    ).all()

    assert [i.iban for i in eigene_ibans] == [IBAN], (
        "Die IBAN wurde stillschweigend nicht registriert — der Partner von Mandant B "
        "wird nie per IBAN erkannt."
    )


async def test_zweiter_import_erkennt_den_partner_wieder(db_session: AsyncSession):
    """Der zweite Import erkennt B's Partner ueber die IBAN — nicht ueber den Namen.

    Die Probe darauf, dass die Registrierung aus dem Test davor auch wirkt: Ein
    ``iban_match`` kann nur herauskommen, wenn die IBAN tatsaechlich am Partner haengt.
    Vorher war das Ergebnis dauerhaft ``name_match``.
    """
    fremder = await create_mandant(db_session, name="Mandant A")
    eigener = await create_mandant(db_session, name="Mandant B")
    await _partner_mit_iban(db_session, fremder.id, "Amazon A", IBAN)

    svc = PartnerMatchingService(db_session)
    erster = await svc.match(mandant_id=eigener.id, iban_raw=IBAN, name_raw="Amazon B")
    await db_session.commit()

    zweiter = await svc.match(mandant_id=eigener.id, iban_raw=IBAN, name_raw="Amazon B")

    assert zweiter.outcome is MatchOutcome.iban_match, (
        f"Zweiter Import erkennt den eigenen Partner nicht per IBAN, sondern als "
        f"{zweiter.outcome}"
    )
    assert zweiter.partner_id == erster.partner_id
