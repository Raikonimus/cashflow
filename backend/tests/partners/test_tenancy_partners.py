"""Mandantentrennung aller Partner-Endpunkte — Stufe 3 des Mandantenfaehigkeitsplans.

Warum gerade dieses Modul zuerst: ``app/partners/service.py`` meldet mit zwölf die
meisten OFFEN-Einträge in ``check_tenancy.py`` und hatte am 2026-09-10 mit 30 % die
niedrigste Abdeckung im Projekt. Zwei unabhängige Messungen zeigten auf dieselbe
Datei, weil beide dasselbe messen: was nie unter Prüfdruck stand.

Was hier geprüft wird
---------------------
``require_mandant_access`` prueft die ``mandant_id`` aus dem Pfad — und nur die. Jede
**zweite** Kennung im selben Pfad muss der Service selbst prüfen. Bei den
Partner-Endpunkten sind das bis zu zwei weitere:

* ``partner_id`` — gehört der Partner zum Mandanten?
* ``iban_id`` / ``account_id`` / ``name_id`` — gehört das Kind zum Partner?

Der zweite Schritt ist der leicht zu vergessende. Ein Endpunkt, der nur den Partner
prüft, laesst über eine fremde ``iban_id`` Daten eines anderen Mandanten löschen.

Jeder Test hat eine Gegenprobe
------------------------------
Ein Test, der nur auf 403/404 prueft, bleibt auch bei einem Endpunkt grün, der
grundsätzlich verweigert — dann ist nicht die Trennung belegt, sondern die
Unerreichbarkeit. Deshalb steht neben jedem Angriff der Nachweis, dass derselbe Aufruf
auf die eigenen Daten funktioniert.
"""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.partners.models import Partner, PartnerAccount, PartnerIban, PartnerName
from tests.conftest import AnmeldeHelfer, ZweiMandanten

# Die Endpunkte mit einer zweiten Kennung im Pfad, als (Methode, Vorlage).
# `{m}` ist die eigene mandant_id, `{p}` die einzusetzende partner_id.
PARTNER_ENDPUNKTE: list[tuple[str, str, dict | None]] = [
    ("GET", "/api/v1/mandants/{m}/partners/{p}", None),
    ("PATCH", "/api/v1/mandants/{m}/partners/{p}", {"display_name": "Neu"}),
    ("DELETE", "/api/v1/mandants/{m}/partners/{p}", None),
    ("GET", "/api/v1/mandants/{m}/partners/{p}/neighbors", None),
    (
        "POST",
        "/api/v1/mandants/{m}/partners/{p}/ibans/preview",
        {"iban": "DE02120300000000202051"},
    ),
    (
        "POST",
        "/api/v1/mandants/{m}/partners/{p}/ibans",
        {"iban": "DE02120300000000202051"},
    ),
    (
        "POST",
        "/api/v1/mandants/{m}/partners/{p}/accounts/preview",
        {"account_number": "9999999", "blz": "99999"},
    ),
    (
        "POST",
        "/api/v1/mandants/{m}/partners/{p}/accounts",
        {"account_number": "9999999", "blz": "99999"},
    ),
    ("POST", "/api/v1/mandants/{m}/partners/{p}/names", {"name": "Zweitname"}),
]


async def _rufe(
    client: AsyncClient, methode: str, pfad: str, header: dict, koerper: dict | None
):
    """Schickt einen Aufruf und gibt die Antwort zurueck."""
    if koerper is None:
        return await client.request(methode, pfad, headers=header)
    return await client.request(methode, pfad, headers=header, json=koerper)


# ─── Fremde partner_id bei eigener mandant_id ────────────────────────────────


