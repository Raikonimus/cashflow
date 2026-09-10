"""Mandantentrennung aller Leistungs-Endpunkte — Stufe 3 des Mandantenfaehigkeitsplans.

Zweites Modul nach OFFEN-Dichte: ``app/services/service.py`` meldet neun
OFFEN-Einträge und stand am 2026-09-10 bei 41 % Abdeckung.

Die Tiefe ist hier größer als bei den Partnern, und darin liegt das Risiko. Eine
Leistung trägt **keine** ``mandant_id`` — ihre Zugehörigkeit hängt an
``partner_id``. Ein Matcher hängt an ``service_id``, also zwei Ebenen tief. Wer vom
Matcher zum Mandanten will, muss über drei Tabellen joinen:

    service_matchers → services → partners → mandant_id

Genau solche Ketten meint der Befund M11: Die Trennung hängt an der Sorgfalt jeder
einzelnen Query, nicht an der Struktur.

Schlagwörter und Gruppen sind dagegen direkt gebunden — und ``mandant_id`` ist bei
``service_type_keywords`` sogar **nullbar**, weil ein Schlagwort ohne Mandanten global
gilt. Ein vergessener Filter fällt dort also nicht durch einen Fehler auf, sondern
liefert stillschweigend mehr.

Wie in ``test_tenancy_partners.py`` steht neben jedem Angriff eine Gegenprobe: Sie
zeigt, dass derselbe Aufruf an der Zugehörigkeitsprüfung vorbeikommt — nicht, dass er
fachlich gelingt.
"""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.services.models import (
    Service,
    ServiceGroup,
    ServiceMatcher,
    ServiceTypeKeyword,
)
from tests.conftest import GRUPPEN_NAME, LEISTUNG_NAME, AnmeldeHelfer, ZweiMandanten

# Endpunkte mit fremder `service_id` bei eigener `mandant_id`.
# `{m}` = eigene mandant_id, `{s}` = einzusetzende service_id.
LEISTUNGS_ENDPUNKTE: list[tuple[str, str, dict | None, str]] = [
    ("PATCH", "/api/v1/mandants/{m}/services/{s}", {"name": "Umbenannt"}, "aendern"),
    ("DELETE", "/api/v1/mandants/{m}/services/{s}", None, "loeschen"),
    (
        "POST",
        "/api/v1/mandants/{m}/services/{s}/matchers",
        {"pattern": "Neu", "pattern_type": "string"},
        "matcher-anlegen",
    ),
    (
        "POST",
        "/api/v1/mandants/{m}/services/{s}/matchers/preview",
        {"pattern": "Neu", "pattern_type": "string"},
        "matcher-vorschau",
    ),
]


async def _rufe(
    client: AsyncClient, methode: str, pfad: str, header: dict, koerper: dict | None
):
    """Schickt einen Aufruf und gibt die Antwort zurueck."""
    if koerper is None:
        return await client.request(methode, pfad, headers=header)
    return await client.request(methode, pfad, headers=header, json=koerper)


