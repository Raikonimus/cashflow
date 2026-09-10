"""Die Mandantenauswahl beim Anmelden — Stufe 1 des Mandantenfaehigkeitsplans.

Deckt die Befunde M4, M5, M6 und M9 ab. Alle vier haben dieselbe Ursache: Die Frage
„welche Mandanten gehoeren zu diesem Nutzer" wurde an drei Stellen unterschiedlich
beantwortet — in `login`, in `_get_mandants_for_user` und in `require_mandant_access`.

Die Tests benutzen die gemeinsame Fixture `zwei_mandanten` aus `tests/conftest.py`.
Deren `admin` hat **keine** Zuordnung und ihr `nutzer_ohne` auch nicht — genau die zwei
Faelle, die vorher unbeobachtbar waren.
"""

from uuid import uuid4

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.security import decode_access_token
from app.partners.models import AuditLog
from tests.conftest import PASSWORT, AnmeldeHelfer, ZweiMandanten


async def _anmelden_rohdaten(client: AsyncClient, email: str) -> dict:
    """Meldet an und gibt die Antwort von `/auth/login` unveraendert zurueck.

    Absichtlich nicht der Helfer `anmelden`: Diese Tests untersuchen gerade, *was*
    `login` meldet, und duerfen den Auswahlschritt nicht schon hinter sich haben.
    """
    antwort = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORT}
    )
    assert antwort.status_code == 200, f"{antwort.status_code} {antwort.text}"
    return antwort.json()


# ─── M4 · Admins gehen denselben Weg wie alle anderen ────────────────────────


async def test_m4_admin_mit_mehreren_mandanten_muss_waehlen(
    client: AsyncClient, zwei_mandanten: ZweiMandanten
):
    """Der Kern von M4.

    Vorher kehrte `login` fuer `role == admin` frueh zurueck und meldete
    `requires_mandant_selection: False`, egal wie viele Mandanten es gab. Die
    Auswahlseite erschien nur ueber den Umweg der Routenweiche im Frontend.
    """
    daten = await _anmelden_rohdaten(client, zwei_mandanten.admin.email)

    assert daten["requires_mandant_selection"] is True
    assert decode_access_token(daten["access_token"])["mandant_id"] is None


async def test_m4_admin_mit_genau_einem_mandanten_waehlt_nicht(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, db_session: AsyncSession
):
    """Gegenprobe zu M4: Bei genau einem Mandanten gibt es nichts zu waehlen.

    Der Mandant kommt direkt ins Token — auch fuer einen Admin, der vorher immer ein
    Token ohne `mandant_id` bekam und danach durch die Auswahlseite laufen musste.
    """
    zwei_mandanten.b.mandant.is_active = False
    db_session.add(zwei_mandanten.b.mandant)
    await db_session.commit()

    daten = await _anmelden_rohdaten(client, zwei_mandanten.admin.email)

    assert daten["requires_mandant_selection"] is False
    assert len(daten["mandants"]) == 1
    nutzlast = decode_access_token(daten["access_token"])
    assert nutzlast["mandant_id"] == str(zwei_mandanten.a.id)


# ─── M5 · Eine Definition von „Mandanten dieses Nutzers" ─────────────────────


async def test_m5_admin_sieht_auch_mandanten_ohne_zuordnung(
    client: AsyncClient, zwei_mandanten: ZweiMandanten
):
    """Der Befund, der am 2026-09-10 real wurde.

    Der `admin` der Fixture hat **keine** Zeile in `mandant_users`. Vorher bekam er
    deshalb eine leere Auswahl, obwohl `require_mandant_access` ihn nach ADR-001 auf
    jeden Mandanten laesst. Ein Mandant ohne Zuordnung war damit unerreichbar.
    """
    daten = await _anmelden_rohdaten(client, zwei_mandanten.admin.email)

    namen = {m["name"] for m in daten["mandants"]}
    assert namen == {"Mandant A", "Mandant B"}