@pytest.mark.parametrize(
    ("methode", "vorlage", "koerper"),
    PARTNER_ENDPUNKTE,
    ids=[
        f"{m}-{v.split('/partners/{p}')[-1] or 'detail'}"
        for m, v, _ in PARTNER_ENDPUNKTE
    ],
)
async def test_fremder_partner_ist_unerreichbar(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    methode: str,
    vorlage: str,
    koerper: dict | None,
):
    """Eigene ``mandant_id`` im Pfad, ``partner_id`` von Mandant B.

    Das ist die Angriffsform, die `require_mandant_access` nicht abdeckt: Die
    ``mandant_id`` ist die eigene, also geht die Dependency zufrieden durch. Ob der
    Partner dazugehoert, muss der Service prüfen.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)
    pfad = vorlage.format(m=zwei_mandanten.a.id, p=zwei_mandanten.b.partner.id)

    antwort = await _rufe(client, methode, pfad, header, koerper)

    assert antwort.status_code in (403, 404), (
        f"{methode} {pfad} lieferte {antwort.status_code} — der fremde Partner war "
        f"erreichbar: {antwort.text}"
    )


@pytest.mark.parametrize(
    ("methode", "vorlage", "koerper"),
    PARTNER_ENDPUNKTE,
    ids=[
        f"{m}-{v.split('/partners/{p}')[-1] or 'detail'}"
        for m, v, _ in PARTNER_ENDPUNKTE
    ],
)
async def test_eigener_partner_bleibt_erreichbar(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    methode: str,
    vorlage: str,
    koerper: dict | None,
):
    """Die Gegenprobe zu jedem Angriff oben — sonst prueft der Vergleich nichts.

    Geprueft wird genau eine Eigenschaft: dass der Aufruf **an der
    Zugehoerigkeitspruefung vorbeikommt**. Nicht, dass er gelingt. Der Unterschied
    ist hier greifbar: ``DELETE`` auf den eigenen Partner ergibt 409, weil er
    Buchungen hat — ein fachlicher Einwand, der erst *nach* der Mandantenpruefung
    entsteht und deshalb genau das belegt, was dieser Test zeigen soll.

    Deshalb die Bedingung „nicht 403/404 und kein Serverfehler" statt „2xx". Ein
    ``assert 2xx`` haette den Endpunkt gezwungen, fachlich erfolgreich zu sein, und
    damit etwas anderes geprueft als die Mandantentrennung.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)
    pfad = vorlage.format(m=zwei_mandanten.a.id, p=zwei_mandanten.a.partner.id)

    antwort = await _rufe(client, methode, pfad, header, koerper)

    # 422 zaehlt hier als Fehlschlag der Gegenprobe: Eine Eingabepruefung schlaegt
    # zu, *bevor* der Aufruf die Zugehoerigkeitspruefung erreicht. Ein solcher Test
    # wuerde gruen bleiben, ohne die Trennung belegt zu haben — etwa bei einem
    # falsch aufgebauten Koerper in der Endpunktliste oben.
    assert antwort.status_code not in (403, 404, 422), (
        f"{methode} {pfad} verweigert auch den eigenen Partner "
        f"({antwort.status_code}) — dann belegt der Gegentest keine "
        f"Mandantentrennung, sondern die Unerreichbarkeit: {antwort.text}"
    )
    assert antwort.status_code < 500, (
        f"{methode} {pfad} endet in einem Serverfehler: "
        f"{antwort.status_code} {antwort.text}"
    )


async def test_erfundene_partner_id_ist_nicht_besser_gestellt(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Eine nicht existierende Kennung darf nicht anders behandelt werden als eine fremde.

    Unterscheiden sich die Antworten, ist an ihnen ablesbar, welche Partner es in
    anderen Mandanten gibt.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)

    fremd = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/partners/{zwei_mandanten.b.partner.id}",
        headers=header,
    )
    erfunden = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/partners/{uuid4()}", headers=header
    )

    assert fremd.status_code == erfunden.status_code, (
        f"Fremder Partner ergibt {fremd.status_code}, erfundener "
        f"{erfunden.status_code} — daran ist seine Existenz ablesbar."
    )


# ─── Dritte Kennung: die Kinder des Partners ─────────────────────────────────


