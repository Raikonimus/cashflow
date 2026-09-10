"""Sonde 1 — die aeussere Schicht: eine fremde ``mandant_id`` muss 403 ergeben.

Was hier geprueft wird
----------------------
Ein Nutzer, der zu Mandant A gehoert und zu B **nicht**, stellt eine vollstaendig
gueltige Anfrage an Mandant B: dessen ``mandant_id`` im Pfad, dessen Objektkennungen,
ein Rumpf aus dessen Daten. Es gibt also keinen anderen Grund zu scheitern als die
fehlende Zugehoerigkeit. Antwort muss 403 sein.

Das ist die Schicht, die Befund M1 fuer vollstaendig erklaert hat — auf Grundlage einer
Zaehlung ueber die Dekoratoren. Diese Zaehlung fand 76 Endpunkte. Aus den registrierten
Routen sind es **89**: Zwei Router (``review``, ``imports``) tragen die ``mandant_id``
im Prefix und waren in der Zaehlung unsichtbar. Hier laeuft die Pruefung deshalb ueber alles, was die Anwendung
tatsaechlich anbietet.

Warum der Akteur nicht frei gewaehlt ist
---------------------------------------
Ein 403 aus ``require_role`` sieht aus wie eines aus ``require_mandant_access``. Wer
mit einem ``viewer`` gegen einen Endpunkt sondiert, der ``accountant`` verlangt, erhaelt
403 und hat nichts gezeigt. Der Akteur kommt deshalb aus ``sonden.akteur()``, das die
Mindestrolle aus der Route selbst liest.

Warum die Gegenprobe im selben Test steht
-----------------------------------------
Ohne sie belegt das 403 nichts: Ein Endpunkt, der grundsaetzlich verweigert, waere von
einem, der richtig trennt, nicht zu unterscheiden. Derselbe Aufruf gegen Mandant A muss
darum **nicht** an der Mandantenpruefung scheitern.

Die Gegenprobe laeuft nach dem Angriff. Der Angriff soll nichts veraendern, die
Gegenprobe darf es — legte man sie zuerst, koennte sie dem Angriff seine Grundlage
wegnehmen (etwa indem sie die Gruppe loescht, deren fremdes Gegenstueck der Angriff
sucht).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import AnmeldeHelfer
from tests.tenancy.endpunkte import Endpunkt, registrierte_endpunkte
from tests.tenancy.erwartungen import (
    kurz,
    sichere_gegenprobe,
    sichere_rollenschranke,
)
from tests.tenancy.sonden import (
    Pruefstand,
    akteur,
    baue_rumpf,
    pfadkennungen,
    stelle,
)

#: Endpunkte, fuer die es keinen mandantenbeschraenkten Akteur gibt — mit Begruendung.
#:
#: Diese Liste ist eine Ratsche wie ``--max-offen`` in ``check_tenancy.py``: Sie darf
#: kuerzer werden, nie laenger. ``test_endpunktliste.py`` haelt ihre Laenge fest und
#: prueft, dass jeder Eintrag noch einer registrierten Route entspricht.
#:
#: **Zur Bezeichnung „ADR-001".** So nennt der Code die Admin-Ausnahme
#: (``app/auth/dependencies.py``: „Admin bypasses this check (ADR-001 / RBAC
#: design)"), und dieselbe Bezeichnung benutzt der Plan. Sie geht ins Leere: ADR-001
#: ist die Entscheidung *Client-only Logout ohne Token-Blacklisting*. Zur
#: Admin-Ausnahme gibt es keinen Entscheidungssatz; ihr einziger schriftlicher Beleg
#: ist eine Klammer im Schema von ``requirements.md`` (Zeile 45): „mandant_users —
#: Zuweisung User <-> Mandant (ausser Admin)". Das Verhalten ist also gewollt und
#: belegt, aber nicht als Entscheidung festgehalten — Befund M17 in
#: ``docs/code-review-befunde.md``. Der Name bleibt hier stehen, weil er im Code steht
#: und auffindbar sein soll.
AUSNAHMEN: dict[str, str] = {
    "GET /api/v1/mandants/{mandant_id}": (
        "Verlangt die Rolle admin, und ein Admin umgeht die Mandantenpruefung nach "
        "ADR-001 absichtlich. Es gibt keinen Akteur, dessen Rolle reicht und dessen "
        "Mandantenzuordnung beschraenkt ist. Was pruefbar bleibt, prueft "
        "test_rollenschranke_statt_mandantenpruefung."
    ),
    "PATCH /api/v1/mandants/{mandant_id}": (
        "Wie GET /mandants/{mandant_id} — Rolle admin, ADR-001."
    ),
    "GET /api/v1/mandants/{mandant_id}/cleanup-preview": (
        "Wie GET /mandants/{mandant_id} — Rolle admin, ADR-001."
    ),
    "POST /api/v1/mandants/{mandant_id}/cleanup": (
        "Wie GET /mandants/{mandant_id} — Rolle admin, ADR-001. Zusaetzlich der "
        "schaerfste Endpunkt des Systems: Er loescht einen Mandanten samt Daten. Eine "
        "Gegenprobe, die ihn auf Mandant A ausfuehrt, wuerde die Pruefumgebung im "
        "selben Test zerlegen."
    ),
    "POST /api/v1/mandants/{mandant_id}/deactivate": (
        "Wie GET /mandants/{mandant_id} — Rolle admin, ADR-001. Die Gegenprobe wuerde "
        "Mandant A abschalten und damit jede weitere Zusicherung im Test entwerten."
    ),
}

#: Alle mandantengebundenen Endpunkte ausser den begruendeten Ausnahmen.
SONDIERT: tuple[Endpunkt, ...] = tuple(
    e for e in registrierte_endpunkte() if e.name not in AUSNAHMEN
)


@pytest.mark.parametrize("endpunkt", SONDIERT, ids=str)
async def test_fremder_mandant_wird_abgewiesen(
    endpunkt: Endpunkt,
    client: AsyncClient,
    pruefstand: Pruefstand,
    anmelden: AnmeldeHelfer,
):
    """Gueltige Anfrage an Mandant B mit einem Token fuer Mandant A → 403.

    Der Angriff nennt durchweg Daten von B: die ``mandant_id``, alle Pfadkennungen und
    den Rumpf. Damit ist die fehlende Zugehoerigkeit der einzige moegliche Grund fuer
    eine Abweisung — und ein 403 ist eine Aussage ueber die Mandantentrennung und nicht
    ueber einen falsch gebauten Aufruf.
    """
    handelnder = akteur(pruefstand, endpunkt)
    kopf = await anmelden(handelnder, pruefstand.a.welt)

    angriff = await stelle(
        client,
        endpunkt,
        kopf=kopf,
        mandant_id=pruefstand.b.id,
        kennungen=pfadkennungen(endpunkt, pruefstand.b),
        rumpf=baue_rumpf(endpunkt, pruefstand.b),
    )

    assert angriff.status_code == 403, (
        f"{endpunkt.name} laesst einen Nutzer von Mandant A auf Mandant B zugreifen.\n"
        f"  Akteur:   {handelnder.email} (Rolle {handelnder.role}, nur Mandant A)\n"
        f"  Angriff:  {endpunkt.methode} auf mandant_id von B, Kennungen von B\n"
        f"  erwartet: 403\n"
        f"  erhalten: {kurz(angriff)}"
    )

    # Gegenprobe: derselbe Aufruf auf die eigenen Daten. Ohne sie koennte das 403 oben
    # auch von einem Endpunkt kommen, der grundsaetzlich verweigert.
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
        gegenprobe=f"{endpunkt.name} auf den eigenen Mandanten A, Akteur "
        f"{handelnder.email}",
    )


@pytest.mark.parametrize("endpunkt", tuple(AUSNAHMEN), ids=str)
async def test_rollenschranke_statt_mandantenpruefung(
    endpunkt: str,
    client: AsyncClient,
    pruefstand: Pruefstand,
    anmelden: AnmeldeHelfer,
):
    """Die fuenf Admin-Endpunkte sind fuer gewoehnliche Nutzer gar nicht erreichbar.

    Fuer sie gibt es keine Sonde 1, weil ein Admin die Mandantenpruefung nach ADR-001
    umgeht. Was sich pruefen laesst, ist die Schranke davor: Ein ``accountant`` mit
    gueltigem Token fuer seinen **eigenen** Mandanten kommt nicht durch. Damit ist der
    Endpunkt fuer jeden ausser Admins verschlossen, und ADR-001 traegt die restliche
    Verantwortung ausdruecklich.

    Geprueft wird bewusst auf dem **eigenen** Mandanten. Auf einem fremden waere das
    403 doppelt begruendet und die Aussage schwaecher.
    """
    passende = {e.name: e for e in registrierte_endpunkte()}
    ziel = passende[endpunkt]
    kopf = await anmelden(pruefstand.a.nutzer, pruefstand.a.welt)

    antwort = await stelle(
        client,
        ziel,
        kopf=kopf,
        mandant_id=pruefstand.a.id,
        kennungen=pfadkennungen(ziel, pruefstand.a),
        rumpf=baue_rumpf(ziel, pruefstand.a),
    )
    sichere_rollenschranke(
        antwort,
        aufruf=f"{ziel.name} mit einem accountant auf dem eigenen Mandanten",
    )


async def test_der_admin_erreicht_jeden_mandanten(
    client: AsyncClient,
    pruefstand: Pruefstand,
    anmelden: AnmeldeHelfer,
):
    """ADR-001 festgenagelt: Ein Admin ohne jede Zuordnung liest jeden Mandanten.

    Das ist kein Leck, sondern eine Entscheidung — aber eine, die niemand versehentlich
    zuruecknehmen und niemand versehentlich ausweiten sollte. Der Test haelt sie fest,
    damit die fuenf Ausnahmen oben nicht als Luecke gelesen werden, sondern als das,
    was sie sind.

    ``admin`` hat in der Pruefumgebung **keine** Zeile in ``mandant_users``. Dass er
    trotzdem durchkommt, liegt allein am Zweig in ``require_mandant_access``.
    """
    kopf = await anmelden(pruefstand.admin, pruefstand.a.welt)

    for seite, bezeichnung in ((pruefstand.a, "A"), (pruefstand.b, "B")):
        antwort = await client.get(
            f"/api/v1/mandants/{seite.id}/partners", headers=kopf
        )
        assert antwort.status_code == 200, (
            f"Der Admin erreicht Mandant {bezeichnung} nicht: {kurz(antwort)}. "
            f"Wenn das Absicht ist, widerspricht es ADR-001 und der Plan gehoert "
            f"angepasst."
        )

    # Das Token nennt Mandant A — trotzdem antwortet B. Genau das ist Befund M10, hier
    # fuer den Admin: Die Auswahl ist Anzeigezustand, keine Grenze.
    assert True
