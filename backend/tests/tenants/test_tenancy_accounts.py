"""Mandantentrennung aller Konto-Endpunkte — Stufe 3 des Mandantenfaehigkeitsplans.

Letztes Modul der Empfehlung: ``app/tenants/service.py`` meldet zwei OFFEN-Einträge
und stand am 2026-09-10 bei 42,7 % Abdeckung.

Warum das Konto der empfindlichste Anker ist
--------------------------------------------
``accounts`` ist die Tabelle, über die fast alles andere seinen Mandanten findet.
``JournalLine`` trägt keine ``mandant_id`` — sie hängt an ``account_id``, und die
hängt am Mandanten. Wer über eine fremde ``account_id`` hineinkommt, erreicht damit
nicht ein Konto, sondern dessen gesamte Buchungshistorie.

Deshalb sind hier gerade die *schreibenden* Endpunkte kritisch. Die Spaltenzuordnung
(`column-mapping`) und `remap` schreiben Buchungsdaten um; `excluded-identifiers/apply`
löst Partnerzuordnungen wieder auf. Zwei dieser Wege hatten in Etappe 1 des Reviews
ein Leck — ``test_tenancy_apply_excluded.py`` ist der Test, der daraus entstand.
Diese Datei zieht denselben Angriff über **alle** Konto-Endpunkte.

Ein bereits bekannter Nebenpunkt
--------------------------------
``create_account`` prüft die IBAN **global** auf Eindeutigkeit und antwortet mit 409
„IBAN already in use", auch wenn sie einem anderen Mandanten gehört. Das ist die
offene Konto-IBAN-Frage aus Stufe 5, kein Zugriffsleck — aber es verrät, dass eine
IBAN anderswo im System vergeben ist. Der letzte Test hält das als heutigen Stand
fest, damit eine Entscheidung dazu nicht unbemerkt verlorengeht.
"""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.imports.models import JournalLine
from app.tenants.models import Account, AccountExcludedIdentifier
from tests.conftest import AnmeldeHelfer, ZweiMandanten

# Endpunkte mit fremder `account_id` bei eigener `mandant_id`.
# `{m}` = eigene mandant_id, `{k}` = einzusetzende account_id.
KONTO_ENDPUNKTE: list[tuple[str, str, dict | None, str]] = [
    ("GET", "/api/v1/mandants/{m}/accounts/{k}", None, "detail"),
    (
        "PATCH",
        "/api/v1/mandants/{m}/accounts/{k}",
        {"name": "Umbenannt"},
        "aendern",
    ),
    (
        "GET",
        "/api/v1/mandants/{m}/accounts/{k}/column-mapping",
        None,
        "zuordnung-lesen",
    ),
    (
        "POST",
        "/api/v1/mandants/{m}/accounts/{k}/remap",
        None,
        "remap",
    ),
    (
        "GET",
        "/api/v1/mandants/{m}/accounts/{k}/excluded-identifiers",
        None,
        "ausschluesse-lesen",
    ),
    (
        "POST",
        "/api/v1/mandants/{m}/accounts/{k}/excluded-identifiers",
        {"identifier_type": "iban", "value": "DE02120300000000202051"},
        "ausschluss-anlegen",
    ),
    (
        "POST",
        "/api/v1/mandants/{m}/accounts/{k}/excluded-identifiers/apply",
        None,
        "ausschluesse-anwenden",
    ),
    ("GET", "/api/v1/mandants/{m}/accounts/{k}/imports", None, "importe-lesen"),
]


async def _rufe(
    client: AsyncClient, methode: str, pfad: str, header: dict, koerper: dict | None
):
    """Schickt einen Aufruf und gibt die Antwort zurueck."""
    if koerper is None:
        return await client.request(methode, pfad, headers=header)
    return await client.request(methode, pfad, headers=header, json=koerper)