async def test_m5_admin_kann_einen_nicht_zugeordneten_mandanten_waehlen(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Und die Auswahl funktioniert auch — nicht nur die Anzeige."""
    header = await anmelden(zwei_mandanten.admin, zwei_mandanten.b)

    antwort = await client.get("/api/v1/auth/me", headers=header)
    assert antwort.json()["mandant_id"] == str(zwei_mandanten.b.id)


async def test_m5_nicht_admins_sehen_weiterhin_nur_ihre_eigenen(
    client: AsyncClient, zwei_mandanten: ZweiMandanten
):
    """Die Ausweitung gilt **nur** fuer Admins.

    Ohne diesen Test waere die Aenderung an `_get_mandants_for_user` nicht von einer
    unterschieden, die jedem Nutzer alle Mandanten zeigt — dem gegenteiligen Fehler.
    """
    daten = await _anmelden_rohdaten(client, zwei_mandanten.nutzer_a.email)

    assert [m["name"] for m in daten["mandants"]] == ["Mandant A"]
    assert daten["requires_mandant_selection"] is False


async def test_m5_fremder_mandant_bleibt_fuer_nicht_admins_verboten(
    client: AsyncClient, zwei_mandanten: ZweiMandanten
):
    """Die Gegenrichtung: `nutzer_a` darf Mandant B nicht waehlen."""
    daten = await _anmelden_rohdaten(client, zwei_mandanten.nutzer_a.email)

    antwort = await client.post(
        "/api/v1/auth/select-mandant",
        json={"mandant_id": str(zwei_mandanten.b.id)},
        headers={"Authorization": f"Bearer {daten['access_token']}"},
    )
    assert antwort.status_code == 403


# ─── M6 · Ein Nutzer ohne Mandant ────────────────────────────────────────────


async def test_m6_nutzer_ohne_mandant_bekommt_eine_leere_liste(
    client: AsyncClient, zwei_mandanten: ZweiMandanten
):
    """Anmelden gelingt, aber die Liste ist leer — daran erkennt der Client den Fall.

    `create_user()` legt keine Zuordnung an, jeder neu eingeladene Nutzer ist also
    zuerst in diesem Zustand. Die Antwort muss ihn unterscheidbar machen von „noch
    nicht gewaehlt", sonst kann das Frontend keine sinnvolle Meldung zeigen.
    """
    daten = await _anmelden_rohdaten(client, zwei_mandanten.nutzer_ohne.email)

    assert daten["mandants"] == []
    assert daten["requires_mandant_selection"] is False
    assert decode_access_token(daten["access_token"])["mandant_id"] is None


async def test_m6_nutzer_ohne_mandant_kommt_an_keine_daten(
    client: AsyncClient, zwei_mandanten: ZweiMandanten
):
    """Und das Token ohne Mandanten oeffnet nichts."""
    daten = await _anmelden_rohdaten(client, zwei_mandanten.nutzer_ohne.email)
    header = {"Authorization": f"Bearer {daten['access_token']}"}

    for mandant_id in (zwei_mandanten.a.id, zwei_mandanten.b.id):
        antwort = await client.get(
            f"/api/v1/mandants/{mandant_id}/accounts", headers=header
        )
        assert antwort.status_code == 403, antwort.text


# ─── M9 · Deaktivierte Mandanten sind nicht waehlbar ─────────────────────────


async def test_m9_deaktivierter_mandant_ist_nicht_waehlbar(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, db_session: AsyncSession
):
    """Der Befund M9.

    `_get_mandants_for_user` filterte auf `is_active`, `select_mandant` nicht — und
    `deactivate_mandant` laesst die Zeilen in `mandant_users` stehen. Eine bekannte
    Mandanten-ID liess sich deshalb weiter in ein gueltiges Token verwandeln.
    """
    daten = await _anmelden_rohdaten(client, zwei_mandanten.nutzer_beide.email)
    token = daten["access_token"]

    zwei_mandanten.b.mandant.is_active = False
    db_session.add(zwei_mandanten.b.mandant)
    await db_session.commit()

    antwort = await client.post(
        "/api/v1/auth/select-mandant",
        json={"mandant_id": str(zwei_mandanten.b.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert antwort.status_code == 403, (
        f"Ein deaktivierter Mandant liess sich waehlen: "
        f"{antwort.status_code} {antwort.text}"
    )


async def test_m9_deaktivierter_mandant_gilt_auch_fuer_admins(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, db_session: AsyncSession
):
    """Die Pruefung auf `is_active` steht **vor** der Rollenpruefung.

    Sonst haette der Admin den einen Weg offen, auf dem ein abgeschalteter Mandant
    doch wieder in ein Token kommt.
    """
    daten = await _anmelden_rohdaten(client, zwei_mandanten.admin.email)

    zwei_mandanten.b.mandant.is_active = False
    db_session.add(zwei_mandanten.b.mandant)
    await db_session.commit()

    antwort = await client.post(
        "/api/v1/auth/select-mandant",
        json={"mandant_id": str(zwei_mandanten.b.id)},
        headers={"Authorization": f"Bearer {daten['access_token']}"},
    )
    assert antwort.status_code == 403, antwort.text


async def test_m9_deaktivierter_mandant_verschwindet_aus_der_auswahl(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, db_session: AsyncSession
):
    """Und er wird gar nicht erst angeboten."""
    zwei_mandanten.b.mandant.is_active = False
    db_session.add(zwei_mandanten.b.mandant)
    await db_session.commit()

    daten = await _anmelden_rohdaten(client, zwei_mandanten.nutzer_beide.email)

    assert [m["name"] for m in daten["mandants"]] == ["Mandant A"]
    # Nur noch einer uebrig, also keine Auswahl mehr noetig:
    assert daten["requires_mandant_selection"] is False


async def test_unbekannter_mandant_ist_nicht_waehlbar(
    client: AsyncClient, zwei_mandanten: ZweiMandanten
):
    """Eine erfundene ID darf nicht besser gestellt sein als eine deaktivierte."""
    daten = await _anmelden_rohdaten(client, zwei_mandanten.admin.email)

    antwort = await client.post(
        "/api/v1/auth/select-mandant",
        json={"mandant_id": str(uuid4())},
        headers={"Authorization": f"Bearer {daten['access_token']}"},
    )
    assert antwort.status_code == 403


# ─── Protokoll ───────────────────────────────────────────────────────────────


async def test_mandantenwahl_wird_protokolliert(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Der Wechsel des Mandantenkontexts gehoert ins Protokoll.

    `auth.login` und `auth.logout` wurden schon geschrieben, die Mandantenwahl nicht —
    obwohl sie die Entscheidung ist, auf welche Daten die folgende Sitzung zugreift.
    """
    await anmelden(zwei_mandanten.nutzer_beide, zwei_mandanten.b)

    treffer = await db_session.exec(
        select(AuditLog).where(AuditLog.event_type == "auth.select_mandant")
    )
    eintraege = list(treffer.all())

    assert len(eintraege) == 1
    assert eintraege[0].mandant_id == zwei_mandanten.b.id
    assert eintraege[0].actor_id == zwei_mandanten.nutzer_beide.id
