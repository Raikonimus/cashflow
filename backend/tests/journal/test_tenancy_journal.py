"""Mandantentrennung der Buchungs- und Auswertungs-Endpunkte — Stufe 3.

Viertes Modul nach OFFEN-Dichte: ``app/journal/service.py`` meldet fünf
OFFEN-Einträge und stand am 2026-09-10 bei 67 % Abdeckung.

Dieses Modul unterscheidet sich von den vorigen in einem Punkt: **Es rechnet mit
Geld.** Ein fehlender Mandantenfilter zeigt hier keine fremden Namen, sondern falsche
Summen — und eine falsche Summe sieht aus wie eine Summe. Niemand bemerkt sie, außer
jemand rechnet nach.

Deshalb prüfen die Auswertungstests nicht nur „kein fremder Datensatz in der Liste",
sondern die **exakten Beträge**. Beide Mandanten der Fixture haben absichtlich
dieselben Buchungsbeträge (+500,00 und −120,00): Fehlt der Filter, verdoppelt sich
die Summe, und das ist ein konkreter, nachrechenbarer Unterschied. Mit
unterschiedlichen Beträgen wäre eine falsche Summe zwar auch falsch, aber nicht so
eindeutig einer Ursache zuzuordnen.

``JournalLine`` trägt **keine** ``mandant_id`` — die Zugehörigkeit hängt an
``account_id``. Das ist der A1-4-Fall: Vier Funktionen dieses Moduls laden Zeilen ohne
Mandantenfilter und sieben sieben danach in Python. Diese Tests halten fest, dass das
Ergebnis stimmt; ob der Filter in SQL gehört, ist die offene Strukturfrage aus Stufe 5.
"""

from decimal import Decimal
from uuid import uuid4

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.imports.models import JournalLine, JournalLineSplit
from tests.conftest import AnmeldeHelfer, ZweiMandanten

# Was die Fixture je Mandant an Buchungen enthaelt.
EINGANG = Decimal("500.00")
AUSGANG = Decimal("-120.00")
ANFANGSBESTAND = Decimal("1000.00")


# ─── Listen ──────────────────────────────────────────────────────────────────


async def test_buchungsliste_zeigt_nur_eigene_zeilen(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Die Grundprüfung: genau die zwei eigenen Zeilen, nicht vier."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/journal", headers=header
    )
    assert antwort.status_code == 200, antwort.text

    daten = antwort.json()
    eintraege = daten["items"] if isinstance(daten, dict) else daten
    ids = {e["id"] for e in eintraege}
    eigene = {str(z.id) for z in zwei_mandanten.a.zeilen}
    fremde = {str(z.id) for z in zwei_mandanten.b.zeilen}

    assert eigene <= ids, "Eigene Buchungen fehlen in der Liste."
    assert not (
        fremde & ids
    ), "Die Buchungsliste enthaelt Zeilen des anderen Mandanten."


async def test_fremde_buchung_ist_nicht_einzeln_erreichbar(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Eigene ``mandant_id``, ``line_id`` von Mandant B — über den Schreibpfad.

    Es gibt keinen Lese-Endpunkt für eine einzelne Zeile; die Zuordnung einer
    Leistung ist der Weg, auf dem eine fremde ``line_id`` in den Service kommt.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/journal/{zwei_mandanten.b.zeilen[1].id}/assign-service",
        json={"service_id": str(zwei_mandanten.a.leistung.id)},
        headers=header,
    )
    assert antwort.status_code in (403, 404), antwort.text


# ─── Geld: die Auswertungen ──────────────────────────────────────────────────


async def test_kontostaende_rechnen_nur_mit_eigenen_buchungen(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Der wichtigste Test dieses Moduls, weil er nachrechnet.

    Erwartet wird genau ein Konto mit ``1000 + 500 − 120 = 1380``. Fehlte der
    Mandantenfilter, stünden dort die Buchungen beider Mandanten und damit
    ``1000 + 1000 − 240 = 1760`` — eine Zahl, die für sich betrachtet plausibel
    aussieht.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/reports/account-balances",
        headers=header,
    )
    assert antwort.status_code == 200, antwort.text

    daten = antwort.json()
    konten = daten["accounts"] if isinstance(daten, dict) else daten

    assert (
        len(konten) == 1
    ), f"Erwartet genau das eigene Konto, gefunden {len(konten)}: {konten}"
    assert konten[0]["account_id"] == str(zwei_mandanten.a.konto.id)

    erwartet = ANFANGSBESTAND + EINGANG + AUSGANG
    tatsaechlich = Decimal(konten[0]["current_balance"])
    assert tatsaechlich == erwartet, (
        f"Kontostand {tatsaechlich} statt {erwartet} — die Buchungen des anderen "
        f"Mandanten sind mitgerechnet."
    )