# ─── Fremdes Konto ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("methode", "vorlage", "koerper", "_name"),
    KONTO_ENDPUNKTE,
    ids=[e[3] for e in KONTO_ENDPUNKTE],
)
async def test_fremdes_konto_ist_unerreichbar(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    methode: str,
    vorlage: str,
    koerper: dict | None,
    _name: str,
):
    """Eigene ``mandant_id`` im Pfad, ``account_id`` von Mandant B.

    ``require_mandant_access`` geht hier zufrieden durch — die ``mandant_id`` ist die
    eigene. Ob das Konto dazugehört, muss der Service prüfen.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)
    pfad = vorlage.format(m=zwei_mandanten.a.id, k=zwei_mandanten.b.konto.id)

    antwort = await _rufe(client, methode, pfad, header, koerper)

    assert antwort.status_code in (403, 404), (
        f"{methode} {pfad} lieferte {antwort.status_code} — das fremde Konto war "
        f"erreichbar: {antwort.text}"
    )


@pytest.mark.parametrize(
    ("methode", "vorlage", "koerper", "_name"),
    KONTO_ENDPUNKTE,
    ids=[e[3] for e in KONTO_ENDPUNKTE],
)
async def test_eigenes_konto_bleibt_erreichbar(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    methode: str,
    vorlage: str,
    koerper: dict | None,
    _name: str,
):
    """Gegenprobe: nicht 403/404/422 und kein Serverfehler.

    Ein 422 zählt als Fehlschlag der Gegenprobe — es bedeutet, dass eine
    Eingabeprüfung zuschlug, *bevor* die Zugehörigkeit geprüft wurde, und belegt
    daher nichts.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)
    pfad = vorlage.format(m=zwei_mandanten.a.id, k=zwei_mandanten.a.konto.id)

    antwort = await _rufe(client, methode, pfad, header, koerper)

    assert antwort.status_code not in (403, 404, 422), (
        f"{methode} {pfad} verweigert auch das eigene Konto "
        f"({antwort.status_code}): {antwort.text}"
    )
    assert antwort.status_code < 500, f"{antwort.status_code} {antwort.text}"


async def test_kontenliste_zeigt_nur_eigene(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Genau ein Konto — nicht zwei."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/accounts", headers=header
    )
    assert antwort.status_code == 200, antwort.text

    daten = antwort.json()
    eintraege = daten["items"] if isinstance(daten, dict) else daten
    ids = {UUID(e["id"]) for e in eintraege}

    assert ids == {
        zwei_mandanten.a.konto.id
    }, f"Erwartet nur das eigene Konto, erhalten {ids}"


async def test_erfundenes_konto_ist_nicht_besser_gestellt(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Fremd und erfunden muessen dieselbe Antwort ergeben."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    fremd = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/accounts/{zwei_mandanten.b.konto.id}",
        headers=header,
    )
    erfunden = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/accounts/{uuid4()}", headers=header
    )

    assert fremd.status_code == erfunden.status_code, (
        f"Fremdes Konto ergibt {fremd.status_code}, erfundenes "
        f"{erfunden.status_code} — daran ist seine Existenz ablesbar."
    )


# ─── Die schreibenden Wege, mit Nachweis am Bestand ──────────────────────────


async def test_fremdes_konto_wird_nicht_umbenannt(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Die Absage allein genuegt nicht — der Name muss unveraendert sein."""
    fremd_id = zwei_mandanten.b.konto.id
    vorher = zwei_mandanten.b.konto.name
    header = await anmelden(zwei_mandanten.nutzer_a)

    await client.patch(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/accounts/{fremd_id}",
        json={"name": "Uebernommen"},
        headers=header,
    )

    db_session.expire_all()
    danach = await db_session.get(Account, fremd_id)
    assert danach is not None
    assert danach.name == vorher, "Das Konto eines fremden Mandanten wurde umbenannt."


async def test_fremde_buchungen_werden_nicht_umgeschrieben(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """``excluded-identifiers/apply`` schreibt Partnerzuordnungen um.

    Das ist derselbe Pfad, der in Etappe 1 des Reviews ein Leck hatte. Hier mit einer
    ausgeschlossenen Kennung, die tatsaechlich greifen wuerde — sonst haette der
    Endpunkt nichts zu tun und der Test wuerde auch bei fehlender Pruefung gruen
    bleiben.
    """
    fremde_zeile_id = zwei_mandanten.b.zeilen[1].id
    partner_vorher = zwei_mandanten.b.zeilen[1].partner_id
    assert partner_vorher is not None

    db_session.add(
        AccountExcludedIdentifier(
            account_id=zwei_mandanten.b.konto.id,
            identifier_type="iban",
            value=zwei_mandanten.b.iban,
        )
    )
    await db_session.commit()

    header = await anmelden(zwei_mandanten.nutzer_a)
    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/accounts/{zwei_mandanten.b.konto.id}/excluded-identifiers/apply",
        headers=header,
    )
    assert antwort.status_code in (403, 404), antwort.text

    db_session.expire_all()
    danach = (
        await db_session.exec(
            select(JournalLine).where(JournalLine.id == fremde_zeile_id)
        )
    ).first()
    assert danach is not None
    assert (
        danach.partner_id == partner_vorher
    ), "Die Buchungszeile eines fremden Mandanten wurde umgeschrieben."


async def test_fremder_ausschluss_kann_nicht_entfernt_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Dritte Kennung im Pfad: eigenes Konto, fremde ``identifier_id``.

    Wieder der zweistufige Fall — der Endpunkt muss Konto **und** Kind prüfen.
    """
    fremder_ausschluss = AccountExcludedIdentifier(
        account_id=zwei_mandanten.b.konto.id,
        identifier_type="iban",
        value=zwei_mandanten.b.iban,
    )
    db_session.add(fremder_ausschluss)
    await db_session.commit()
    await db_session.refresh(fremder_ausschluss)
    fremd_id = fremder_ausschluss.id

    header = await anmelden(zwei_mandanten.nutzer_a)
    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/accounts/{zwei_mandanten.a.konto.id}/excluded-identifiers/{fremd_id}",
        headers=header,
    )

    assert antwort.status_code in (403, 404), antwort.text
    assert await db_session.get(AccountExcludedIdentifier, fremd_id) is not None