# ─── Fremde Leistung ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("methode", "vorlage", "koerper", "_name"),
    LEISTUNGS_ENDPUNKTE,
    ids=[e[3] for e in LEISTUNGS_ENDPUNKTE],
)
async def test_fremde_leistung_ist_unerreichbar(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    methode: str,
    vorlage: str,
    koerper: dict | None,
    _name: str,
):
    """Eigene ``mandant_id``, ``service_id`` von Mandant B.

    Die Leistung hat keine eigene ``mandant_id`` — der Service muss über den Partner
    zurückrechnen. Ein fehlender Schritt in dieser Kette ist von außen nicht
    erkennbar und liefert einfach ein Ergebnis.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)
    pfad = vorlage.format(m=zwei_mandanten.a.id, s=zwei_mandanten.b.leistung.id)

    antwort = await _rufe(client, methode, pfad, header, koerper)

    assert antwort.status_code in (403, 404), (
        f"{methode} {pfad} lieferte {antwort.status_code} — die fremde Leistung war "
        f"erreichbar: {antwort.text}"
    )


@pytest.mark.parametrize(
    ("methode", "vorlage", "koerper", "_name"),
    LEISTUNGS_ENDPUNKTE,
    ids=[e[3] for e in LEISTUNGS_ENDPUNKTE],
)
async def test_eigene_leistung_bleibt_erreichbar(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    methode: str,
    vorlage: str,
    koerper: dict | None,
    _name: str,
):
    """Gegenprobe: nicht 403/404 und kein Serverfehler.

    Bewusst nicht „2xx": Löschen kann fachlich abgelehnt werden, wenn Buchungen an
    der Leistung hängen. Ein solcher Einwand entsteht erst *nach* der
    Mandantenprüfung und belegt damit genau, was hier gezeigt werden soll.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)
    pfad = vorlage.format(m=zwei_mandanten.a.id, s=zwei_mandanten.a.leistung.id)

    antwort = await _rufe(client, methode, pfad, header, koerper)

    # 422 zaehlt hier als Fehlschlag der Gegenprobe: Eine Eingabepruefung schlaegt
    # zu, *bevor* der Aufruf die Zugehoerigkeitspruefung erreicht. Ein solcher Test
    # wuerde gruen bleiben, ohne die Trennung belegt zu haben — etwa bei einem
    # falsch aufgebauten Koerper in der Endpunktliste oben.
    assert antwort.status_code not in (403, 404, 422), (
        f"{methode} {pfad} verweigert auch die eigene Leistung "
        f"({antwort.status_code}): {antwort.text}"
    )
    assert antwort.status_code < 500, f"{antwort.status_code} {antwort.text}"


async def test_fremde_leistung_wird_nicht_geloescht(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Die Absage allein genügt nicht — die Zeile muss noch da sein.

    Ein Endpunkt könnte löschen und danach scheitern; der Statuscode sähe dann
    richtig aus.
    """
    fremd_id = zwei_mandanten.b.leistung.id
    header = await anmelden(zwei_mandanten.nutzer_a)

    await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/services/{fremd_id}", headers=header
    )

    noch_da = await db_session.get(Service, fremd_id)
    assert noch_da is not None, "Die Leistung eines fremden Mandanten wurde geloescht."


async def test_fremder_partner_bekommt_keine_leistung(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Anlegen unter einem fremden Partner — der Weg *hinein* statt heraus.

    Gelänge das, entstünde eine Leistung, die über ihren Partner zu Mandant B
    gehört, aber von Mandant A angelegt wurde. Kein Lesezugriff, sondern eine
    Verunreinigung fremder Daten.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/partners/{zwei_mandanten.b.partner.id}/services",
        json={"name": "Eingeschmuggelt", "service_type": "supplier"},
        headers=header,
    )

    assert antwort.status_code in (403, 404), antwort.text

    fremde = (
        await db_session.exec(
            select(Service).where(Service.partner_id == zwei_mandanten.b.partner.id)
        )
    ).all()
    assert [s.name for s in fremde] == [
        LEISTUNG_NAME
    ], "Beim fremden Partner ist eine Leistung entstanden."


async def test_leistungsliste_bleibt_beim_eigenen_partner(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Beide Mandanten haben eine Leistung gleichen Namens unter gleichnamigen Partnern.

    Eine Abfrage, die nur nach dem Namen sucht, liefert hier zwei Treffer.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/partners/{zwei_mandanten.a.partner.id}/services",
        headers=header,
    )
    assert antwort.status_code == 200, antwort.text

    daten = antwort.json()
    eintraege = daten["items"] if isinstance(daten, dict) else daten
    ids = {UUID(e["id"]) for e in eintraege}

    assert zwei_mandanten.a.leistung.id in ids
    assert (
        zwei_mandanten.b.leistung.id not in ids
    ), "Die Leistungsliste enthaelt die gleichnamige Leistung des anderen Mandanten."


# ─── Dritte Ebene: Matcher ───────────────────────────────────────────────────


async def test_fremder_matcher_kann_nicht_geaendert_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Eigene Leistung im Pfad, ``matcher_id`` von Mandant B.

    Zwei Ebenen unter dem Mandanten. Ein Matcher entscheidet, welche Buchungen einer
    Leistung zugeordnet werden — wer ihn ändert, verändert fremde Auswertungen.
    """
    fremd_id = zwei_mandanten.b.matcher.id
    vorher = zwei_mandanten.b.matcher.pattern
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.patch(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/services/{zwei_mandanten.a.leistung.id}/matchers/{fremd_id}",
        json={"pattern": "Uebernommen", "pattern_type": "string"},
        headers=header,
    )

    assert antwort.status_code in (403, 404), antwort.text
    danach = await db_session.get(ServiceMatcher, fremd_id)
    assert danach is not None
    assert (
        danach.pattern == vorher
    ), "Der Matcher eines fremden Mandanten wurde geaendert."


async def test_fremder_matcher_kann_nicht_entfernt_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Dasselbe fuer das Loeschen."""
    fremd_id = zwei_mandanten.b.matcher.id
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/services/{zwei_mandanten.a.leistung.id}/matchers/{fremd_id}",
        headers=header,
    )

    assert antwort.status_code in (403, 404), antwort.text
    assert await db_session.get(ServiceMatcher, fremd_id) is not None


async def test_eigener_matcher_kann_entfernt_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Gegenprobe — sonst belegen die zwei Tests oben nur, dass nichts geht."""
    eigen_id = zwei_mandanten.a.matcher.id
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/services/{zwei_mandanten.a.leistung.id}/matchers/{eigen_id}",
        headers=header,
    )

    assert antwort.status_code in (200, 204), antwort.text
    assert await db_session.get(ServiceMatcher, eigen_id) is None


