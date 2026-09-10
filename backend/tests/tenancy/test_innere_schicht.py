"""Sonde 2 und 3 — die innere Schicht: eine fremde Objektkennung muss abgewiesen werden.

Der Unterschied zur aeusseren Schicht
-------------------------------------
Sonde 1 prueft, ob ein Nutzer den fremden Mandanten erreicht. Hier ist die
``mandant_id`` die **eigene** — die aeussere Pruefung ist also bestanden — und nur die
benannte Objektkennung gehoert zu einem anderen Mandanten. Ob das auffaellt, entscheidet
keine gemeinsame Abhaengigkeit, sondern die einzelne Query oder Validierung im Dienst.

Genau hier lagen die Lecks. Beide Befunde aus Etappe 1 des Code-Reviews und M16 aus
Stufe 3 waren von dieser Art, und keiner von ihnen ist eine Luecke in der aeusseren
Schicht.

**Sonde 2 — Kennung im Pfad.** ``.../mandants/{A}/partners/{Partner von B}``.
60 Faelle ueber 53 Endpunkte.

**Sonde 3 — Kennung im Rumpf.** ``.../mandants/{A}/journal/bulk-assign`` mit einer
``partner_id`` aus B. 14 Faelle ueber 10 Endpunkte, in beide Richtungen gefahren.
Das ist die Klasse von M16: Die
Buchungszeilen wurden gegen den Mandanten geprueft, das Zuordnungsziel nicht. Der
Aufruf antwortete mit 200 und schrieb einen Protokolleintrag.

Warum ``check_tenancy.py`` diese Klasse nicht abdeckt
-----------------------------------------------------
Die statische Pruefung sieht, ob eine ``mandant_id`` im Statement vorkommt. Bei M16 kam
sie vor — im Statement fuer die Buchungszeilen. Was fehlte, war eine Validierung des
Partners. Kein AST-Muster unterscheidet „prueft das richtige Objekt" von „prueft ein
Objekt". Dieser Test muss laufen.

Immer nur ein Feld auf einmal
-----------------------------
Wuerden alle Kennungen gleichzeitig auf B umgestellt, waere bei einer Abweisung nicht
zu erkennen, welche Pruefung gegriffen hat — und ob die anderen ueberhaupt eine haben.
``.../partners/{partner_id}/ibans/{iban_id}`` braucht zwei Aussagen: dass der Partner
zum Mandanten gehoert **und** dass die IBAN zu diesem Partner gehoert. Deshalb ein
Testfall je Kennung.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.imports.models import ReviewItem, utcnow
from app.services.models import Service, ServiceType
from tests.conftest import AnmeldeHelfer
from tests.tenancy.endpunkte import Endpunkt, registrierte_endpunkte
from tests.tenancy.erwartungen import sichere_abweisung, sichere_gegenprobe
from tests.tenancy.sonden import (
    Pruefstand,
    akteur,
    angreifbare_pfadkennungen,
    baue_rumpf,
    pfadkennungen,
    rumpfkennungen,
    stelle,
)

#: Faelle, die sich nicht generisch sondieren lassen — Schluessel ``"<Endpunkt> → <Feld>"``.
#:
#: Ratsche: darf kuerzer werden, nie laenger. ``test_endpunktliste.py`` haelt die Laenge
#: fest und prueft, dass jeder Eintrag noch einem echten Fall entspricht — ein Eintrag
#: fuer einen Endpunkt, den es nicht mehr gibt, waere eine stille Luecke.
AUSNAHMEN: dict[str, str] = {}


def _faelle_pfad() -> tuple[tuple[Endpunkt, str], ...]:
    """Alle Sonde-2-Faelle: je Endpunkt eine Pfadkennung, die austauschbar ist."""
    return tuple(
        (endpunkt, feld)
        for endpunkt in registrierte_endpunkte()
        for feld in angreifbare_pfadkennungen(endpunkt)
        if f"{endpunkt.name} → {feld}" not in AUSNAHMEN
    )


def _faelle_rumpf() -> tuple[tuple[Endpunkt, str], ...]:
    """Alle Sonde-3-Faelle: je Endpunkt ein kennungstragendes Rumpffeld."""
    return tuple(
        (endpunkt, feld)
        for endpunkt in registrierte_endpunkte()
        for feld in rumpfkennungen(endpunkt)
        if f"{endpunkt.name} → {feld}" not in AUSNAHMEN
    )


def _bezeichner(fall: tuple[Endpunkt, str]) -> str:
    """Lesbarer Fallname fuer ``pytest`` — Endpunkt und ausgetauschtes Feld."""
    endpunkt, feld = fall
    return f"{endpunkt.name} → {feld}"


@pytest.mark.parametrize("fall", _faelle_pfad(), ids=_bezeichner)
async def test_fremde_kennung_im_pfad(
    fall: tuple[Endpunkt, str],
    client: AsyncClient,
    pruefstand: Pruefstand,
    anmelden: AnmeldeHelfer,
):
    """Eigene ``mandant_id``, eine Objektkennung aus Mandant B → 403 oder 404.

    Die uebrigen Kennungen und der Rumpf bleiben eigene. So ist die fremde Kennung der
    einzige Unterschied zur Gegenprobe, und was der Endpunkt daraus macht, ist die
    ganze Aussage des Tests.
    """
    endpunkt, feld = fall
    handelnder = akteur(pruefstand, endpunkt)
    kopf = await anmelden(handelnder, pruefstand.a.welt)

    angriff = await stelle(
        client,
        endpunkt,
        kopf=kopf,
        mandant_id=pruefstand.a.id,
        kennungen=pfadkennungen(endpunkt, pruefstand.a, fremd=pruefstand.b, feld=feld),
        rumpf=baue_rumpf(endpunkt, pruefstand.a),
    )
    sichere_abweisung(
        angriff,
        angriff=f"{endpunkt.name}: eigene mandant_id (A), aber {feld} von Mandant B.",
    )

    gegenprobe = await stelle(
        client,
        endpunkt,
        kopf=kopf,
        mandant_id=pruefstand.a.id,
        kennungen=pfadkennungen(endpunkt, pruefstand.a),
        rumpf=baue_rumpf(endpunkt, pruefstand.a),
    )
    sichere_gegenprobe(
        gegenprobe,
        gegenprobe=f"{endpunkt.name} mit durchweg eigenen Kennungen (Feld {feld})",
    )


@pytest.mark.parametrize("fall", _faelle_rumpf(), ids=_bezeichner)
async def test_fremde_kennung_im_rumpf(
    fall: tuple[Endpunkt, str],
    client: AsyncClient,
    pruefstand: Pruefstand,
    anmelden: AnmeldeHelfer,
):
    """Eigene ``mandant_id``, eigene Pfadkennungen, eine fremde Kennung im Rumpf.

    Die Klasse von M16. Der Angriff sieht von aussen makellos aus: richtige Rolle,
    richtiger Mandant, eigene Objekte im Pfad. Nur das Ziel der Schreibaktion liegt
    woanders — und ob das geprueft wird, entscheidet eine einzelne Zeile im Dienst.
    """
    endpunkt, feld = fall
    handelnder = akteur(pruefstand, endpunkt)
    kopf = await anmelden(handelnder, pruefstand.a.welt)

    angriff = await stelle(
        client,
        endpunkt,
        kopf=kopf,
        mandant_id=pruefstand.a.id,
        kennungen=pfadkennungen(endpunkt, pruefstand.a),
        rumpf=baue_rumpf(endpunkt, pruefstand.a, fremd=pruefstand.b, feld=feld),
    )
    sichere_abweisung(
        angriff,
        angriff=f"{endpunkt.name}: eigener Mandant und eigener Pfad, aber "
        f"'{feld}' im Rumpf zeigt auf Mandant B.",
    )

    gegenprobe = await stelle(
        client,
        endpunkt,
        kopf=kopf,
        mandant_id=pruefstand.a.id,
        kennungen=pfadkennungen(endpunkt, pruefstand.a),
        rumpf=baue_rumpf(endpunkt, pruefstand.a),
    )
    sichere_gegenprobe(
        gegenprobe,
        gegenprobe=f"{endpunkt.name} mit durchweg eigenen Kennungen (Rumpffeld {feld})",
    )


@pytest.mark.parametrize("fall", _faelle_rumpf(), ids=_bezeichner)
async def test_fremde_kennung_im_rumpf_auch_von_b_aus(
    fall: tuple[Endpunkt, str],
    client: AsyncClient,
    pruefstand: Pruefstand,
    anmelden: AnmeldeHelfer,
):
    """Dieselben 14 Faelle in der Gegenrichtung: Mandant B greift auf A.

    Warum nur diese 14 und nicht alle 158 Faelle der einen Richtung: Beide Welten baut
    dieselbe Funktion, ein einseitiges Ergebnis laesst also kaum eine Asymmetrie zu.
    Der Fall, den es doch aufdecken kann, ist ein auf einen bestimmten Mandanten
    festgenagelter Filter — und dafuer genuegt eine Stichprobe. Genommen wird die
    Klasse mit dem hoechsten Risiko: Sonde 3 ist die von M16, und ihre Endpunkte sind
    die schreibenden.

    Stufe 3 hat dieselbe Gegenrichtung fuer die Review-Endpunkte gezogen
    (``test_die_trennung_gilt_auch_von_b_aus``) — aus demselben Grund.
    """
    endpunkt, feld = fall
    handelnder = pruefstand.b.nutzer
    kopf = await anmelden(handelnder, pruefstand.b.welt)

    angriff = await stelle(
        client,
        endpunkt,
        kopf=kopf,
        mandant_id=pruefstand.b.id,
        kennungen=pfadkennungen(endpunkt, pruefstand.b),
        rumpf=baue_rumpf(endpunkt, pruefstand.b, fremd=pruefstand.a, feld=feld),
    )
    sichere_abweisung(
        angriff,
        angriff=f"{endpunkt.name}: Mandant B, aber '{feld}' im Rumpf zeigt auf A.",
    )

    gegenprobe = await stelle(
        client,
        endpunkt,
        kopf=kopf,
        mandant_id=pruefstand.b.id,
        kennungen=pfadkennungen(endpunkt, pruefstand.b),
        rumpf=baue_rumpf(endpunkt, pruefstand.b),
    )
    sichere_gegenprobe(
        gegenprobe,
        gegenprobe=f"{endpunkt.name} mit durchweg eigenen Kennungen von B "
        f"(Rumpffeld {feld})",
    )


async def test_eine_aufteilung_kann_keine_fremde_leistung_nennen(
    client: AsyncClient,
    pruefstand: Pruefstand,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """``POST .../review/{item_id}/adjust`` mit ``splits`` — der Fall, der nicht generisch geht.

    ``kennungsfelder_im_schema`` meldet fuer diesen Endpunkt zwei Kennungsfelder:
    ``service_id`` und ``splits[].service_id``. Sonde 3 erreicht nur das erste, weil
    ``adjust`` sein Verhalten am **Typ des Review-Eintrags** waehlt und der aus der
    ``item_id`` im Pfad kommt: ``service_assignment`` nimmt ``service_id``,
    ``manual_service_assignment`` nimmt ``splits``. Ein Rumpfbauer kann nicht beides
    bedienen, weil ein Eintrag nur einen Typ hat.

    Statt den Fall auf die Ausnahmeliste zu setzen, steht er hier von Hand.

    Geprueft wird ``await self._get_service(service_id, mandant_id)`` in
    ``ServiceManagementService.manually_assign_journal_line_splits`` — die Zeile laeuft
    in einer Schleife ueber **jede** Aufteilung, nicht nur die erste. Die
    Mandantenpruefung selbst reicht ``_get_service`` an den Partner der Leistung
    weiter; deshalb lautet die Antwort ``404 Partner not found`` und nicht
    ``Service not found``.

    Warum zwei Eintraege auf zwei Buchungszeilen
    --------------------------------------------
    Die erste Fassung benutzte **einen** Eintrag fuer Angriff und Gegenprobe. Sie war
    gruen und belegte nichts: ``_adjust_manual_service_assignment_splits`` setzt
    ``item.status = "adjusted"`` und ruft ``flush()`` **bevor** es die Aufteilungen
    pruefen laesst. Im Betrieb verhindert die Ausnahme das ``commit``, und die
    Statusaenderung ist verloren — im Test teilen Anwendung und Test die
    Datenbanksitzung, also sah die Gegenprobe den Eintrag als bereits erledigt und
    antwortete mit ``409 Review item is already adjusted``. Das ist kein 403/404/422
    und ging als Gegenprobe durch, ohne dass der splits-Weg fuer eigene Daten ein
    einziges Mal gelaufen waere.

    Jetzt hat jede Seite ihren eigenen Eintrag auf ihrer eigenen Buchungszeile. Die
    Betraege muessen je Zeile aufgehen (``review_items`` ist auf
    ``(journal_line_id, item_type)`` eindeutig, die Betraege pruefen ``sum == amount``):

    ==================  ===========  ===========================
    Zeile               Betrag       Aufteilung
    ``zeilen[1]``       ``-120,00``  ``-100,00`` + ``-20,00``  → Angriff
    ``zeilen[0]``       ``+500,00``  ``+400,00`` + ``+100,00``  → Gegenprobe
    ==================  ===========  ===========================
    """
    welt = pruefstand.a.welt
    jetzt = utcnow()

    # Zweite Leistung unter demselben Partner — eine Aufteilung braucht mindestens
    # zwei, und `manually_assign_journal_line_splits` verlangt, dass jede zum Partner
    # der Buchungszeile gehoert.
    zweite = Service(
        partner_id=welt.partner.id,
        name="Zweite Leistung",
        service_type=ServiceType.supplier.value,
        tax_rate=Decimal("20.00"),
        created_at=jetzt,
        updated_at=jetzt,
    )
    db_session.add(zweite)

    eintraege = {}
    for schluessel, zeile in (
        ("angriff", welt.zeilen[1]),
        ("gegenprobe", welt.zeilen[0]),
    ):
        eintrag = ReviewItem(
            mandant_id=welt.id,
            item_type="manual_service_assignment",
            journal_line_id=zeile.id,
            context={"partner_name_raw": welt.partner.name},
            status="open",
            created_at=jetzt,
            updated_at=jetzt,
        )
        db_session.add(eintrag)
        eintraege[schluessel] = eintrag
    await db_session.commit()
    await db_session.refresh(zweite)
    for eintrag in eintraege.values():
        await db_session.refresh(eintrag)

    kopf = await anmelden(pruefstand.a.nutzer, welt)

    pfad_angriff = f"/api/v1/mandants/{welt.id}/review/{eintraege['angriff'].id}/adjust"
    angriff = await client.post(
        pfad_angriff,
        headers=kopf,
        json={
            "splits": [
                {"service_id": str(pruefstand.b.welt.leistung.id), "amount": "-100.00"},
                {"service_id": str(zweite.id), "amount": "-20.00"},
            ]
        },
    )
    sichere_abweisung(
        angriff,
        angriff="POST .../review/{item_id}/adjust: die erste der beiden Aufteilungen "
        "nennt eine Leistung aus Mandant B.",
    )

    pfad_gegen = (
        f"/api/v1/mandants/{welt.id}/review/{eintraege['gegenprobe'].id}/adjust"
    )
    gegenprobe = await client.post(
        pfad_gegen,
        headers=kopf,
        json={
            "splits": [
                {"service_id": str(welt.leistung.id), "amount": "400.00"},
                {"service_id": str(zweite.id), "amount": "100.00"},
            ]
        },
    )
    sichere_gegenprobe(
        gegenprobe,
        gegenprobe="derselbe Weg mit zwei eigenen Leistungen, auf einem eigenen "
        "Review-Eintrag",
    )