async def test_eigener_ausschluss_kann_entfernt_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Gegenprobe zum Ausschluss."""
    eigener = AccountExcludedIdentifier(
        account_id=zwei_mandanten.a.konto.id,
        identifier_type="iban",
        value=zwei_mandanten.a.iban,
    )
    db_session.add(eigener)
    await db_session.commit()
    await db_session.refresh(eigener)
    eigen_id = eigener.id

    header = await anmelden(zwei_mandanten.nutzer_a)
    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/accounts/{zwei_mandanten.a.konto.id}/excluded-identifiers/{eigen_id}",
        headers=header,
    )

    assert antwort.status_code in (200, 204), antwort.text
    assert await db_session.get(AccountExcludedIdentifier, eigen_id) is None


# ─── Die Gegenrichtung ───────────────────────────────────────────────────────


async def test_die_trennung_gilt_auch_von_b_aus(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Eine Verwechslung von eigen und fremd kann in genau einer Richtung aufgehen."""
    header = await anmelden(zwei_mandanten.nutzer_b)

    fremd = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/accounts/{zwei_mandanten.a.konto.id}",
        headers=header,
    )
    assert fremd.status_code in (403, 404), fremd.text

    eigen = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/accounts/{zwei_mandanten.b.konto.id}",
        headers=header,
    )
    assert eigen.status_code == 200, eigen.text


# ─── Heutiger Stand zur Konto-IBAN (Stufe 5) ─────────────────────────────────


async def test_fremde_iban_blockiert_das_anlegen_eines_kontos(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Kein Leck, aber eine Auskunft — und eine offene Entscheidung.

    ``create_account`` prüft die IBAN global. Legt Mandant A ein Konto mit einer IBAN
    an, die Mandant B schon führt, kommt 409 „IBAN already in use". Zwei Firmen
    desselben Eigentümers mit einem gemeinsamen Konto können es also nicht beide
    erfassen — und die Antwort verrät, dass diese IBAN irgendwo im System vergeben
    ist.

    Dieser Test hält den **heutigen** Stand fest, er verteidigt ihn nicht. Fällt die
    Entscheidung in Stufe 5 anders (IBAN je Mandant eindeutig), schlägt er an und
    muss mit ihr geändert werden — das ist Absicht.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)

    # Erst ein Konto in Mandant B mit einer bekannten IBAN versehen.
    fremde_iban = "DE02500105170137075030"
    admin_header = await anmelden(zwei_mandanten.admin, zwei_mandanten.b)
    angelegt = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/accounts",
        json={"name": "Konto mit IBAN", "iban": fremde_iban, "currency": "EUR"},
        headers=admin_header,
    )
    assert angelegt.status_code == 201, angelegt.text

    # Dieselbe IBAN in Mandant A: heute abgelehnt.
    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/accounts",
        json={"name": "Eigenes Konto", "iban": fremde_iban, "currency": "EUR"},
        headers=header,
    )
    assert antwort.status_code == 409, (
        f"Heutiger Stand ist 409 (ADR-008, Konto-IBAN-Frage aus Stufe 5), "
        f"erhalten {antwort.status_code}: {antwort.text}"
    )