# ─── Direkt gebunden: Schlagwoerter ──────────────────────────────────────────


async def test_schlagwortliste_bleibt_im_eigenen_mandanten(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """``service_type_keywords.mandant_id`` ist **nullbar** — und das ist die Falle.

    Ein Schlagwort ohne Mandanten gilt global. Eine Abfrage ohne Filter liefert
    deshalb keine Fehlermeldung, sondern einfach die Schlagwoerter aller Mandanten
    zusaetzlich zu den globalen. Beide Mandanten haben hier eines mit demselben
    Muster, damit ein fehlender Filter als doppelter Treffer auffaellt.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/settings/service-keywords",
        headers=header,
    )
    assert antwort.status_code == 200, antwort.text

    daten = antwort.json()
    eintraege = daten["items"] if isinstance(daten, dict) else daten
    ids = {UUID(e["id"]) for e in eintraege}

    assert zwei_mandanten.a.schlagwort.id in ids
    assert (
        zwei_mandanten.b.schlagwort.id not in ids
    ), "Die Schlagwortliste enthaelt das Schlagwort des anderen Mandanten."


async def test_fremdes_schlagwort_kann_nicht_geaendert_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Fremde ``keyword_id`` bei eigener ``mandant_id``."""
    fremd_id = zwei_mandanten.b.schlagwort.id
    vorher = zwei_mandanten.b.schlagwort.pattern
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.patch(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/settings/service-keywords/{fremd_id}",
        json={"pattern": "Uebernommen"},
        headers=header,
    )

    assert antwort.status_code in (403, 404), antwort.text
    danach = await db_session.get(ServiceTypeKeyword, fremd_id)
    assert danach is not None and danach.pattern == vorher


async def test_fremdes_schlagwort_kann_nicht_entfernt_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Und nicht geloescht."""
    fremd_id = zwei_mandanten.b.schlagwort.id
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/settings/service-keywords/{fremd_id}",
        headers=header,
    )

    assert antwort.status_code in (403, 404), antwort.text
    assert await db_session.get(ServiceTypeKeyword, fremd_id) is not None


async def test_eigenes_schlagwort_kann_entfernt_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Gegenprobe zum Schlagwort."""
    eigen_id = zwei_mandanten.a.schlagwort.id
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/settings/service-keywords/{eigen_id}",
        headers=header,
    )

    assert antwort.status_code in (200, 204), antwort.text
    assert await db_session.get(ServiceTypeKeyword, eigen_id) is None


# ─── Direkt gebunden: Leistungsgruppen ──────────────────────────────────────


