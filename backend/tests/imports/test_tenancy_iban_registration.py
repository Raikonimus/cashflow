"""Wechselwirkung der global eindeutigen IBAN (ADR-008) mit dem Import-Matching.

ADR-008 legt fest, dass eine IBAN ueber alle Mandanten hinweg nur einem Partner
gehoeren darf. Der Lookup beim Import filtert dagegen korrekt auf den eigenen
Mandanten. Beides zusammen ergibt eine Luecke: Hat Mandant A eine IBAN registriert,
kann der Partner von Mandant B sie nie bekommen — und wird nie per IBAN gematcht.
"""

import pytest
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
        session.add(PartnerIban(partner_id=partner.id, iban=iban, created_at=now))
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BEFUND A1-2 (offen): ADR-008 macht die IBAN global eindeutig, der Import-Lookup "
        "filtert aber auf den eigenen Mandanten. Die Registrierung ueberspringt still, was "
        "ein fremder Mandant belegt hat. Fix erfordert eine Entscheidung ueber ADR-008 — "
        "entweder IBAN pro Mandant eindeutig, oder der Import legt ein Review-Item an, statt "
        "stillschweigend nichts zu tun."
    ),
)
async def test_iban_wird_beim_import_auch_registriert_wenn_ein_fremder_mandant_sie_hat(
    db_session: AsyncSession,
):
    """Der neue Partner von Mandant B muss die IBAN bekommen.

    Sonst faellt jeder weitere Import desselben Zahlungspartners erneut auf die
    schwaechere Namenserkennung zurueck — dauerhaft und ohne jeden Hinweis.
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BEFUND A1-2 (offen): ADR-008 macht die IBAN global eindeutig, der Import-Lookup "
        "filtert aber auf den eigenen Mandanten. Die Registrierung ueberspringt still, was "
        "ein fremder Mandant belegt hat. Fix erfordert eine Entscheidung ueber ADR-008 — "
        "entweder IBAN pro Mandant eindeutig, oder der Import legt ein Review-Item an, statt "
        "stillschweigend nichts zu tun."
    ),
)
async def test_zweiter_import_erkennt_den_partner_wieder(db_session: AsyncSession):
    """Folgefehler: beim zweiten Import muesste iban_match herauskommen."""
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
