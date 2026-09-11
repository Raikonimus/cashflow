"""Die Endpunktliste — **erzeugt** aus den registrierten Routen, nicht abgeschrieben.

Warum dieses Modul existiert
----------------------------
Stufe 3 hat die Mandantentrennung von vier Modulen von Hand geprueft und dabei ein
echtes Leck gefunden (M16). Eine Pruefung von Hand hat aber einen Fehler, den keine
Sorgfalt behebt: Sie deckt genau die Endpunkte ab, an die der Schreibende gedacht hat.
Der 90. Endpunkt, der morgen hinzukommt, faellt still durch.

Deshalb liest dieses Modul die Endpunktliste aus ``app.routes`` — dem Zustand, den die
Anwendung beim Start tatsaechlich aufbaut. Wer einen Endpunkt hinzufuegt, taucht ohne
weiteres Zutun in der Liste auf, und ``test_endpunktliste.py`` schlaegt fehl, solange
niemand sagt, wie er zu pruefen ist.

Warum nicht aus den Dekoratoren
-------------------------------
Die naheliegende Abkuerzung — die Zeichenketten in den ``@router.get(...)``-Dekoratoren
einsammeln — geht schief. Zwei Router tragen die ``mandant_id`` im **Prefix** des
Routers und nicht im Pfad des einzelnen Endpunkts:

* ``review_router``  → ``/mandants/{mandant_id}/review`` (10 Endpunkte)
* ``imports_router`` → ``/mandants/{mandant_id}/accounts/{account_id}/imports`` (3)

Alle uebrigen Router tragen ``/mandants`` als Prefix und die ``{mandant_id}`` im
Dekoratorpfad; sie waren in der Zaehlung sichtbar.

Wer nur die Dekoratoren liest, haelt die dreizehn Endpunkte der beiden fuer
mandantenlos. Genau daher
stammt die Zahl „76 mandantengebundene Endpunkte" aus der Analyse in
``docs/mandantenfaehigkeit-plan.md`` (Befund M1). Die Wahrheit aus den registrierten
Routen ist **89**. Dreizehn Endpunkte waren in der Zaehlung unsichtbar — keiner davon
ungeprueft, aber alle dreizehn ungezaehlt.

Was hier mechanisch ausgelesen wird und warum
---------------------------------------------
Nicht nur Methode und Pfad, sondern auch:

``mindestrolle``
    Aus dem Abschluss (*closure*) von ``require_role`` — die Fabrik in
    ``app/auth/dependencies.py`` haelt ihr Argument ``min_role`` dort fest. Das sieht
    nach einem Kunstgriff aus und ist doch der Kern der Sache: Die Sonden brauchen
    einen Akteur, dessen Rolle **reicht** und dessen Mandantenzuordnung **beschraenkt**
    ist. Stuende die Rolle in einer Tabelle in dieser Datei, waere sie nach der
    naechsten Rollenaenderung falsch, und der Test wuerde ein 403 aus der Rolle fuer
    ein 403 aus der Mandantenpruefung halten — also gruen bleiben, ohne etwas zu
    belegen. Ein 403 ist nur dann eine Aussage ueber die Mandantentrennung, wenn
    ausgeschlossen ist, dass es aus der Rolle kommt.

``mandantenpruefung``
    Ob ``require_mandant_access`` an der Route haengt. Sieben der 89 tragen sie nicht
    (Befund M1); sie pruefen entweder gar nicht (ADR-001: Admin umgeht die
    Mandantenpruefung absichtlich) oder erst im Dienst (die beiden
    Zuordnungsendpunkte aus Stufe 2). Beide Faelle brauchen eine andere Erwartung als
    die uebrigen 82, und diese Unterscheidung darf nicht geraten werden.

``kennungen``
    Die Pfadparameter **ausser** ``mandant_id``, in der Reihenfolge des Pfades. Das
    sind die zweiten Kennungen, um die es in Stufe 4 geht: Die aeussere Schicht prueft
    die ``mandant_id``, die innere muss pruefen, ob das benannte Objekt zu ihr gehoert.
    Dort lagen die Lecks aus Etappe 1 des Code-Reviews.

Warum nur Routen aus ``app.*`` zaehlen
-------------------------------------
``app`` ist ein Modulsingleton, und **Testmodule haengen Routen daran an**:
``tests/auth/test_rbac.py`` registriert beim Import einen ``/api/v1/test-rbac``-Router,
um die Rollenwaechter zu pruefen. Damit haengt der Inhalt von ``app.routes`` davon ab,
welche Testmodule pytest schon eingesammelt hat.

Das ist beim ersten Gesamtlauf aufgefallen: Einzeln lief
``test_die_endpunkte_ohne_mandantenbezug_sind_festgehalten`` gruen, im Gesamtlauf fiel
es ueber die drei Testrouten. Eine Filterung nach dem Pfad (``/test-rbac`` ausnehmen)
waere eine Ausnahme fuer genau diesen einen Fall gewesen; der naechste Testrouter mit
anderem Namen haette wieder angeschlagen.

Deshalb entscheidet das **Herkunftsmodul der Handhabungsfunktion**: Ein Endpunkt der
Anwendung ist einer, dessen Funktion in ``app.`` liegt. Das gilt fuer jeden kuenftigen
Testrouter mit und kommt ohne Namensliste aus.

Dieses Modul kennt die Pruefumgebung nicht
------------------------------------------
Es liest Routen und sonst nichts — keine Fixture, keine Testdaten, keine Erwartungen.
Was mit der Liste geschieht, steht in ``sonden.py`` und in den Testmodulen. Die
Trennung ist Absicht: Die Introspektion laesst sich damit einzeln lesen und einzeln
irren.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from fastapi.routing import APIRoute

from app.auth.dependencies import ROLE_HIERARCHY
from app.main import app

#: Der Praefix, unter dem ``app/main.py`` alle Router einhaengt.
PRAEFIX = "/api/v1"

#: Der Pfadparameter, der einen Endpunkt mandantengebunden macht.
MANDANTENPARAMETER = "mandant_id"

_PLATZHALTER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

#: Herkunft, die eine Route zu einer Route **der Anwendung** macht.
#:
#: Siehe Modulkopf: Testmodule haengen eigene Router an dasselbe ``app``-Objekt.
ANWENDUNGSPAKET = "app."


def _ist_anwendungsroute(route: APIRoute) -> bool:
    """Gehoert diese Route zur Anwendung — oder hat ein Testmodul sie angehaengt?

    Entschieden wird am Modul der Handhabungsfunktion. Eine Route, deren Funktion in
    ``tests.`` liegt, ist Pruefwerkzeug und kein Endpunkt des Systems; sie in die
    Listen aufzunehmen wuerde die Zaehlungen und Ratschen davon abhaengig machen,
    welche Testdateien pytest gerade eingesammelt hat.
    """
    herkunft = getattr(route.endpoint, "__module__", "")
    return herkunft.startswith(ANWENDUNGSPAKET)


def _eingehaengte_routen(
    routen: Iterable[Any], praefix: str = ""
) -> Iterator[tuple[str, APIRoute]]:
    """Jede ``APIRoute`` unterhalb von ``routen`` — mit ihrem vollen Pfad.

    Warum das nicht einfach ``app.routes`` ist
    ------------------------------------------
    Bis FastAPI 0.139 hat ``include_router()`` die Routen des eingehaengten Routers
    **flachgeklopft**: Jede landete einzeln in ``app.routes``, ihr ``path`` trug den
    Praefix bereits. Seit 0.140 steht dort stattdessen ein ``_IncludedRouter``, der
    den urspruenglichen Router unter ``original_router`` haelt und den beim Einhaengen
    gegebenen Praefix in ``include_context.prefix``.

    Aus ``app.routes`` wurden damit 89 Endpunkte zu dreizehn Behaeltern, und eine
    Pruefung auf ``isinstance(route, APIRoute)`` fand **nichts**. Genau das ist am
    2026-09-11 passiert: CI loest die Abhaengigkeiten frei auf und bekam 0.141, die
    Entwicklungsumgebung hatte 0.135 — dieselbe Datei war lokal gruen und in CI rot.

    Diese Funktion steigt deshalb ab und setzt den Pfad selbst zusammen. Sie kommt mit
    beiden Formen zurecht: Liegen die Routen flach, greift der erste Zweig und der
    Praefix bleibt leer; liegen sie verschachtelt, sammelt der zweite ihn ein. Den
    Praefix des Routers selbst (``/auth``, ``/mandants/{mandant_id}/review``) traegt
    der Kindpfad in beiden Faellen schon, weil ``APIRouter`` ihn beim Anlegen der Route
    einsetzt und nicht erst beim Einhaengen.

    ``original_router`` und ``include_context`` sind FastAPI-Interna. Das ist hier
    vertretbar, weil die Alternative — die Endpunktliste von Hand zu fuehren — den
    ganzen Zweck der Datei aufhebt (siehe Modulkopf). Aendern sie sich erneut, faellt
    es sofort auf: ``anwendungsrouten()`` besteht darauf, etwas zu finden.
    """
    for route in routen:
        if isinstance(route, APIRoute):
            yield praefix + route.path, route
            continue
        eingehaengter = getattr(route, "original_router", None)
        if eingehaengter is not None:
            zusatz = (
                getattr(getattr(route, "include_context", None), "prefix", "") or ""
            )
            yield from _eingehaengte_routen(eingehaengter.routes, praefix + zusatz)
            continue
        # Mount und Co. — ``/docs`` und ``/openapi.json`` sind keine APIRoute und
        # fallen hier heraus, wie sie es vorher auch taten.
        unterrouten = getattr(route, "routes", None)
        if unterrouten:
            yield from _eingehaengte_routen(unterrouten, praefix)


def anwendungsrouten() -> tuple[tuple[str, APIRoute], ...]:
    """Die Routen der Anwendung, ohne die von Testmodulen angehaengten.

    Oeffentlich, weil ``sonden.py`` dieselbe Quelle braucht: Dort stand bis zum
    2026-09-11 ein zweiter Lauf ueber ``app.routes``, der beim FastAPI-Umbau
    genauso blind wurde und getrennt repariert werden musste. Zwei Wege zu
    derselben Auskunft sind genau der Zwilling, nach dem der Merge-Check fragt.

    Besteht darauf, etwas zu finden. Eine leere Liste ist kein moeglicher Zustand
    dieser Anwendung, sondern heisst, dass die Introspektion die Routenstruktur nicht
    mehr versteht — und das ist der gefaehrlichste Fehlschlag, den diese Datei haben
    kann: Alle Sonden werden ueber die Endpunkte parametrisiert, und eine leere
    Parametrisierung laesst **jede** Pruefung der Stufe 4 lautlos verschwinden. In CI
    blieben am 2026-09-11 sechs der dreizehn Buchhaltungstests gruen, weil „fuer jeden
    Endpunkt gilt ..." auf der leeren Menge wahr ist.

    Deshalb hier ein Abbruch mit Namen statt einer leeren Rueckgabe.
    """
    gefunden = tuple(
        (pfad, route)
        for pfad, route in _eingehaengte_routen(app.routes)
        if _ist_anwendungsroute(route)
    )
    if not gefunden:
        raise RuntimeError(
            "Keine einzige Anwendungsroute in app.routes gefunden. Die Introspektion "
            "versteht die Routenstruktur nicht mehr — vermutlich hat FastAPI die Form "
            "von include_router() erneut geaendert. Siehe _eingehaengte_routen(). "
            f"Gefundene Klassen: {sorted({type(r).__name__ for r in app.routes})}"
        )
    return gefunden


@dataclass(frozen=True)
class Endpunkt:
    """Ein registrierter Endpunkt mit allem, was die Sonden ueber ihn wissen muessen.

    ``pfad`` ist die Routenschablone einschliesslich Praefix und Platzhaltern, also
    ``/api/v1/mandants/{mandant_id}/partners/{partner_id}``. Die Sonden setzen die
    Platzhalter mit ``str.format`` ein; deshalb ist die Schablone und nicht der fertige
    Pfad das, was hier steht.
    """

    methode: str
    pfad: str
    #: Pfadparameter ausser ``mandant_id``, in der Reihenfolge des Pfades.
    kennungen: tuple[str, ...]
    #: Query-Parameter ohne Vorgabewert — ohne sie antwortet der Endpunkt mit 422.
    pflicht_query: tuple[str, ...]
    #: ``"json"``, ``"multipart"`` oder ``None`` (kein Rumpf).
    rumpfart: str | None
    #: Haengt ``require_mandant_access`` an dieser Route?
    mandantenpruefung: bool
    #: Rolle, die ``require_role`` verlangt.
    mindestrolle: str

    @property
    def name(self) -> str:
        """Bezeichner fuer Ausnahmelisten, Testnamen und Fehlermeldungen."""
        return f"{self.methode} {self.pfad}"

    def __str__(self) -> str:
        """Derselbe Bezeichner — damit ``pytest`` lesbare Fallnamen zeigt."""
        return self.name


def _mindestrolle(dependant: Any) -> str:
    """Liest die von ``require_role`` verlangte Rolle aus dem Abhaengigkeitsbaum.

    ``require_role`` ist eine Fabrik: Sie gibt eine Funktion namens ``dependency``
    zurueck, die ``min_role`` in ihrem Abschluss haelt. Genau dort wird sie hier
    geholt.

    Bei mehreren Rollen an einer Route gilt die **strengste** — so wirkt es auch zur
    Laufzeit, weil jede einzelne Pruefung bestehen muss.

    Wirft ``AssertionError``, wenn keine Rolle zu finden ist. Ein stiller Vorgabewert
    waere hier gefaehrlich: Er wuerde einen Endpunkt ohne Rollenpruefung wie einen mit
    behandeln, und die Sonde wuerde mit dem falschen Akteur laufen.
    """
    gefunden: list[str] = []

    def sammle(knoten: Any) -> None:
        """Steigt in den Abhaengigkeitsbaum ab und merkt jede gefundene Rolle."""
        for unter in knoten.dependencies:
            aufruf = unter.call
            if aufruf is not None and getattr(aufruf, "__name__", "") == "dependency":
                freie = getattr(getattr(aufruf, "__code__", None), "co_freevars", ())
                zellen = getattr(aufruf, "__closure__", None)
                if "min_role" in freie and zellen:
                    gefunden.append(zellen[freie.index("min_role")].cell_contents)
            sammle(unter)

    sammle(dependant)
    assert gefunden, (
        "Keine Rolle im Abhaengigkeitsbaum gefunden. Entweder hat der Endpunkt keine "
        "Rollenpruefung — dann ist das der Befund — oder require_role wurde umgebaut "
        "und diese Introspektion muss nachziehen."
    )
    return max(gefunden, key=lambda rolle: ROLE_HIERARCHY.get(rolle, 0))


def _hat_mandantenpruefung(dependant: Any) -> bool:
    """Prueft, ob ``require_mandant_access`` an der Route haengt.

    Nur die oberste Ebene wird betrachtet: So haengen die Router sie ein, und eine
    Mandantenpruefung, die in einer Unterabhaengigkeit versteckt waere, sollte man
    ohnehin nicht so nennen.
    """
    return any(
        getattr(unter.call, "__name__", "") == "require_mandant_access"
        for unter in dependant.dependencies
    )


def _rumpfart(route: APIRoute) -> str | None:
    """``"multipart"`` bei Dateiannahme, ``"json"`` bei einem Modell, sonst ``None``.

    Die Unterscheidung braucht die Sonde, weil ein Dateiendpunkt mit ``json=`` nicht
    bedient werden kann — er antwortete mit 422, und das Ergebnis waere wertlos.
    """
    if route.body_field is None:
        return None
    art = getattr(route.body_field.field_info, "media_type", None)
    if art == "multipart/form-data":
        return "multipart"
    return "json"


def registrierte_endpunkte() -> tuple[Endpunkt, ...]:
    """Alle mandantengebundenen Endpunkte der laufenden Anwendung.

    Mandantengebunden heisst: ``{mandant_id}`` steht in der Routenschablone — egal ob
    aus dem Dekorator oder aus dem Prefix des Routers. Eine Route mit mehreren Methoden
    ergibt mehrere Endpunkte, weil ``GET`` und ``DELETE`` desselben Pfades verschiedene
    Dinge tun und getrennt zu pruefen sind.

    Die Reihenfolge ist nach Pfad und Methode sortiert, damit die Testfallnamen stabil
    bleiben und ein Lauf mit ``-k`` reproduzierbar ist.
    """
    endpunkte: list[Endpunkt] = []
    for pfad, route in anwendungsrouten():
        platzhalter = _PLATZHALTER.findall(pfad)
        if MANDANTENPARAMETER not in platzhalter:
            continue
        kennungen = tuple(p for p in platzhalter if p != MANDANTENPARAMETER)
        pflicht_query = tuple(
            sorted(
                p.name
                for p in route.dependant.query_params
                if p.field_info.is_required()
            )
        )
        for methode in sorted(route.methods - {"HEAD", "OPTIONS"}):
            endpunkte.append(
                Endpunkt(
                    methode=methode,
                    pfad=pfad,
                    kennungen=kennungen,
                    pflicht_query=pflicht_query,
                    rumpfart=_rumpfart(route),
                    mandantenpruefung=_hat_mandantenpruefung(route.dependant),
                    mindestrolle=_mindestrolle(route.dependant),
                )
            )
    return tuple(sorted(endpunkte, key=lambda e: (e.pfad, e.methode)))


def alle_endpunkte() -> tuple[Endpunkt, ...]:
    """Alle registrierten Endpunkte, auch die ohne Mandantenbezug.

    Gebraucht von ``test_endpunktliste.py``, um die Gesamtzahl gegen die
    mandantengebundene Teilmenge zu stellen: Waechst die eine und die andere nicht,
    ist ein neuer Endpunkt entweder bewusst mandantenlos oder es fehlt ihm die
    Bindung. Beides soll auffallen.
    """
    endpunkte: list[Endpunkt] = []
    for pfad, route in anwendungsrouten():
        platzhalter = _PLATZHALTER.findall(pfad)
        for methode in sorted(route.methods - {"HEAD", "OPTIONS"}):
            endpunkte.append(
                Endpunkt(
                    methode=methode,
                    pfad=pfad,
                    kennungen=tuple(p for p in platzhalter if p != MANDANTENPARAMETER),
                    pflicht_query=(),
                    rumpfart=_rumpfart(route),
                    mandantenpruefung=_hat_mandantenpruefung(route.dependant),
                    mindestrolle="",
                )
            )
    return tuple(sorted(endpunkte, key=lambda e: (e.pfad, e.methode)))