async def test_gruppenliste_bleibt_im_eigenen_mandanten(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Gleicher Gruppenname in beiden Mandanten — ein fehlender Filter zeigt zwei."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    # `section` ist ein pflichtiger Abfrageparameter — Gruppen sind je Abschnitt
    # (Einnahmen/Ausgaben/neutral) getrennt organisiert.
    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/service-groups?section=expense",
        headers=header,
    )
    assert antwort.status_code == 200, antwort.text

    daten = antwort.json()
    eintraege = daten["items"] if isinstance(daten, dict) else daten
    passende = [e for e in eintraege if e["name"] == GRUPPEN_NAME]

    assert len(passende) == 1, (
        f"{len(passende)} Gruppen mit dem Namen {GRUPPEN_NAME!r} — beide Mandanten "
        f"haben eine, es darf nur die eigene erscheinen."
    )
    assert UUID(passende[0]["id"]) == zwei_mandanten.a.gruppe.id


async def test_fremde_gruppe_kann_nicht_geaendert_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Fremde ``group_id`` bei eigener ``mandant_id``."""
    fremd_id = zwei_mandanten.b.gruppe.id
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.patch(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/service-groups/{fremd_id}",
        json={"name": "Uebernommen"},
        headers=header,
    )

    assert antwort.status_code in (403, 404), antwort.text
    danach = await db_session.get(ServiceGroup, fremd_id)
    assert danach is not None and danach.name == GRUPPEN_NAME


async def test_fremde_gruppe_kann_nicht_zugewiesen_werden(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Eigene Leistung, fremde Gruppe — die Zuweisung verbindet zwei Mandanten.

    Der gefaehrlichste Fall dieser Gruppe: Gelänge er, stünde eine Leistung von
    Mandant A in einer Gruppe von Mandant B, und beide Auswertungen wären falsch.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/services/{zwei_mandanten.a.leistung.id}/group-assignment",
        json={"service_group_id": str(zwei_mandanten.b.gruppe.id)},
        headers=header,
    )

    assert antwort.status_code in (400, 403, 404), (
        f"Eine Leistung liess sich einer fremden Gruppe zuweisen: "
        f"{antwort.status_code} {antwort.text}"
    )


async def test_eigene_gruppe_kann_zugewiesen_werden(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Gegenprobe: mit der eigenen Gruppe geht es."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/services/{zwei_mandanten.a.leistung.id}/group-assignment",
        json={"service_group_id": str(zwei_mandanten.a.gruppe.id)},
        headers=header,
    )
    assert antwort.status_code not in (403, 404), antwort.text
    assert antwort.status_code < 500, f"{antwort.status_code} {antwort.text}"


# ─── Beide Richtungen ────────────────────────────────────────────────────────


async def test_die_trennung_gilt_auch_von_b_aus(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Dieselbe Prüfung mit ``nutzer_b`` — eine Verwechslung von eigen und fremd
    kann genau in einer Richtung aufgehen."""
    header = await anmelden(zwei_mandanten.nutzer_b)

    fremd = await client.patch(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/services/{zwei_mandanten.a.leistung.id}",
        json={"name": "Uebernommen"},
        headers=header,
    )
    assert fremd.status_code in (403, 404), fremd.text

    eigen = await client.patch(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/services/{zwei_mandanten.b.leistung.id}",
        json={"name": "Eigen umbenannt"},
        headers=header,
    )
    assert eigen.status_code not in (403, 404), eigen.text


async def test_erfundene_leistung_ist_nicht_besser_gestellt(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Fremd und erfunden muessen dieselbe Antwort ergeben."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    fremd = await client.patch(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/services/{zwei_mandanten.b.leistung.id}",
        json={"name": "X"},
        headers=header,
    )
    erfunden = await client.patch(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/services/{uuid4()}",
        json={"name": "X"},
        headers=header,
    )

    assert fremd.status_code == erfunden.status_code, (
        f"Fremde Leistung ergibt {fremd.status_code}, erfundene "
        f"{erfunden.status_code} — daran ist ihre Existenz ablesbar."
    )