async def test_fremde_iban_kann_nicht_entfernt_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Eigener Mandant, **eigener** Partner — aber die ``iban_id`` von Mandant B.

    Der gefaehrlichste Zuschnitt: Ein Service, der nur den Partner prueft, laesst
    hier eine fremde Zeile loeschen. Deshalb wird nicht nur die Antwort geprueft,
    sondern auch, dass die Zeile noch existiert.
    """
    fremde_iban_id = zwei_mandanten.b.partner_iban.id
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/partners/{zwei_mandanten.a.partner.id}/ibans/{fremde_iban_id}",
        headers=header,
    )

    assert antwort.status_code in (403, 404), antwort.text
    noch_da = (
        await db_session.exec(
            select(PartnerIban).where(PartnerIban.id == fremde_iban_id)
        )
    ).first()
    assert noch_da is not None, "Die IBAN eines fremden Mandanten wurde geloescht."


async def test_eigene_iban_kann_entfernt_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Gegenprobe: Der eigene Eintrag verschwindet tatsaechlich."""
    eigene_iban_id = zwei_mandanten.a.partner_iban.id
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/partners/{zwei_mandanten.a.partner.id}/ibans/{eigene_iban_id}",
        headers=header,
    )

    assert antwort.status_code == 204, antwort.text
    weg = (
        await db_session.exec(
            select(PartnerIban).where(PartnerIban.id == eigene_iban_id)
        )
    ).first()
    assert weg is None


async def test_fremdes_partnerkonto_kann_nicht_entfernt_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Dasselbe Muster fuer BLZ + Kontonummer."""
    fremd_id = zwei_mandanten.b.partner_konto.id
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/partners/{zwei_mandanten.a.partner.id}/accounts/{fremd_id}",
        headers=header,
    )

    assert antwort.status_code in (403, 404), antwort.text
    noch_da = (
        await db_session.exec(
            select(PartnerAccount).where(PartnerAccount.id == fremd_id)
        )
    ).first()
    assert (
        noch_da is not None
    ), "Das Partnerkonto eines fremden Mandanten wurde geloescht."


async def test_eigenes_partnerkonto_kann_entfernt_werden(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Gegenprobe zum Partnerkonto."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/partners/{zwei_mandanten.a.partner.id}"
        f"/accounts/{zwei_mandanten.a.partner_konto.id}",
        headers=header,
    )
    assert antwort.status_code == 204, antwort.text


async def test_fremder_zusatzname_kann_nicht_entfernt_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Und fuer den Zusatznamen."""
    fremd_id = zwei_mandanten.b.partner_name.id
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/partners/{zwei_mandanten.a.partner.id}/names/{fremd_id}",
        headers=header,
    )

    assert antwort.status_code in (403, 404), antwort.text
    noch_da = (
        await db_session.exec(select(PartnerName).where(PartnerName.id == fremd_id))
    ).first()
    assert (
        noch_da is not None
    ), "Der Zusatzname eines fremden Mandanten wurde geloescht."


async def test_eigener_zusatzname_kann_entfernt_werden(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Gegenprobe zum Zusatznamen."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/partners/{zwei_mandanten.a.partner.id}"
        f"/names/{zwei_mandanten.a.partner_name.id}",
        headers=header,
    )
    assert antwort.status_code == 204, antwort.text


# ─── Zusammenfuehren: zwei Kennungen im Koerper ──────────────────────────────


async def test_fremder_partner_kann_nicht_hineingemischt_werden(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Beim Zusammenfuehren stehen die Kennungen im Koerper, nicht im Pfad.

    Damit greift keine Pfadpruefung — und der Vorgang schreibt: Er verschiebt IBANs,
    Kontonummern, Namen und Buchungszeilen von einem Partner auf einen anderen.
    Waere die Herkunft ungeprueft, liessen sich damit Daten zwischen Mandanten
    verschieben, und zwar unwiederbringlich.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/partners/merge",
        json={
            "source_partner_id": str(zwei_mandanten.b.partner.id),
            "target_partner_id": str(zwei_mandanten.a.partner.id),
        },
        headers=header,
    )

    assert antwort.status_code in (403, 404), (
        f"Ein fremder Partner liess sich zusammenfuehren: "
        f"{antwort.status_code} {antwort.text}"
    )

    fremder = await db_session.get(Partner, zwei_mandanten.b.partner.id)
    assert fremder is not None
    assert (
        fremder.is_active
    ), "Der fremde Partner wurde beim Zusammenfuehren stillgelegt."
    assert fremder.mandant_id == zwei_mandanten.b.id


