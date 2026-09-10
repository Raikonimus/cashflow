"""Mandantentrennung der Review-Endpunkte — Stufe 3 des Mandantenfaehigkeitsplans.

Drittes Modul nach OFFEN-Dichte: ``app/review/service.py`` meldet sechs
OFFEN-Einträge und stand am 2026-09-10 bei 60 % Abdeckung.

Warum dieses Modul besonders zählt
----------------------------------
Ein Review-Eintrag ist eine **Aufforderung zu einer Entscheidung** über eine Buchung:
Gehört sie zu diesem Partner? Zu dieser Leistung? Wer einen fremden Eintrag bestätigt,
ändert die Zuordnung einer Buchung in einem anderen Mandanten — und die Zahlen dort
danach. Die schreibenden Endpunkte (``confirm``, ``adjust``, ``reject``, ``reassign``,
``new-partner``) sind deshalb die riskantesten des ganzen Systems.

Eine Besonderheit im Zuschnitt
------------------------------
Der Router trägt die ``mandant_id`` im **Prefix** (``/mandants/{mandant_id}/review``),
nicht im Pfad des einzelnen Endpunkts. Für die Prüfung macht das keinen Unterschied —
``require_mandant_access`` greift genauso —, wohl aber für jede maschinelle
Endpunktzählung: Wer nur die Dekorator-Pfade liest, hält diese Endpunkte für
mandantenlos. Das ist der Grund, warum der Isolationstest in Stufe 4 seine Liste aus
den registrierten Routen der Anwendung erzeugen muss und nicht aus den Dekoratoren.

``review_items`` ist direkt gebunden (eigene ``mandant_id``), aber ``item_id`` ist
trotzdem eine zweite Kennung im Pfad und muss vom Service geprüft werden.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.imports.models import JournalLine, ReviewItem, utcnow
from tests.conftest import AnmeldeHelfer, MandantWelt, ZweiMandanten

# Die schreibenden Endpunkte, jeweils mit einem gültigen Körper.
# `{m}` = eigene mandant_id, `{i}` = einzusetzende item_id.
SCHREIBENDE_ENDPUNKTE: list[tuple[str, dict | None, str]] = [
    ("/api/v1/mandants/{m}/review/{i}/confirm", None, "confirm"),
    ("/api/v1/mandants/{m}/review/{i}/reject", None, "reject"),
]


async def _lege_review_an(
    session: AsyncSession, welt: MandantWelt, item_type: str = "name_match_with_iban"
) -> ReviewItem:
    """Legt einen offenen Review-Eintrag zur Ausgangsbuchung dieser Welt an.

    Die Einträge entstehen im Betrieb beim Import; hier direkt, weil dieser Test die
    Endpunkte prüft und nicht ihre Entstehung.
    """
    eintrag = ReviewItem(
        mandant_id=welt.id,
        item_type=item_type,
        journal_line_id=welt.zeilen[1].id,
        context={"partner_name_raw": welt.partner.name},
        status="open",
        created_at=utcnow(),
    )
    session.add(eintrag)
    await session.commit()
    await session.refresh(eintrag)
    return eintrag


# ─── Lesen ───────────────────────────────────────────────────────────────────


async def test_fremder_review_eintrag_ist_nicht_abrufbar(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Eigene ``mandant_id``, ``item_id`` von Mandant B.

    Der Eintrag nennt im Kontext den Partnernamen und über die Buchung den Betrag —
    schon das Lesen gibt fremde Geschäftsdaten heraus.
    """
    fremd = await _lege_review_an(db_session, zwei_mandanten.b)
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/review/{fremd.id}", headers=header
    )

    assert antwort.status_code in (403, 404), (
        f"Der fremde Review-Eintrag war abrufbar: "
        f"{antwort.status_code} {antwort.text}"
    )


async def test_eigener_review_eintrag_ist_abrufbar(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Gegenprobe — ohne sie belegt der Test oben nur Unerreichbarkeit."""
    eigen = await _lege_review_an(db_session, zwei_mandanten.a)
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/review/{eigen.id}", headers=header
    )
    assert antwort.status_code == 200, antwort.text


async def test_liste_zeigt_nur_eigene_eintraege(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Beide Mandanten haben einen offenen Eintrag desselben Typs.

    Eine Abfrage ohne Mandantenfilter liefert hier zwei statt einem — und weil die
    Liste die Grundlage der taeglichen Arbeit ist, würde jemand die fremde Buchung
    bearbeiten, ohne den Unterschied zu bemerken.
    """
    eigen = await _lege_review_an(db_session, zwei_mandanten.a)
    fremd = await _lege_review_an(db_session, zwei_mandanten.b)
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/review", headers=header
    )
    assert antwort.status_code == 200, antwort.text

    daten = antwort.json()
    eintraege = daten["items"] if isinstance(daten, dict) else daten
    ids = {e["id"] for e in eintraege}

    assert str(eigen.id) in ids
    assert (
        str(fremd.id) not in ids
    ), "Die Review-Liste enthaelt den Eintrag des anderen Mandanten."