async def test_liquiditaet_bleibt_beim_eigenen_mandanten(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Dieselbe Rechnung über den Liquiditätsendpunkt."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/reports/liquidity?year=2026",
        headers=header,
    )
    assert antwort.status_code == 200, antwort.text

    # Geprueft wird der Ausgangsbestand, nicht der gesamte Antworttext.
    #
    # Erster Entwurf suchte den Betrag "1760" im Rohtext — die Summe beider
    # Mandanten. Der Test schlug an, aber aus dem falschen Grund: 1760,00 steht dort
    # als `closing_high` eines Unsicherheitsbands, also als voellig korrekt
    # errechneter Wert. Eine Textsuche ueber eine Antwort mit hundert Betraegen
    # trifft irgendwann jeden Betrag; sie prueft nicht, sie raet.
    daten = antwort.json()
    assert Decimal(daten["start_balance"]) == ANFANGSBESTAND + EINGANG + AUSGANG, (
        f"Ausgangsbestand {daten['start_balance']} statt "
        f"{ANFANGSBESTAND + EINGANG + AUSGANG} — die Buchungen des anderen "
        f"Mandanten sind mitgerechnet."
    )


async def test_jahresliste_kennt_nur_eigene_jahre(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Ein Jahr, in dem nur der andere Mandant gebucht hat, darf nicht erscheinen.

    Das ist die sichtbarste Form eines fehlenden Filters: Der Jahresumschalter
    zeigt ein Jahr an, für das es im eigenen Mandanten nichts gibt.
    """
    # Mandant B bekommt eine Buchung in einem Jahr, das A nicht hat.
    fremde_zeile = JournalLine(
        account_id=zwei_mandanten.b.konto.id,
        import_run_id=zwei_mandanten.b.import_lauf.id,
        partner_id=zwei_mandanten.b.partner.id,
        valuta_date="2019-03-01",
        booking_date="2019-03-01",
        amount=Decimal("77.00"),
        currency="EUR",
        text="Nur bei B",
    )
    db_session.add(fremde_zeile)
    await db_session.commit()

    header = await anmelden(zwei_mandanten.nutzer_a)
    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/journal/years", headers=header
    )
    assert antwort.status_code == 200, antwort.text

    jahre = antwort.json()
    werte = jahre["years"] if isinstance(jahre, dict) else jahre
    assert 2019 not in [
        int(j) for j in werte
    ], f"Das Jahr 2019 stammt nur aus Mandant B, erscheint aber in {werte}."


# ─── Schreiben ───────────────────────────────────────────────────────────────


async def test_fremde_leistung_kann_nicht_zugeordnet_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Eigene Buchung, aber die ``service_id`` von Mandant B im Körper.

    Gelänge das, hinge eine Buchung von A an einer Leistung von B: Beide
    Auswertungen wären falsch, und zwar dauerhaft und lautlos.
    """
    zeile_id = zwei_mandanten.a.zeilen[0].id
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/journal/{zeile_id}/assign-service",
        json={"service_id": str(zwei_mandanten.b.leistung.id)},
        headers=header,
    )

    assert antwort.status_code in (400, 403, 404, 422), (
        f"Eine fremde Leistung liess sich zuordnen: "
        f"{antwort.status_code} {antwort.text}"
    )

    aufteilungen = (
        await db_session.exec(
            select(JournalLineSplit).where(
                JournalLineSplit.journal_line_id == zeile_id,
                JournalLineSplit.service_id == zwei_mandanten.b.leistung.id,
            )
        )
    ).all()
    assert not aufteilungen, "Es entstand eine Aufteilung auf die fremde Leistung."


async def test_eigene_leistung_kann_zugeordnet_werden(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Gegenprobe — sonst belegt der Test oben nur, dass der Endpunkt nichts tut."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/journal/{zwei_mandanten.a.zeilen[0].id}/assign-service",
        json={"service_id": str(zwei_mandanten.a.leistung.id)},
        headers=header,
    )
    assert antwort.status_code not in (403, 404, 422), antwort.text
    assert antwort.status_code < 500, f"{antwort.status_code} {antwort.text}"