async def test_fremdes_ziel_kann_nicht_beliefert_werden(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Die Gegenrichtung: eigener Quellpartner, fremdes Ziel.

    Ohne diesen Fall wuerde nur eine der beiden Kennungen geprueft.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/partners/merge",
        json={
            "source_partner_id": str(zwei_mandanten.a.partner.id),
            "target_partner_id": str(zwei_mandanten.b.partner.id),
        },
        headers=header,
    )
    assert antwort.status_code in (400, 403, 404), antwort.text


# ─── Listen und Auswertungen ─────────────────────────────────────────────────


async def test_partnerliste_zeigt_nur_den_eigenen_mandanten(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Beide Mandanten haben einen Partner **gleichen Namens**.

    Das ist der Grund für die Namensgleichheit in der Fixture: Eine Abfrage ohne
    Mandantenfilter liefert hier zwei Treffer statt einem und fällt auf. Mit
    verschiedenen Namen wäre derselbe Fehler unsichtbar.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)

    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/partners", headers=header
    )
    assert antwort.status_code == 200, antwort.text

    daten = antwort.json()
    eintraege = daten["items"] if isinstance(daten, dict) else daten
    ids = {UUID(e["id"]) for e in eintraege}

    assert zwei_mandanten.a.partner.id in ids
    assert (
        zwei_mandanten.b.partner.id not in ids
    ), "Die Partnerliste enthaelt den gleichnamigen Partner des anderen Mandanten."


async def test_audit_log_bleibt_im_eigenen_mandanten(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Das Protokoll ist mandantengebunden — es nennt Namen und Betraege."""
    header = await anmelden(zwei_mandanten.nutzer_a)

    fremd = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/audit-log", headers=header
    )
    assert fremd.status_code == 403, fremd.text

    eigen = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/audit-log", headers=header
    )
    assert eigen.status_code == 200, eigen.text


# ─── Die Gegenrichtung ───────────────────────────────────────────────────────


async def test_die_trennung_gilt_in_beide_richtungen(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Dieselbe Pruefung mit ``nutzer_b``.

    Eine Trennung, die nur in einer Richtung geprueft wird, kann an einer
    Verwechslung von „eigen" und „fremd" haengen, die genau einmal aufgeht.
    """
    header = await anmelden(zwei_mandanten.nutzer_b)

    fremd = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/partners/{zwei_mandanten.a.partner.id}",
        headers=header,
    )
    assert fremd.status_code in (403, 404), fremd.text

    eigen = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/partners/{zwei_mandanten.b.partner.id}",
        headers=header,
    )
    assert eigen.status_code == 200, eigen.text


async def test_nutzer_beider_mandanten_erreicht_beide(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """``nutzer_beide`` darf beide sehen — die Trennung ist keine Abschottung.

    Die Aussage ist unveraendert, der Weg dorthin nicht. Bis Stufe 5 genuegte **ein**
    Token: Es war fuer A gewaehlt und wirkte auch auf B, weil
    ``require_mandant_access`` nur die Mitgliedschaft pruefte (Befund M10). Seit
    ADR-019 ist die Auswahl eine Grenze, und der Nutzer muss den Mandanten benennen,
    in dem er arbeitet.

    Was der Test damit prueft, ist genau das Verbleibende: Die Zuordnung zu zwei
    Mandanten ist echt, und keiner der beiden ist ihm verschlossen. Dass ein fuer A
    gewaehltes Token B **nicht** mehr erreicht, prueft
    ``tests/tenancy/test_token_und_pfad.py``.
    """
    for welt in (zwei_mandanten.a, zwei_mandanten.b):
        header = await anmelden(zwei_mandanten.nutzer_beide, welt)
        antwort = await client.get(
            f"/api/v1/mandants/{welt.id}/partners/{welt.partner.id}", headers=header
        )
        assert antwort.status_code == 200, f"{welt.mandant.name}: {antwort.text}"