async def test_archiv_zeigt_nur_eigene_eintraege(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Dasselbe fuer das Archiv — erledigte Eintraege bleiben mandantengebunden."""
    fremd = await _lege_review_an(db_session, zwei_mandanten.b)
    fremd.status = "confirmed"
    db_session.add(fremd)
    await db_session.commit()

    header = await anmelden(zwei_mandanten.nutzer_a)
    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/review/archive", headers=header
    )
    assert antwort.status_code == 200, antwort.text

    daten = antwort.json()
    eintraege = daten["items"] if isinstance(daten, dict) else daten
    assert str(fremd.id) not in {e["id"] for e in eintraege}


# ─── Schreiben — die riskanten Endpunkte ─────────────────────────────────────


@pytest.mark.parametrize(
    ("vorlage", "koerper", "_name"),
    SCHREIBENDE_ENDPUNKTE,
    ids=[e[2] for e in SCHREIBENDE_ENDPUNKTE],
)
async def test_fremder_eintrag_kann_nicht_entschieden_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
    vorlage: str,
    koerper: dict | None,
    _name: str,
):
    """Und der Eintrag muss danach unveraendert offen sein.

    Der Statuscode allein genügt nicht: Ein Endpunkt könnte entscheiden und danach
    scheitern. Deshalb wird der Zustand des fremden Eintrags nachgesehen.
    """
    fremd = await _lege_review_an(db_session, zwei_mandanten.b)
    fremd_id = fremd.id
    header = await anmelden(zwei_mandanten.nutzer_a)
    pfad = vorlage.format(m=zwei_mandanten.a.id, i=fremd_id)

    if koerper is None:
        antwort = await client.post(pfad, headers=header)
    else:
        antwort = await client.post(pfad, headers=header, json=koerper)

    assert antwort.status_code in (
        403,
        404,
    ), f"POST {pfad} lieferte {antwort.status_code}: {antwort.text}"

    db_session.expire_all()
    danach = await db_session.get(ReviewItem, fremd_id)
    assert danach is not None
    assert danach.status == "open", (
        f"Der fremde Review-Eintrag steht jetzt auf {danach.status!r} — er wurde "
        f"entschieden."
    )


async def test_eigener_eintrag_kann_bestaetigt_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Gegenprobe zum Bestaetigen.

    Geprueft wird „nicht 403/404/422": Ob die Bestaetigung fachlich durchgeht, haengt
    am Zustand des Eintrags und ist hier nicht der Gegenstand.
    """
    eigen = await _lege_review_an(db_session, zwei_mandanten.a)
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/review/{eigen.id}/confirm",
        headers=header,
    )

    assert antwort.status_code not in (403, 404, 422), antwort.text
    assert antwort.status_code < 500, f"{antwort.status_code} {antwort.text}"


async def test_fremder_partner_kann_nicht_zugewiesen_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Eigener Eintrag, aber ein Partner aus Mandant B im Koerper.

    Der gefaehrlichste Fall dieses Moduls: Die Kennung steht nicht im Pfad, also
    greift keine Pfadpruefung. Gelänge es, haenge eine Buchung von Mandant A an einem
    Partner von Mandant B — und beide Auswertungen waeren falsch, ohne dass irgendwo
    ein Fehler erscheint.
    """
    eigen = await _lege_review_an(db_session, zwei_mandanten.a)
    header = await anmelden(zwei_mandanten.nutzer_a)

    # Kennungen vor dem Verwerfen des Sitzungszustands festhalten: `expire_all()`
    # entwertet auch die Objekte der Fixture, und ein Attributzugriff darauf loest
    # danach eine synchrone Nachladung aus — in einer asynchronen Sitzung nicht
    # erlaubt (`MissingGreenlet`).
    zeile_id = zwei_mandanten.a.zeilen[1].id
    erwarteter_partner = zwei_mandanten.a.partner.id

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/review/{eigen.id}/reassign",
        json={"partner_id": str(zwei_mandanten.b.partner.id)},
        headers=header,
    )

    assert antwort.status_code in (400, 403, 404, 422), (
        f"Ein fremder Partner liess sich zuweisen: "
        f"{antwort.status_code} {antwort.text}"
    )

    db_session.expire_all()
    aktuell = await db_session.get(JournalLine, zeile_id)
    assert aktuell is not None
    assert (
        aktuell.partner_id == erwarteter_partner
    ), "Die Buchung haengt jetzt an einem Partner des anderen Mandanten."


async def test_erfundener_eintrag_ist_nicht_besser_gestellt(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Fremd und erfunden muessen dieselbe Antwort ergeben."""
    fremd = await _lege_review_an(db_session, zwei_mandanten.b)
    header = await anmelden(zwei_mandanten.nutzer_a)

    a = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/review/{fremd.id}", headers=header
    )
    b = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/review/{uuid4()}", headers=header
    )

    assert a.status_code == b.status_code, (
        f"Fremder Eintrag ergibt {a.status_code}, erfundener {b.status_code} — "
        f"daran ist seine Existenz ablesbar."
    )


async def test_die_trennung_gilt_auch_von_b_aus(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Die Gegenrichtung."""
    eintrag_a = await _lege_review_an(db_session, zwei_mandanten.a)
    eintrag_b = await _lege_review_an(db_session, zwei_mandanten.b)
    header = await anmelden(zwei_mandanten.nutzer_b)

    fremd = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/review/{eintrag_a.id}", headers=header
    )
    assert fremd.status_code in (403, 404), fremd.text

    eigen = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/review/{eintrag_b.id}", headers=header
    )
    assert eigen.status_code == 200, eigen.text
