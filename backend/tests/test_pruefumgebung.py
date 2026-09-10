"""Prueft die Pruefumgebung selbst — Stufe 0 des Mandantenfaehigkeitsplans.

Warum eine Fixture einen eigenen Test braucht: Sie ist ab jetzt die Grundlage aller
Mandantentests. Ist sie still falsch — beide Welten am selben Mandanten, eine Zuordnung
zu viel, ein Partner nur in einer der beiden Welten —, dann werden die Tests darueber
gruen, ohne etwas zu pruefen. Das ist Frage 5 des Merge-Checks („Prueft die Pruefung?");
Befund N-1 des Reviews war genau so ein Pruefschritt, der nichts pruefte.

Der letzte Test in dieser Datei ist der wichtigste: Er zeigt, dass die Umgebung eine
Mandantenverletzung tatsaechlich sichtbar macht.
"""

from uuid import uuid4

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import MandantUser
from app.tenants.models import Account
from tests.conftest import (
    LEISTUNG_NAME,
    PARTNER_NAME,
    AnmeldeHelfer,
    ZweiMandanten,
)

# ─── Die Welt ist zweigeteilt ────────────────────────────────────────────────


async def test_es_sind_wirklich_zwei_mandanten(zwei_mandanten: ZweiMandanten):
    """Der Grundfall. Waeren beide Welten derselbe Mandant, wuerde nichts auffallen."""
    assert zwei_mandanten.a.id != zwei_mandanten.b.id
    assert zwei_mandanten.a.mandant.name == "Mandant A"
    assert zwei_mandanten.b.mandant.name == "Mandant B"
    assert zwei_mandanten.a.mandant.is_active
    assert zwei_mandanten.b.mandant.is_active


async def test_jede_welt_haengt_am_eigenen_mandanten(zwei_mandanten: ZweiMandanten):
    """Direkt gebundene Tabellen tragen die richtige ``mandant_id``."""
    for welt in (zwei_mandanten.a, zwei_mandanten.b):
        assert welt.konto.mandant_id == welt.id
        assert welt.partner.mandant_id == welt.id
        assert welt.import_lauf.mandant_id == welt.id


async def test_die_transitive_kette_ist_vollstaendig(
    zwei_mandanten: ZweiMandanten, db_session: AsyncSession
):
    """Leistung, Buchungszeilen und Aufteilung haengen nur mittelbar am Mandanten.

    Das ist die Kette, an der die Trennung real haengt: Wer von der Aufteilung zum
    Mandanten will, muss vier Tabellen weit joinen. Vergisst eine Query einen Schritt,
    kann sie fremde Daten sehen. Dieser Test haelt fest, dass die Kette in beiden
    Welten geschlossen ist — sonst pruefen die Tests darueber ins Leere.
    """
    for welt in (zwei_mandanten.a, zwei_mandanten.b):
        # Aufteilung -> Buchungszeile -> Konto -> Mandant
        assert welt.aufteilung.service_id == welt.leistung.id
        assert welt.aufteilung.journal_line_id == welt.zeilen[1].id
        assert welt.leistung.partner_id == welt.partner.id

        for zeile in welt.zeilen:
            assert zeile.account_id == welt.konto.id
            assert zeile.import_run_id == welt.import_lauf.id
            konto = await db_session.get(Account, zeile.account_id)
            assert konto is not None
            assert konto.mandant_id == welt.id


async def test_beide_welten_benutzen_dieselben_namen(zwei_mandanten: ZweiMandanten):
    """Die absichtliche Namensgleichheit — ohne sie prueft die Umgebung zu wenig.

    Eine Suche nach ``PARTNER_NAME`` ohne Mandantenfilter findet zwei Partner statt
    einem. Genau daran soll ein fehlender Filter auffallen.
    """
    assert zwei_mandanten.a.partner.name == PARTNER_NAME
    assert zwei_mandanten.b.partner.name == PARTNER_NAME
    assert zwei_mandanten.a.leistung.name == LEISTUNG_NAME
    assert zwei_mandanten.b.leistung.name == LEISTUNG_NAME
    # Trotz gleichen Namens verschiedene Zeilen:
    assert zwei_mandanten.a.partner.id != zwei_mandanten.b.partner.id
    assert zwei_mandanten.a.leistung.id != zwei_mandanten.b.leistung.id


async def test_die_ibans_sind_verschieden(zwei_mandanten: ZweiMandanten):
    """ADR-008 macht die IBAN global eindeutig — gleiche IBAN waere ein anderer Test.

    Siehe ``tests/imports/test_tenancy_iban_registration.py``, das den Fall gleicher
    IBAN gezielt untersucht (Befund M13/A1-3).
    """
    assert zwei_mandanten.a.iban != zwei_mandanten.b.iban


# ─── Die fuenf Nutzer ────────────────────────────────────────────────────────


