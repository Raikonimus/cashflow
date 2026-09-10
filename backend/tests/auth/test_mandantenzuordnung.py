"""Mandantenzuordnung in der Nutzerverwaltung — Stufe 2 des Mandantenfaehigkeitsplans.

Deckt die Befunde M7 (keine Zuordnung in der Nutzerverwaltung) und M8 (nur Admins
durften zuordnen) ab, samt Entscheidung E2: **Ein Mandant-Admin darf Nutzer seinen
eigenen Mandanten zuordnen, aber keinem fremden.**

Der gefaehrlichste Fall steht unter „Abgleich": Ein Abgleich, der den Sollstand setzt,
sieht harmlos aus und kann trotzdem Zuordnungen entfernen, die den Handelnden nichts
angehen. Dafuer gibt es hier drei Tests.
"""

from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import MandantUser
from app.partners.models import AuditLog
from tests.conftest import AnmeldeHelfer, ZweiMandanten


async def _nutzer_aus_liste(client: AsyncClient, header: dict, email: str) -> dict:
    """Holt einen Nutzer aus `GET /users` heraus."""
    antwort = await client.get("/api/v1/users", headers=header)
    assert antwort.status_code == 200, antwort.text
    passende = [n for n in antwort.json() if n["email"] == email]
    assert passende, f"{email} steht nicht in der Liste"
    return passende[0]


async def _mandanten_von(session: AsyncSession, user_id: UUID | str) -> set[UUID]:
    """Liest die Zuordnungen eines Nutzers direkt aus der Datenbank.

    Nimmt die Kennung auch als Zeichenkette, weil sie oft aus einer JSON-Antwort
    kommt — die Spalte ist als UUID typisiert und wuerde eine Zeichenkette abweisen.
    """
    treffer = await session.exec(
        select(MandantUser.mandant_id).where(MandantUser.user_id == UUID(str(user_id)))
    )
    return set(treffer.all())


# ─── M7 · Die Zuordnung ist ueberhaupt sichtbar ──────────────────────────────


