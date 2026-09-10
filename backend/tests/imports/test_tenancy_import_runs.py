"""Mandantentrennung der Import-Endpunkte.

`require_mandant_access` prueft nur die `mandant_id` aus dem Pfad. Die zweite ID im
selben Pfad — hier `account_id` — wird von der Dependency nicht geprueft. Ob sie zum
Mandanten gehoert, muss der Service tun. Diese Tests halten fest, dass er es tut.

Die zwei Mandanten kommen seit Stufe 0 des Mandantenfaehigkeitsplans aus der
gemeinsamen Fixture in `tests/conftest.py`. Vorher baute diese Datei sie selbst — und
`test_tenancy_apply_excluded.py` daneben ein zweites Mal, leicht anders. Genau der
Zwilling, nach dem Frage 1 des Merge-Checks sucht.
"""

from httpx import AsyncClient

from tests.conftest import AnmeldeHelfer, ZweiMandanten
from tests.imports import (  # noqa: F401
    client,
    db_session,
    setup_db,
)


async def test_fremde_importlaeufe_sind_nicht_auflistbar(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Eigene mandant_id im Pfad, fremde account_id — die Liste muss verweigert werden."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    resp = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/accounts/{zwei_mandanten.b.konto.id}/imports",
        headers=header,
    )

    assert resp.status_code in (
        403,
        404,
    ), f"Fremde Importlaeufe wurden ausgeliefert: {resp.status_code} {resp.text}"


async def test_fremder_importlauf_ist_nicht_abrufbar(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Dasselbe fuer den Detailabruf eines einzelnen Laufs."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    resp = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/accounts/{zwei_mandanten.b.konto.id}"
        f"/imports/{zwei_mandanten.b.import_lauf.id}",
        headers=header,
    )

    assert resp.status_code in (
        403,
        404,
    ), f"Fremder Importlauf wurde ausgeliefert: {resp.status_code} {resp.text}"


async def test_eigene_importlaeufe_bleiben_abrufbar(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Gegenprobe — ohne sie wuerden die zwei Tests oben auch bei einem Endpunkt
    gruen bleiben, der grundsaetzlich verweigert."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    resp = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/accounts/{zwei_mandanten.a.konto.id}/imports",
        headers=header,
    )

    assert resp.status_code == 200, f"{resp.status_code} {resp.text}"
    seite = resp.json()
    assert seite["total"] == 1
    assert [lauf["id"] for lauf in seite["items"]] == [
        str(zwei_mandanten.a.import_lauf.id)
    ]
