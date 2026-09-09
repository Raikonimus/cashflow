"""Mandantentrennung der Import-Endpunkte.

`require_mandant_access` prueft nur die `mandant_id` aus dem Pfad. Die zweite ID im
selben Pfad — hier `account_id` — wird von der Dependency nicht geprueft. Ob sie zum
Mandanten gehoert, muss der Service tun. Diese Tests halten fest, dass er es tut.
"""
import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import UserRole
from app.imports.models import ImportRun
from tests.imports import (  # noqa: F401
    assign_user_to_mandant,
    client,
    create_account_db,
    create_mandant,
    create_user,
    db_session,
    get_auth_token,
    setup_db,
    utcnow,
)


@pytest.fixture
async def zwei_mandanten(db_session: AsyncSession, client: AsyncClient):
    """Nutzer gehoert zu Mandant A. Mandant B hat ein Konto mit einem Import."""
    eigener = await create_mandant(db_session, name="Mandant A")
    fremder = await create_mandant(db_session, name="Mandant B")
    nutzer = await create_user(db_session, email="a@example.com", role=UserRole.accountant)
    await assign_user_to_mandant(db_session, nutzer, eigener)

    fremdes_konto = await create_account_db(db_session, fremder.id, name="Konto B")
    lauf = ImportRun(
        account_id=fremdes_konto.id,
        mandant_id=fremder.id,
        user_id=nutzer.id,
        filename="fremd.csv",
        row_count=3,
        status="completed",
        created_at=utcnow(),
    )
    db_session.add(lauf)
    await db_session.commit()
    await db_session.refresh(lauf)

    token = await get_auth_token(client, nutzer, eigener)
    return {
        "eigener": eigener,
        "fremdes_konto": fremdes_konto,
        "lauf": lauf,
        "headers": {"Authorization": f"Bearer {token}"},
    }


async def test_fremde_importlaeufe_sind_nicht_auflistbar(client: AsyncClient, zwei_mandanten):
    """Eigene mandant_id im Pfad, fremde account_id — die Liste muss verweigert werden."""
    ctx = zwei_mandanten
    resp = await client.get(
        f"/api/v1/mandants/{ctx['eigener'].id}/accounts/{ctx['fremdes_konto'].id}/imports",
        headers=ctx["headers"],
    )

    assert resp.status_code in (403, 404), (
        f"Fremde Importlaeufe wurden ausgeliefert: {resp.status_code} {resp.text}"
    )


async def test_fremder_importlauf_ist_nicht_abrufbar(client: AsyncClient, zwei_mandanten):
    """Dasselbe fuer den Detailabruf eines einzelnen Laufs."""
    ctx = zwei_mandanten
    resp = await client.get(
        f"/api/v1/mandants/{ctx['eigener'].id}/accounts/{ctx['fremdes_konto'].id}"
        f"/imports/{ctx['lauf'].id}",
        headers=ctx["headers"],
    )

    assert resp.status_code in (403, 404), (
        f"Fremder Importlauf wurde ausgeliefert: {resp.status_code} {resp.text}"
    )
