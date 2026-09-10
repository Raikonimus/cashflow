"""Die Auswahl ist eine Grenze — Befund M10, entschieden und umgesetzt.

Was sich geaendert hat
----------------------
Bis Stufe 5 war der gewaehlte Mandant **Anzeigezustand**: Alle mandantengebundenen
Endpunkte nehmen ihre ``mandant_id`` aus dem Pfad, und ``require_mandant_access``
pruefte nur die *Mitgliedschaft*, nie die Uebereinstimmung mit dem Token. Ein Nutzer mit
zwei Mandanten konnte mit einem fuer A gewaehlten Token die Endpunkte von B ansprechen.
Fuer die Berechtigung war das folgerichtig — er darf beide —, es hiess aber, dass die
Auswahl nichts erzwingt.

Die Entscheidung fiel in Stufe 5 auf **erzwingen** (ADR-019). ``require_mandant_access``
vergleicht jetzt zuerst Token und Pfad und erst danach die Mitgliedschaft. Dieses Modul
hielt vorher das alte Verhalten fest und haelt jetzt das neue; die vorige Fassung steht
in der Versionsgeschichte.

Warum die Umstellung fuer das Frontend unsichtbar ist
-----------------------------------------------------
Der Zustandsspeicher leitet den gewaehlten Mandanten **aus dem Token** ab
(``sanitizeAuthState`` in ``src/store/auth-store.ts``:
``mandants.find(m => m.id === user.mandant_id)``). Auswahl und Token koennen deshalb
nicht auseinanderlaufen, und das Frontend schickt nie ein Paar, das der neue Vergleich
abweisen wuerde. Belegt hat das auch die Umstellung selbst: Von 310 Tests fielen genau
die sechs, die das alte Verhalten beschrieben — kein einziger fachlicher.

Was es kostet
-------------
Ein Token **ohne** ``mandant_id`` erreicht keinen dieser Endpunkte mehr. Das trifft zwei
Zustaende: mehrere Mandanten und noch keine Auswahl, oder gar keine Zuordnung (M6). In
beiden gibt es auch nichts anzuzeigen. Fuer den Admin heisst es einen Zwischenschritt
mehr — er muss den Mandanten benennen, erreicht aber weiter jeden.
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
#: Der Vergleich sitzt in ``require_mandant_access`` und haengt an 82 Routen. Vier
#: Stichproben aus verschiedenen Modulen belegen das hinreichend; alle 89 zu wiederholen
#: wuerde 89-mal dasselbe zeigen. Die Vollstaendigkeit sichert Sonde 1 ab.
STICHPROBEN = (
    "partners",
    "review",
    "journal",
    "accounts",
)


@pytest.mark.parametrize("modul", STICHPROBEN)
async def test_ein_token_fuer_a_wirkt_nicht_auf_b(
    modul: str,
    client: AsyncClient,
    pruefstand: Pruefstand,
    anmelden: AnmeldeHelfer,
):
    """Token mit ``mandant_id`` von A, Pfad von B — abgewiesen, obwohl erlaubt.

    ``nutzer_beide`` gehoert **beiden** Mandanten. Die Abweisung kommt also nicht aus
    der Berechtigung, sondern allein aus der Auswahl. Genau das ist die Aussage: Die
    Auswahl ist eine Grenze, keine Anzeige.

    Die Gegenprobe steht daneben und ist hier unentbehrlich: Ohne sie waere das 403
    nicht von einer fehlenden Berechtigung zu unterscheiden — und der Test wuerde auch
    dann bestehen, wenn ``nutzer_beide`` seine Zuordnung zu B verloren haette.
    """
    kopf = await anmelden(pruefstand.nutzer_beide, pruefstand.a.welt)

    gewaehlt = decode_access_token(kopf["Authorization"].removeprefix("Bearer "))
    assert gewaehlt["mandant_id"] == str(pruefstand.a.id), (
        f"Das Token nennt {gewaehlt.get('mandant_id')}, erwartet war Mandant A "
        f"({pruefstand.a.id}). Ohne diese Voraussetzung sagt der Test nichts."
    )

    abgewiesen = await client.get(
        f"/api/v1/mandants/{pruefstand.b.id}/{modul}", headers=kopf
    )
    assert abgewiesen.status_code == 403, (
        f"Der Aufruf auf Mandant B gelingt mit einem Token fuer A: "
        f"{kurz(abgewiesen)}.\n"
        f"Wenn das Absicht ist, wurde ADR-019 zurueckgenommen — dann gehoert dieser "
        f"Test umgeschrieben und der Plan angepasst."
    )

    # Gegenprobe: derselbe Nutzer, derselbe Endpunkt, aber B gewaehlt. Belegt, dass die
    # Berechtigung besteht und wirklich nur die Auswahl im Weg stand.
    kopf_b = await anmelden(pruefstand.nutzer_beide, pruefstand.b.welt)
    erlaubt = await client.get(
        f"/api/v1/mandants/{pruefstand.b.id}/{modul}", headers=kopf_b
    )
    assert erlaubt.status_code == 200, (
        f"Mit gewaehltem Mandant B scheitert derselbe Aufruf ebenfalls: "
        f"{kurz(erlaubt)}. Dann belegt das 403 oben nichts ueber die Auswahl, sondern "
        f"nur, dass {pruefstand.nutzer_beide.email} zu B gar nicht gehoert."
    )


async def test_ein_token_ohne_auswahl_erreicht_nichts(
    client: AsyncClient,
    pruefstand: Pruefstand,
    anmelden: AnmeldeHelfer,
):
    """Wer sich angemeldet, aber nicht gewaehlt hat, erreicht keinen Endpunkt.

    Der Preis der Entscheidung, und deshalb ausdruecklich festgehalten.
    ``nutzer_beide`` hat zwei Mandanten, ``login`` waehlt deshalb keinen aus (M2), und
    das Token traegt keine ``mandant_id``. Vorher wirkte so ein Token auf **jeden**
    Mandanten, dem der Nutzer zugeordnet war — die Auswahl war ja bloss Anzeige.

    Geprueft werden beide Mandanten, damit nicht offenbleibt, ob die Abweisung an der
    fehlenden Auswahl oder an einem der beiden Mandanten haengt.
    """
    kopf = await anmelden(pruefstand.nutzer_beide, mandant=None, mandant_erwartet=False)
    ohne_auswahl = decode_access_token(kopf["Authorization"].removeprefix("Bearer "))
    assert ohne_auswahl.get("mandant_id") is None, (
        "Das Token traegt eine mandant_id, obwohl nichts gewaehlt wurde — dann prueft "
        "der Test etwas anderes als er soll."
    )

    for seite, bezeichnung in ((pruefstand.a, "A"), (pruefstand.b, "B")):
        antwort = await client.get(
            f"/api/v1/mandants/{seite.id}/partners", headers=kopf
        )
        assert (
            antwort.status_code == 403
        ), f"Ein Token ohne Auswahl erreicht Mandant {bezeichnung}: {kurz(antwort)}"


async def test_die_abweisung_aendert_die_auswahl_nicht(
    client: AsyncClient,
    pruefstand: Pruefstand,
    anmelden: AnmeldeHelfer,
):
    """Ein abgewiesener Aufruf auf B laesst das Token bei A.

    Klingt selbstverstaendlich und ist es nicht: Ein Vergleich, der bei Abweichung
    „hilfsbereit" den Mandanten im Token nachzieht, waere schlimmer als keiner — er
    machte die Grenze zu einer Umschaltung, und der Nutzer arbeitete danach woanders,
    als die Oberflaeche anzeigt.
    """
    kopf = await anmelden(pruefstand.nutzer_beide, pruefstand.a.welt)

    antwort = await client.get(
        f"/api/v1/mandants/{pruefstand.b.id}/partners", headers=kopf
    )
    assert antwort.status_code == 403, kurz(antwort)

    danach = decode_access_token(kopf["Authorization"].removeprefix("Bearer "))
    assert danach["mandant_id"] == str(
        pruefstand.a.id
    ), "Das Token hat sich durch den abgewiesenen Zugriff auf B geaendert."


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

    Seit ADR-019 greift bei ihm schon die Auswahl-Schranke, vorher erst die
    Zugehoerigkeit. Das Ergebnis ist dasselbe, und das ist der Punkt.
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
