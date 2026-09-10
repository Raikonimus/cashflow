"""Befund M10 festgenagelt: Der gewaehlte Mandant ist Anzeigezustand, keine Grenze.

Worum es geht
-------------
Nach dem Anmelden waehlt ein Nutzer mit mehreren Mandanten einen aus (Stufe 1). Die
Wahl landet als ``mandant_id`` im Token. Alle 89 mandantengebundenen Endpunkte nehmen
ihre ``mandant_id`` aber aus dem **Pfad** und vergleichen sie nie mit der im Token.
``require_mandant_access`` prueft die *Mitgliedschaft* — nicht die Uebereinstimmung.

Ein Nutzer mit zwei Mandanten kann also mit einem fuer A gewaehlten Token die Endpunkte
von B ansprechen. Fuer die Berechtigung ist das folgerichtig: Er darf beide sehen.
Es heisst aber, dass die Auswahl nichts **erzwingt**.

Warum das ein Test und keine Behebung ist
-----------------------------------------
Ob die Auswahl eine Grenze sein soll, ist eine Entscheidung und kein Fehler. Beide
Antworten sind vertretbar:

* **So lassen.** Die Auswahl ist Bedienkomfort. Wer zwei Mandanten darf, darf beide —
  und ein Fenster je Mandant im Browser waere sonst unmoeglich, weil das zweite Fenster
  dem ersten den Mandanten wegnimmt.
* **Erzwingen.** Dann muesste jeder Endpunkt Pfad und Token vergleichen. Das schuetzt
  vor dem Bedienfehler, in dem der Nutzer glaubt, in A zu arbeiten, waehrend das
  Frontend B anspricht.

Der Plan fuehrt die Entscheidung als offenen Punkt (Stufe 5). Bis sie fallt, haelt
dieser Test **fest, was heute gilt** — damit niemand die Sicherheit annimmt, die es
nicht gibt, und damit eine kuenftige Umstellung als Testaenderung sichtbar wird und
nicht als stille Verhaltensaenderung.

Die Gegenprobe steht daneben
----------------------------
Dass ``nutzer_beide`` auf B durchkommt, wuerde alleine auch zu einem Endpunkt passen,
der niemanden prueft. Deshalb erhaelt derselbe Aufruf mit ``nutzer_a`` — der zu B
**nicht** gehoert — im selben Test ein 403. Erst der Unterschied zeigt, dass geprueft
wird, und zwar die Mitgliedschaft und nicht die Auswahl.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.auth.security import decode_access_token
from tests.conftest import AnmeldeHelfer
from tests.tenancy.erwartungen import kurz
from tests.tenancy.sonden import Pruefstand

#: Ein Lese-Endpunkt je Modul — mehr braucht die Aussage nicht.
#:
#: M10 ist keine Eigenschaft einzelner Endpunkte, sondern von
#: ``require_mandant_access``: Die Abhaengigkeit haengt an 82 Routen und vergleicht an
#: keiner davon Pfad und Token. Vier Stichproben aus verschiedenen Modulen belegen das
#: hinreichend; alle 89 zu wiederholen wuerde 89-mal dasselbe zeigen.
STICHPROBEN = (
    "partners",
    "review",
    "journal",
    "accounts",
)


@pytest.mark.parametrize("modul", STICHPROBEN)
async def test_ein_token_fuer_a_wirkt_auch_auf_b(
    modul: str,
    client: AsyncClient,
    pruefstand: Pruefstand,
    anmelden: AnmeldeHelfer,
):
    """Token mit ``mandant_id`` von A, Pfad von B — der Aufruf gelingt.

    Das ist das dokumentierte Verhalten, nicht das erwuenschte. Faellt dieser Test
    eines Tages um, weil jemand den Vergleich eingebaut hat, ist das die Umsetzung von
    M10 und der Test gehoert umgeschrieben — bewusst und mit einem Eintrag im Plan.
    """
    kopf = await anmelden(pruefstand.nutzer_beide, pruefstand.a.welt)

    # Das Token nennt tatsaechlich A — sonst wuerde der Test etwas anderes zeigen.
    gewaehlt = decode_access_token(kopf["Authorization"].removeprefix("Bearer "))
    assert gewaehlt["mandant_id"] == str(pruefstand.a.id), (
        f"Das Token nennt {gewaehlt.get('mandant_id')}, erwartet war Mandant A "
        f"({pruefstand.a.id}). Ohne diese Voraussetzung sagt der Test nichts."
    )

    antwort = await client.get(
        f"/api/v1/mandants/{pruefstand.b.id}/{modul}", headers=kopf
    )
    assert antwort.status_code == 200, (
        f"Der Aufruf auf Mandant B scheitert: {kurz(antwort)}.\n"
        f"Wenn das Absicht ist, wurde M10 behoben — dann gehoert dieser Test "
        f"umgeschrieben und docs/mandantenfaehigkeit-plan.md angepasst."
    )

    # Gegenprobe: derselbe Aufruf mit einem Nutzer, der zu B nicht gehoert. Ohne sie
    # koennte das 200 oben auch von einem Endpunkt ohne jede Pruefung kommen.
    kopf_a = await anmelden(pruefstand.a.nutzer, pruefstand.a.welt)
    verweigert = await client.get(
        f"/api/v1/mandants/{pruefstand.b.id}/{modul}", headers=kopf_a
    )
    assert verweigert.status_code == 403, (
        f"Die Gegenprobe scheitert: {kurz(verweigert)}. Erwartet war 403, weil "
        f"{pruefstand.a.nutzer.email} nicht zu Mandant B gehoert. Ohne dieses 403 "
        f"belegt das 200 oben nichts."
    )


async def test_die_auswahl_bleibt_im_token_stehen(
    client: AsyncClient,
    pruefstand: Pruefstand,
    anmelden: AnmeldeHelfer,
):
    """Der Zugriff auf B aendert die Auswahl im Token nicht.

    Die andere Haelfte von M10, und die unangenehmere: Nach einem Aufruf auf B nennt
    das Token weiter A. Wer ``mandant_id`` aus dem Token als „woran ich gerade
    arbeite" liest — das Frontend tut es —, liegt danach falsch, ohne es zu merken.
    Auch das ist heute so und soll festgehalten sein.
    """
    kopf = await anmelden(pruefstand.nutzer_beide, pruefstand.a.welt)

    antwort = await client.get(
        f"/api/v1/mandants/{pruefstand.b.id}/partners", headers=kopf
    )
    assert antwort.status_code == 200, kurz(antwort)

    danach = decode_access_token(kopf["Authorization"].removeprefix("Bearer "))
    assert danach["mandant_id"] == str(pruefstand.a.id), (
        "Das Token hat sich durch den Zugriff auf B geaendert. Das waere eine "
        "Verhaltensaenderung gegenueber M10 und gehoert in den Plan."
    )


async def test_wer_zu_keinem_mandanten_gehoert_kommt_nirgends_hin(
    client: AsyncClient,
    pruefstand: Pruefstand,
    anmelden: AnmeldeHelfer,
):
    """Befund M6 von der anderen Seite: ohne Zuordnung ist jeder Mandant verschlossen.

    ``nutzer_ohne`` ist der Zustand, in dem jeder neu eingeladene Nutzer beginnt. Sein
    Token traegt keine ``mandant_id`` — das ist der Grund, warum Stufe 1 die Sackgasse
    im Frontend sichtbar machen musste. Hier zaehlt die andere Frage: Ein Token ohne
    Auswahl darf nicht versehentlich mehr koennen als eines mit.

    Geprueft werden **beide** Mandanten. Ein Test auf nur einen liesse offen, ob die
    Abweisung an der Zuordnung haengt oder am Zufall.
    """
    kopf = await anmelden(pruefstand.nutzer_ohne, mandant=None, mandant_erwartet=False)

    for seite, bezeichnung in ((pruefstand.a, "A"), (pruefstand.b, "B")):
        antwort = await client.get(
            f"/api/v1/mandants/{seite.id}/partners", headers=kopf
        )
        assert antwort.status_code == 403, (
            f"{pruefstand.nutzer_ohne.email} erreicht Mandant {bezeichnung}, obwohl "
            f"er keinem Mandanten zugeordnet ist: {kurz(antwort)}"
        )
