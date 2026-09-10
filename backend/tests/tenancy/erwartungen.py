"""Was eine Antwort belegt und was nicht — die Zusicherungen der Sonden.

Warum das ein eigenes Modul ist
-------------------------------
Die schwierigste Stelle an einem Angriffstest ist nicht der Angriff, sondern die
Frage, welche Antwort ihn **beweist**. In Stufe 3 hat diese Frage dreimal einen Test
entlarvt, der gruen war und nichts prueft. Die Antworten stehen deshalb hier
gebuendelt, mit dem Grund daneben, statt in 89 Testfaellen einzeln.

Die drei Faelle, in denen ein Test nichts prueft
-----------------------------------------------
1. **Die Gegenprobe verlangt 2xx.** Ein fachliches 409 („Partner existiert bereits")
   belegt gerade, dass die Mandantenpruefung *bestanden* wurde — der Aufruf ist tief
   in der Fachlogik angekommen. Wer 2xx verlangt, verwirft diesen Beleg und macht die
   Gegenprobe unbrauchbar, ohne dass es auffaellt.
2. **Der Datensatz fehlt beim fremden Objekt.** Dann antwortet der Angriff mit 404,
   und die Zusicherung „403 oder 404" ist erfuellt, ohne dass irgendetwas geprueft
   wurde. Gegen diesen Fall hilft nur die Gegenprobe: Wenn derselbe Aufruf auf die
   eigenen Daten *funktioniert*, existiert der Datensatz auch beim fremden.
3. **Die Rolle verweigert, nicht der Mandant.** Ein 403 aus ``require_role`` sieht
   genauso aus wie eines aus ``require_mandant_access``. Deshalb waehlen die Sonden
   ihren Akteur nach der Mindestrolle, die aus der Route selbst gelesen wird — siehe
   ``endpunkte.py``.

Warum 422 in der Gegenprobe verboten ist
----------------------------------------
Ein 422 heisst: Die Anfrage kam nicht bis zur Fachlogik. Kein Rumpf, falscher Typ,
fehlender Pflichtparameter. Ein Angriff, der mit 422 endet, hat die Mandantenpruefung
vielleicht nie erreicht — und ein Endpunkt, dessen Gegenprobe 422 liefert, ist von der
Sonde nur scheinbar bedient. Beides ist ein Mangel der Sonde, kein Befund ueber die
Anwendung, und muss darum als Testfehler sichtbar werden.
"""

from __future__ import annotations

from httpx import Response

#: Antworten, die einen abgewiesenen Zugriff belegen.
#:
#: 403 ist die saubere Antwort. 404 gilt genauso, weil eine Pruefung, die ein fremdes
#: Objekt schlicht nicht findet (``WHERE mandant_id = ...`` im Statement), dieselbe
#: Trennung erreicht — und dabei nicht einmal verraet, dass es das Objekt gibt.
VERWEIGERT = (403, 404)

#: Antworten, aus denen die Gegenprobe nichts folgern kann.
#:
#: 403/404 wuerden bedeuten, dass der Endpunkt auch die eigenen Daten verweigert; 422,
#: dass die Anfrage nie in der Fachlogik ankam. In allen drei Faellen ist die Sonde
#: falsch gebaut und der zugehoerige Angriff wertlos.
BEWEISLOS = (403, 404, 422)


def kurz(antwort: Response, grenze: int = 300) -> str:
    """Die Antwort als knappe Zeile fuer Fehlermeldungen."""
    text = antwort.text.replace("\n", " ")
    if len(text) > grenze:
        text = text[:grenze] + " …"
    return f"{antwort.status_code} {text}"


def sichere_abweisung(antwort: Response, *, angriff: str) -> None:
    """Verlangt, dass der Angriff abgewiesen wurde.

    Ein 2xx ist der Befund: fremde Daten gelesen oder geaendert. Ein 5xx ist ebenfalls
    einer — er heisst, dass die Anwendung an der fremden Kennung zerbricht statt sie
    abzuweisen, und verraet ueber die Fehlermeldung womoeglich mehr, als sie sollte.
    """
    assert antwort.status_code in VERWEIGERT, (
        f"{angriff}\n"
        f"  erwartet: {' oder '.join(str(c) for c in VERWEIGERT)}\n"
        f"  erhalten: {kurz(antwort)}\n"
        f"  Ein 2xx ist ein Mandantenleck. Ein 4xx ausserhalb der Liste oder ein 5xx "
        f"heisst, dass die Anwendung die fremde Kennung nicht abweist, sondern an ihr "
        f"scheitert."
    )


def sichere_gegenprobe(antwort: Response, *, gegenprobe: str) -> None:
    """Verlangt, dass derselbe Aufruf auf die **eigenen** Daten nicht abgewiesen wird.

    Ohne diese Zusicherung beweist der Angriff nichts: Ein Endpunkt, der grundsaetzlich
    403 gibt, oder eine Sonde mit unpassendem Rumpf, waere von der Abweisung nicht zu
    unterscheiden.

    Was hier durchgeht, ist absichtlich weit gefasst — jede Antwort ausser 403, 404,
    422 und 5xx. Der Grund steht im Modulkopf.
    """
    assert antwort.status_code not in BEWEISLOS, (
        f"Die Gegenprobe scheitert, also prueft der Angriff nichts.\n"
        f"  {gegenprobe}\n"
        f"  erhalten: {kurz(antwort)}\n"
        f"  403/404 heisst: der Endpunkt verweigert auch die eigenen Daten. "
        f"422 heisst: die Anfrage kam nicht bis zur Fachlogik — Rumpf, Query oder "
        f"Kennung der Sonde passen nicht. Beides ist ein Mangel der Sonde."
    )
    assert antwort.status_code < 500, (
        f"Die Gegenprobe loest einen Serverfehler aus, also prueft der Angriff "
        f"nichts.\n  {gegenprobe}\n  erhalten: {kurz(antwort)}"
    )


def sichere_rollenschranke(antwort: Response, *, aufruf: str) -> None:
    """Verlangt 403 — hier aus der **Rolle**, nicht aus der Mandantenzugehoerigkeit.

    Gebraucht fuer die fuenf Endpunkte der Mandantenverwaltung: Sie verlangen die Rolle
    ``admin``, und ein Admin umgeht die Mandantenpruefung nach ADR-001 absichtlich. Es
    gibt also keinen Akteur, der rollenmaessig darf und mandantenmaessig beschraenkt
    ist. Was bleibt und was hier zugesichert wird: dass ein gewoehnlicher Nutzer sie
    ueberhaupt nicht erreicht.
    """
    assert antwort.status_code == 403, (
        f"{aufruf}\n"
        f"  erwartet: 403 aus der Rollenpruefung\n"
        f"  erhalten: {kurz(antwort)}"
    )