async def test_zuordnungen_stimmen(
    zwei_mandanten: ZweiMandanten, db_session: AsyncSession
):
    """Jeder der sechs Nutzer hat genau die Zuordnung, die seinen Fall ausmacht."""

    async def mandanten_von(nutzer_id):
        """Liest die Mandanten-IDs, die fuer diesen Nutzer in ``mandant_users`` stehen."""
        treffer = await db_session.exec(
            select(MandantUser.mandant_id).where(MandantUser.user_id == nutzer_id)
        )
        return set(treffer.all())

    assert await mandanten_von(zwei_mandanten.nutzer_a.id) == {zwei_mandanten.a.id}
    assert await mandanten_von(zwei_mandanten.nutzer_b.id) == {zwei_mandanten.b.id}
    assert await mandanten_von(zwei_mandanten.nutzer_beide.id) == {
        zwei_mandanten.a.id,
        zwei_mandanten.b.id,
    }
    assert await mandanten_von(zwei_mandanten.nutzer_ohne.id) == set()
    assert await mandanten_von(zwei_mandanten.mandant_admin_a.id) == {
        zwei_mandanten.a.id
    }
    assert await mandanten_von(zwei_mandanten.admin.id) == set()


async def test_ein_nutzer_kann_zwei_mandanten_haben(
    zwei_mandanten: ZweiMandanten, client: AsyncClient
):
    """Die Ausgangsfrage des ganzen Plans, als Test.

    Eine E-Mail-Adresse, zwei Mandanten — und das Anmelden verlangt daraufhin eine
    Auswahl. Bis Stufe 0 gab es diesen Fall in keiner Datenbank des Projekts.
    """
    antwort = await client.post(
        "/api/v1/auth/login",
        json={"email": zwei_mandanten.nutzer_beide.email, "password": "password123"},
    )
    assert antwort.status_code == 200
    daten = antwort.json()

    assert daten["requires_mandant_selection"] is True
    namen = {m["name"] for m in daten["mandants"]}
    assert namen == {"Mandant A", "Mandant B"}


async def test_ein_mandant_braucht_keine_auswahl(
    zwei_mandanten: ZweiMandanten, client: AsyncClient
):
    """Gegenprobe: Bei genau einem Mandanten setzt ``login`` ihn direkt ins Token."""
    antwort = await client.post(
        "/api/v1/auth/login",
        json={"email": zwei_mandanten.nutzer_a.email, "password": "password123"},
    )
    daten = antwort.json()

    assert daten["requires_mandant_selection"] is False
    assert len(daten["mandants"]) == 1


# ─── Der Anmeldehelfer ───────────────────────────────────────────────────────


async def test_anmelden_liefert_ein_brauchbares_token(
    zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer, client: AsyncClient
):
    """Der Helfer geht den echten Weg und das Ergebnis traegt den Mandanten."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.get("/api/v1/auth/me", headers=header)
    assert antwort.status_code == 200
    daten = antwort.json()
    assert daten["email"] == zwei_mandanten.nutzer_a.email
    assert daten["mandant_id"] == str(zwei_mandanten.a.id)


async def test_anmelden_waehlt_den_verlangten_mandanten(
    zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer, client: AsyncClient
):
    """Fuer ``nutzer_beide`` entscheidet die Angabe, welcher Mandant ins Token kommt."""
    for welt in (zwei_mandanten.a, zwei_mandanten.b):
        header = await anmelden(zwei_mandanten.nutzer_beide, welt)
        antwort = await client.get("/api/v1/auth/me", headers=header)
        assert antwort.json()["mandant_id"] == str(welt.id)


# ─── Und der Grund fuer das Ganze ────────────────────────────────────────────


async def test_die_umgebung_macht_eine_verletzung_sichtbar(
    zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer, client: AsyncClient
):
    """Der eigentliche Zweck von Stufe 0, an einem Endpunkt vorgefuehrt.

    ``nutzer_a`` fragt die Konten von Mandant B ab. Mit nur einem Mandanten in der
    Datenbank waere dieser Aufruf nicht formulierbar — es gaebe keine fremde
    ``mandant_id``. Jetzt ist er formulierbar, und die Antwort muss 403 sein.

    Zusaetzlich der Gegenbeweis, dass der Aufruf ueberhaupt funktioniert: Auf den
    eigenen Mandanten liefert derselbe Endpunkt 200. Ohne diese zweite Haelfte wuerde
    der Test auch bei einem kaputten Endpunkt gruen bleiben, der immer 403 sagt.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)

    fremd = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/accounts", headers=header
    )
    assert fremd.status_code == 403, (
        f"nutzer_a kam an die Konten von Mandant B: "
        f"{fremd.status_code} {fremd.text}"
    )

    eigen = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/accounts", headers=header
    )
    assert eigen.status_code == 200, (
        f"Der Endpunkt verweigert auch den eigenen Mandanten — dann prueft der "
        f"Vergleich oben nichts: {eigen.status_code} {eigen.text}"
    )
    assert [k["name"] for k in eigen.json()] == ["Konto A"]


async def test_unbekannter_mandant_ist_kein_zugang(
    zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer, client: AsyncClient
):
    """Eine erfundene ``mandant_id`` darf nicht besser gestellt sein als eine fremde."""
    header = await anmelden(zwei_mandanten.nutzer_a)
    antwort = await client.get(f"/api/v1/mandants/{uuid4()}/accounts", headers=header)
    assert antwort.status_code in (403, 404), antwort.text