async def test_m7_nutzerliste_zeigt_die_mandanten(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Der Kern von M7: Vorher trug die Antwort kein Mandantenfeld.

    Ohne die Angabe kann die Nutzerverwaltung nicht anzeigen, wer wohin gehoert — und
    ohne Anzeige gibt es auch keine sinnvolle Bearbeitung.
    """
    header = await anmelden(zwei_mandanten.admin, zwei_mandanten.a)

    beide = await _nutzer_aus_liste(client, header, zwei_mandanten.nutzer_beide.email)
    assert {m["name"] for m in beide["mandants"]} == {"Mandant A", "Mandant B"}

    nur_a = await _nutzer_aus_liste(client, header, zwei_mandanten.nutzer_a.email)
    assert [m["name"] for m in nur_a["mandants"]] == ["Mandant A"]


async def test_m7_nutzer_ohne_mandant_ist_erkennbar(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Die leere Liste ist eine Aussage, kein fehlender Wert.

    Sie markiert genau die Nutzer, die in der Sackgasse aus M6 sitzen — damit die
    Verwaltung sie findet, ohne dass jemand sich beschwert.
    """
    header = await anmelden(zwei_mandanten.admin, zwei_mandanten.a)

    ohne = await _nutzer_aus_liste(client, header, zwei_mandanten.nutzer_ohne.email)
    assert ohne["mandants"] == []


async def test_m7_neuer_nutzer_kann_direkt_zugeordnet_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Anlegen und Zuordnen in einem Schritt — sonst entsteht der Zustand aus M6.

    Die Zuordnung muss **vor** dem Einladungsversand passieren (ADR-004: ein
    SMTP-Fehler rollt die Anlage nicht zurueck). Stuende sie dahinter, waere ein
    Mailfehler genau der Weg in die Sackgasse.
    """
    header = await anmelden(zwei_mandanten.admin, zwei_mandanten.a)

    antwort = await client.post(
        "/api/v1/users",
        json={
            "email": "neu@example.com",
            "role": "accountant",
            "mandant_ids": [str(zwei_mandanten.a.id), str(zwei_mandanten.b.id)],
        },
        headers=header,
    )
    assert antwort.status_code == 201, antwort.text
    daten = antwort.json()
    assert {m["name"] for m in daten["mandants"]} == {"Mandant A", "Mandant B"}
    assert await _mandanten_von(db_session, daten["id"]) == {
        zwei_mandanten.a.id,
        zwei_mandanten.b.id,
    }


async def test_m7_anlegen_ohne_mandanten_bleibt_erlaubt(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Das bisherige Verhalten bleibt moeglich — die Angabe ist freiwillig."""
    header = await anmelden(zwei_mandanten.admin, zwei_mandanten.a)

    antwort = await client.post(
        "/api/v1/users",
        json={"email": "leer@example.com", "role": "viewer"},
        headers=header,
    )
    assert antwort.status_code == 201, antwort.text
    assert antwort.json()["mandants"] == []


# ─── Abgleich über PATCH ─────────────────────────────────────────────────────


async def test_abgleich_setzt_den_sollstand(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Ein Aufruf, ein Endstand — statt je Zuordnung ein eigener Aufruf.

    Bei mehreren Aufrufen koennte der zweite scheitern und ein halb geaenderter
    Stand zurueckbleiben.
    """
    header = await anmelden(zwei_mandanten.admin, zwei_mandanten.a)

    antwort = await client.patch(
        f"/api/v1/users/{zwei_mandanten.nutzer_a.id}",
        json={"mandant_ids": [str(zwei_mandanten.b.id)]},
        headers=header,
    )
    assert antwort.status_code == 200, antwort.text
    assert [m["name"] for m in antwort.json()["mandants"]] == ["Mandant B"]
    assert await _mandanten_von(db_session, zwei_mandanten.nutzer_a.id) == {
        zwei_mandanten.b.id
    }


async def test_abgleich_ohne_angabe_laesst_die_zuordnungen_stehen(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Ein Rollenwechsel darf keine Zugriffe loeschen.

    `mandant_ids` fehlt im Patch — also bleiben die Zuordnungen unberuehrt. Waere das
    anders, wuerde jede Rollenaenderung stillschweigend Zugriffe entfernen.
    """
    header = await anmelden(zwei_mandanten.admin, zwei_mandanten.a)

    antwort = await client.patch(
        f"/api/v1/users/{zwei_mandanten.nutzer_beide.id}",
        json={"role": "viewer"},
        headers=header,
    )
    assert antwort.status_code == 200, antwort.text
    assert await _mandanten_von(db_session, zwei_mandanten.nutzer_beide.id) == {
        zwei_mandanten.a.id,
        zwei_mandanten.b.id,
    }


async def test_abgleich_eines_mandant_admins_laesst_fremde_zuordnungen_unberuehrt(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Der gefaehrlichste Fall dieser Stufe.

    Der Mandant-Admin gehoert nur zu A. Er sendet fuer `nutzer_beide` den Sollstand
    ``[A]`` — was woertlich genommen die Zuordnung zu B entfernen wuerde. Genau das
    darf nicht passieren: Der Abgleich wirkt nur innerhalb der Mandanten, die der
    Handelnde selbst zuordnen darf. B liegt ausserhalb und bleibt.

    Ohne diese Regel waere ein harmlos aussehender Speichervorgang in der
    Nutzerverwaltung ein Weg, fremde Zugriffe zu entfernen.
    """
    header = await anmelden(zwei_mandanten.mandant_admin_a, zwei_mandanten.a)

    antwort = await client.patch(
        f"/api/v1/users/{zwei_mandanten.nutzer_beide.id}",
        json={"mandant_ids": [str(zwei_mandanten.a.id)]},
        headers=header,
    )
    assert antwort.status_code == 200, antwort.text

    assert await _mandanten_von(db_session, zwei_mandanten.nutzer_beide.id) == {
        zwei_mandanten.a.id,
        zwei_mandanten.b.id,
    }, "Die Zuordnung zu Mandant B wurde von einem Mandant-Admin aus A entfernt."


async def test_abgleich_auf_fremden_mandanten_wird_abgewiesen(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Ein Mandant im Sollstand, den der Handelnde nicht zuordnen darf, ergibt 403.

    Nicht stillschweigend uebergangen: Sonst meldet die Oberflaeche Erfolg fuer eine
    Zuordnung, die es nicht gibt.
    """
    header = await anmelden(zwei_mandanten.mandant_admin_a, zwei_mandanten.a)

    antwort = await client.patch(
        f"/api/v1/users/{zwei_mandanten.nutzer_a.id}",
        json={
            "mandant_ids": [str(zwei_mandanten.a.id), str(zwei_mandanten.b.id)],
        },
        headers=header,
    )
    assert antwort.status_code == 403, antwort.text


# ─── E2 · Was ein Mandant-Admin darf ─────────────────────────────────────────


async def test_e2_mandant_admin_sieht_nur_eigene_zuordenbare_mandanten(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Die Auswahlliste der Nutzerverwaltung, aus derselben Quelle wie die Rechte."""
    header = await anmelden(zwei_mandanten.mandant_admin_a, zwei_mandanten.a)

    antwort = await client.get("/api/v1/users/assignable-mandants", headers=header)
    assert antwort.status_code == 200, antwort.text
    assert [m["name"] for m in antwort.json()] == ["Mandant A"]


async def test_e2_admin_sieht_alle_zuordenbaren_mandanten(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Fuer Admins alle aktiven — auch die ohne eigene Zuordnung (Befund M5)."""
    header = await anmelden(zwei_mandanten.admin, zwei_mandanten.a)

    antwort = await client.get("/api/v1/users/assignable-mandants", headers=header)
    assert [m["name"] for m in antwort.json()] == ["Mandant A", "Mandant B"]


async def test_e2_deaktivierter_mandant_ist_nicht_zuordenbar(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Ein abgeschalteter Mandant taucht in der Auswahl nicht auf.

    Sonst koennte man Nutzer einem Mandanten zuordnen, den `select_mandant` danach
    ablehnt (M9) — eine Zuordnung, die nichts bewirkt.
    """
    header = await anmelden(zwei_mandanten.admin, zwei_mandanten.a)

    zwei_mandanten.b.mandant.is_active = False
    db_session.add(zwei_mandanten.b.mandant)
    await db_session.commit()

    antwort = await client.get("/api/v1/users/assignable-mandants", headers=header)
    assert [m["name"] for m in antwort.json()] == ["Mandant A"]


async def test_e2_accountant_darf_die_liste_nicht_abrufen(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Unterhalb von `mandant_admin` ist die Nutzerverwaltung geschlossen."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.get("/api/v1/users/assignable-mandants", headers=header)
    assert antwort.status_code == 403


async def test_e2_mandant_admin_darf_keinen_fremden_nutzer_hereinziehen(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """`nutzer_b` gehoert nur zu B und teilt keinen Mandanten mit dem Handelnden.

    Duerfte der Mandant-Admin ihn zu A holen, wuesste er anschliessend dessen
    E-Mail-Adresse — und haette einen Nutzer erreicht, der ihn nichts angeht.
    """
    header = await anmelden(zwei_mandanten.mandant_admin_a, zwei_mandanten.a)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/users",
        json={"user_id": str(zwei_mandanten.nutzer_b.id)},
        headers=header,
    )
    assert antwort.status_code == 403, antwort.text


async def test_e2_mandant_admin_darf_einen_nutzer_ohne_mandant_zuordnen(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Die Gegenprobe — und der eigentliche Arbeitsablauf.

    Ein frisch eingeladener Nutzer hat keine Zuordnung und teilt daher auch keinen
    Mandanten mit dem Mandant-Admin. Ohne diese Ausnahme koennte er niemanden
    zuordnen, den er selbst angelegt hat.
    """
    header = await anmelden(zwei_mandanten.mandant_admin_a, zwei_mandanten.a)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/users",
        json={"user_id": str(zwei_mandanten.nutzer_ohne.id)},
        headers=header,
    )
    assert antwort.status_code == 201, antwort.text


# ─── Entfernen und Selbstaussperrung ─────────────────────────────────────────


async def test_entfernen_funktioniert(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Die Gegenrichtung zum Zuordnen."""
    header = await anmelden(zwei_mandanten.admin, zwei_mandanten.a)

    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/users/{zwei_mandanten.nutzer_beide.id}",
        headers=header,
    )
    assert antwort.status_code == 204, antwort.text
    assert await _mandanten_von(db_session, zwei_mandanten.nutzer_beide.id) == {
        zwei_mandanten.a.id
    }


async def test_die_eigene_letzte_zuordnung_bleibt(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Niemand darf sich selbst aussperren.

    Der Mandant-Admin gehoert nur zu A. Nimmt er sich diese Zuordnung, kommt er an
    keine Daten mehr — und kann sie sich nicht zurueckgeben, weil dafuer eine
    Zuordnung noetig waere. Fuer Admins gilt die Sperre nicht, sie sehen seit E3 alle
    aktiven Mandanten.
    """
    header = await anmelden(zwei_mandanten.mandant_admin_a, zwei_mandanten.a)

    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/users/{zwei_mandanten.mandant_admin_a.id}",
        headers=header,
    )
    assert antwort.status_code == 400, antwort.text


async def test_abgleich_kann_die_eigene_letzte_zuordnung_nicht_leeren(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Dieselbe Sperre auf dem anderen Weg.

    Der Abgleich prueft den **Endstand**, nicht die einzelne Zeile. Eine Pruefung pro
    entfernter Zuordnung waere hier durchgelaufen.
    """
    header = await anmelden(zwei_mandanten.mandant_admin_a, zwei_mandanten.a)

    antwort = await client.patch(
        f"/api/v1/users/{zwei_mandanten.mandant_admin_a.id}",
        json={"mandant_ids": []},
        headers=header,
    )
    assert antwort.status_code == 400, antwort.text
    assert await _mandanten_von(db_session, zwei_mandanten.mandant_admin_a.id) == {
        zwei_mandanten.a.id
    }


async def test_unbekannte_ids_ergeben_404(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Unbekannter Nutzer und unbekannter Mandant, jeweils einzeln."""
    header = await anmelden(zwei_mandanten.admin, zwei_mandanten.a)

    fremder_nutzer = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/users",
        json={"user_id": str(uuid4())},
        headers=header,
    )
    assert fremder_nutzer.status_code == 404

    fremder_mandant = await client.post(
        f"/api/v1/mandants/{uuid4()}/users",
        json={"user_id": str(zwei_mandanten.nutzer_a.id)},
        headers=header,
    )
    assert fremder_mandant.status_code == 404


# ─── Protokoll ───────────────────────────────────────────────────────────────


async def test_zuordnung_wird_protokolliert(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Eine Zuordnung ist eine Zugriffsentscheidung und gehoert ins Protokoll.

    Vorher schrieben `auth.login` und `auth.logout` einen Eintrag, das Zuordnen
    nicht — obwohl es die weiter reichende Aenderung ist.
    """
    header = await anmelden(zwei_mandanten.admin, zwei_mandanten.a)

    await client.post(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/users",
        json={"user_id": str(zwei_mandanten.nutzer_a.id)},
        headers=header,
    )
    await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/users/{zwei_mandanten.nutzer_a.id}",
        headers=header,
    )

    treffer = await db_session.exec(
        select(AuditLog).where(
            AuditLog.event_type.in_(
                ["auth.mandant_assigned", "auth.mandant_unassigned"]
            )
        )
    )
    eintraege = list(treffer.all())
    arten = {e.event_type for e in eintraege}

    assert arten == {"auth.mandant_assigned", "auth.mandant_unassigned"}
    for eintrag in eintraege:
        assert eintrag.mandant_id == zwei_mandanten.b.id
        assert eintrag.actor_id == zwei_mandanten.admin.id
        assert eintrag.payload["user_email"] == zwei_mandanten.nutzer_a.email