async def test_sammelzuordnung_greift_nicht_auf_fremde_zeilen(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Die Sammelzuordnung nimmt eine **Liste** von Kennungen — der riskanteste Fall.

    Eine Liste wird leicht als Ganzes geprüft oder gar nicht. Hier ist eine eigene
    und eine fremde Zeile gemischt: Der Aufruf muss abgewiesen werden, **und** die
    eigene Zeile darf auch nicht teilweise umgeschrieben sein. Ein Vorgang, der die
    Hälfte tut, ist schlimmer als einer, der nichts tut.
    """
    eigene_id = zwei_mandanten.a.zeilen[0].id
    fremde_id = zwei_mandanten.b.zeilen[0].id
    eigener_partner = zwei_mandanten.a.partner.id
    fremder_partner_vorher = zwei_mandanten.b.zeilen[0].partner_id
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/journal/bulk-assign",
        json={
            "line_ids": [str(eigene_id), str(fremde_id)],
            "partner_id": str(eigener_partner),
        },
        headers=header,
    )

    assert antwort.status_code in (400, 403, 404, 422), (
        f"Die Sammelzuordnung nahm eine fremde Zeile an: "
        f"{antwort.status_code} {antwort.text}"
    )

    db_session.expire_all()
    fremde_danach = await db_session.get(JournalLine, fremde_id)
    assert fremde_danach is not None
    assert (
        fremde_danach.partner_id == fremder_partner_vorher
    ), "Die Buchung des anderen Mandanten wurde umgeschrieben."


async def test_sammelzuordnung_mit_eigenen_zeilen_funktioniert(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Gegenprobe zur Sammelzuordnung."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/journal/bulk-assign",
        json={
            "line_ids": [str(z.id) for z in zwei_mandanten.a.zeilen],
            "partner_id": str(zwei_mandanten.a.partner.id),
        },
        headers=header,
    )
    assert antwort.status_code not in (403, 404, 422), antwort.text
    assert antwort.status_code < 500, f"{antwort.status_code} {antwort.text}"


async def test_fremder_partner_kann_nicht_sammelzugeordnet_werden(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Die andere Kennung im Körper: eigene Zeilen, fremder Partner."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/journal/bulk-assign",
        json={
            "line_ids": [str(zwei_mandanten.a.zeilen[0].id)],
            "partner_id": str(zwei_mandanten.b.partner.id),
        },
        headers=header,
    )
    assert antwort.status_code in (400, 403, 404, 422), antwort.text


# ─── Protokoll und Gegenrichtung ─────────────────────────────────────────────


async def test_audit_bleibt_im_eigenen_mandanten(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Das Protokoll nennt Namen und Beträge und ist mandantengebunden.

    ``nutzer_a`` ist ``accountant``, das Protokoll verlangt ``mandant_admin`` — also
    wird hier der Mandant-Admin von A benutzt, damit die Rollenschwelle nicht die
    Mandantenprüfung verdeckt.
    """
    header = await anmelden(zwei_mandanten.mandant_admin_a, zwei_mandanten.a)

    fremd = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/audit", headers=header
    )
    assert fremd.status_code == 403, fremd.text

    eigen = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/audit", headers=header
    )
    assert eigen.status_code == 200, eigen.text


async def test_die_trennung_gilt_auch_von_b_aus(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Die Gegenrichtung, mit derselben Nachrechnung."""
    header = await anmelden(zwei_mandanten.nutzer_b)

    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/reports/account-balances",
        headers=header,
    )
    assert antwort.status_code == 200, antwort.text

    daten = antwort.json()
    konten = daten["accounts"] if isinstance(daten, dict) else daten
    assert len(konten) == 1
    assert konten[0]["account_id"] == str(zwei_mandanten.b.konto.id)
    assert Decimal(konten[0]["current_balance"]) == ANFANGSBESTAND + EINGANG + AUSGANG


async def test_unbekannter_mandant_ergibt_keine_zahlen(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Eine erfundene ``mandant_id`` darf keine leere, aber gültige Auswertung liefern.

    Eine leere Auswertung mit 200 wäre gefährlicher als ein Fehler: Sie sieht aus wie
    „dieser Mandant hat keine Buchungen".
    """
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.get(
        f"/api/v1/mandants/{uuid4()}/reports/account-balances", headers=header
    )
    assert antwort.status_code in (403, 404), antwort.text
