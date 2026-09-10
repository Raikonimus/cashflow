"""Die Liste selbst ist der Gegenstand — damit kein Endpunkt still durchfaellt.

Warum es diese Tests gibt
-------------------------
Die Sonden in ``test_aeussere_schicht.py`` und ``test_innere_schicht.py`` pruefen die
Anwendung. Dieses Modul prueft die **Sonden**: ob sie jeden Endpunkt erreichen, ob jede
Ausnahme begruendet und noch aktuell ist, ob jede Kennung eine Quelle hat.

Der Grund ist der Fehler, den Stufe 4 vermeiden soll. Eine Pruefung von Hand deckt
genau die Endpunkte ab, an die der Schreibende gedacht hat. Fuegt jemand morgen einen
Endpunkt hinzu, waechst die Liste aus ``registrierte_endpunkte()`` automatisch mit —
aber nur die Tests hier bemerken, wenn er unsondiert bleibt, weil ihm ein Rumpf oder
eine Kennungsquelle fehlt. Ohne sie waere der neue Endpunkt einfach ein Testfall
weniger, und niemand saehe es.

Die Ratschen
------------
Drei Zahlen sind hier festgenagelt: die Zahl der Endpunkte ohne Mandantenbezug, die
Zahl der Endpunkte ohne ``require_mandant_access`` und die Laenge der beiden
Ausnahmelisten. Alle vier duerfen **kleiner** werden, nie groesser — dasselbe Prinzip
wie ``--max-offen`` bei ``check_tenancy.py``. Wer eine Zahl anhebt, tut es sichtbar und
mit Begruendung im Diff.
"""

from __future__ import annotations

from tests.tenancy import test_aeussere_schicht as aeussere
from tests.tenancy import test_innere_schicht as innere
from tests.tenancy.endpunkte import (
    MANDANTENPARAMETER,
    alle_endpunkte,
    registrierte_endpunkte,
)
from tests.tenancy.sonden import (
    OHNE_MANDANTENBINDUNG,
    QUELLEN,
    QUERYWERTE,
    RUMPF,
    SONDERQUELLEN,
    angreifbare_pfadkennungen,
    kennungsfelder_im_schema,
    quelle,
    rumpfkennungen,
)

#: Endpunkte ohne ``{mandant_id}`` im Pfad — jeder mit dem Grund, warum das richtig ist.
#:
#: Die gefaehrlichste Luecke, die Stufe 4 haben koennte: ein Endpunkt, der
#: mandantenbezogene Daten liefert, seinen Mandanten aber aus dem Token oder dem Rumpf
#: nimmt. Er stuende in keiner der Sondenlisten, weil er ``{mandant_id}`` nicht im Pfad
#: traegt — und faellt still durch. Deshalb ist auch diese Liste festgehalten: Ein neuer
#: mandantenloser Endpunkt muss hier eingetragen und damit begruendet werden.
OHNE_MANDANTENBEZUG: dict[str, str] = {
    "POST /api/v1/auth/login": "Vor der Anmeldung gibt es keinen Mandanten.",
    "POST /api/v1/auth/logout": "Beendet die Sitzung, beruehrt keine Mandantendaten.",
    "GET /api/v1/auth/me": "Gibt den eigenen Nutzer samt seiner Mandanten heraus.",
    "POST /api/v1/auth/select-mandant": (
        "Waehlt den Mandanten — bekommt ihn im Rumpf und prueft die Zuordnung selbst. "
        "Geprueft in tests/auth/test_mandantenauswahl.py (Stufe 1)."
    ),
    "POST /api/v1/auth/forgot-password": "Kennwort vergessen, ohne Anmeldung.",
    "POST /api/v1/auth/reset-password": "Kennwort neu setzen, ohne Anmeldung.",
    "POST /api/v1/auth/accept-invitation": "Einladung annehmen, ohne Anmeldung.",
    "GET /api/v1/mandants": (
        "Listet die Mandanten des Nutzers — die Liste ist selbst das Ergebnis der "
        "Zuordnung und kann keinen Mandanten im Pfad haben."
    ),
    "POST /api/v1/mandants": "Legt einen Mandanten an; Rolle admin.",
    "GET /api/v1/users": (
        "Nutzerverwaltung. Nutzer sind global, nicht mandantengebunden; die Sichtbarkeit "
        "richtet sich nach der Rolle. Geprueft in tests/auth/ (Stufe 2)."
    ),
    "POST /api/v1/users": "Nutzerverwaltung — siehe GET /users.",
    "GET /api/v1/users/assignable-mandants": (
        "Liefert die Mandanten, die der Handelnde zuordnen darf. Aus Stufe 2, "
        "Entscheidung E2; geprueft in tests/auth/test_mandantenzuordnung.py."
    ),
    "GET /api/v1/users/{user_id}": "Nutzerverwaltung — siehe GET /users.",
    "PATCH /api/v1/users/{user_id}": "Nutzerverwaltung — siehe GET /users.",
    "DELETE /api/v1/users/{user_id}": "Nutzerverwaltung — siehe GET /users.",
    "POST /api/v1/users/{user_id}/resend-invitation": (
        "Nutzerverwaltung — siehe GET /users."
    ),
}

#: Mandantengebundene Endpunkte **ohne** ``require_mandant_access`` — Befund M1.
#:
#: Sieben, und keiner davon ungeprueft: Fuenf verlangen ``admin`` und umgehen die
#: Mandantenpruefung nach ADR-001 absichtlich; zwei pruefen erst im Dienst, weil die
#: Regel dort komplizierter ist als Zugehoerigkeit (Entscheidung E2 aus Stufe 2).
OHNE_ZUGANGSPRUEFUNG: dict[str, str] = {
    "GET /api/v1/mandants/{mandant_id}": "Rolle admin, ADR-001.",
    "PATCH /api/v1/mandants/{mandant_id}": "Rolle admin, ADR-001.",
    "GET /api/v1/mandants/{mandant_id}/cleanup-preview": "Rolle admin, ADR-001.",
    "POST /api/v1/mandants/{mandant_id}/cleanup": "Rolle admin, ADR-001.",
    "POST /api/v1/mandants/{mandant_id}/deactivate": "Rolle admin, ADR-001.",
    "POST /api/v1/mandants/{mandant_id}/users": (
        "Rolle mandant_admin. Die Pruefung sitzt im Dienst "
        "(MandantAssignmentService._require_mandant_assignable), weil ein "
        "Mandant-Admin nur seine eigenen Mandanten zuordnen darf — Entscheidung E2. "
        "Geprueft in tests/auth/test_mandantenzuordnung.py."
    ),
    "DELETE /api/v1/mandants/{mandant_id}/users/{user_id}": (
        "Wie POST /mandants/{mandant_id}/users — Pruefung im Dienst, Entscheidung E2."
    ),
}


def test_jeder_mandantengebundene_endpunkt_ist_erfasst():
    """Jeder Endpunkt mit ``{mandant_id}`` wird sondiert oder steht begruendet abseits.

    Die Zusicherung, um die es in Stufe 4 im Kern geht. Sie kann nur reissen, wenn
    jemand einen Endpunkt hinzufuegt und ihn in keine der beiden Listen eintraegt.
    """
    erfasst = {e.name for e in aeussere.SONDIERT} | set(aeussere.AUSNAHMEN)
    alle = {e.name for e in registrierte_endpunkte()}
    fehlend = sorted(alle - erfasst)
    assert not fehlend, (
        "Diese mandantengebundenen Endpunkte werden von keiner Sonde erreicht und "
        "stehen in keiner Ausnahmeliste:\n  " + "\n  ".join(fehlend)
    )


def test_keine_ausnahme_zeigt_ins_leere():
    """Jeder Eintrag der Ausnahmelisten entspricht einem heute vorhandenen Fall.

    Ein Eintrag fuer einen Endpunkt, den es nicht mehr gibt — oder fuer eine Kennung,
    die aus dem Pfad verschwunden ist —, ist keine harmlose Altlast: Er verdeckt, dass
    die Ausnahme nicht mehr gebraucht wird, und haelt die Ratsche unnoetig hoch.
    """
    alle = {e.name for e in registrierte_endpunkte()}
    veraltet = sorted(name for name in aeussere.AUSNAHMEN if name not in alle)
    assert not veraltet, (
        "Ausnahmen in test_aeussere_schicht.AUSNAHMEN ohne zugehoerige Route:\n  "
        + "\n  ".join(veraltet)
    )

    faelle = {
        f"{e.name} → {feld}"
        for e in registrierte_endpunkte()
        for feld in (*angreifbare_pfadkennungen(e), *rumpfkennungen(e))
    }
    veraltet_innen = sorted(name for name in innere.AUSNAHMEN if name not in faelle)
    assert not veraltet_innen, (
        "Ausnahmen in test_innere_schicht.AUSNAHMEN ohne zugehoerigen Fall:\n  "
        + "\n  ".join(veraltet_innen)
    )


def test_die_ausnahmelisten_sind_eine_ratsche():
    """Die Ausnahmelisten duerfen kuerzer werden, nie laenger.

    Fuenf aeussere Ausnahmen (die Admin-Endpunkte nach ADR-001), keine innere. Wer eine
    hinzufuegt, hebt hier eine Zahl an — sichtbar im Diff und mit Begruendung daneben,
    statt einen Endpunkt stillschweigend aus der Pruefung zu nehmen.
    """
    assert len(aeussere.AUSNAHMEN) <= 5, (
        f"Die aeussere Ausnahmeliste ist auf {len(aeussere.AUSNAHMEN)} gewachsen. "
        f"Wenn das richtig ist, hebe die Zahl hier mit Begruendung an."
    )
    assert len(innere.AUSNAHMEN) <= 0, (
        f"Die innere Ausnahmeliste hat {len(innere.AUSNAHMEN)} Eintraege. Sie war "
        f"leer; jeder Fall liess sich generisch sondieren. Wenn das nicht mehr gilt, "
        f"hebe die Zahl hier mit Begruendung an."
    )


def test_jede_ausnahme_ist_begruendet():
    """Keine Ausnahme ohne Grund im Klartext.

    Eine Ausnahme ohne Begruendung ist von einem Versehen nicht zu unterscheiden. Die
    Grenze von 40 Zeichen ist grob, verhindert aber ein ``"TODO"`` als Begruendung.
    """
    for liste, bezeichnung in (
        (aeussere.AUSNAHMEN, "test_aeussere_schicht"),
        (innere.AUSNAHMEN, "test_innere_schicht"),
    ):
        for name, grund in liste.items():
            assert len(grund) >= 40, (
                f"Die Ausnahme '{name}' in {bezeichnung} hat keine tragfaehige "
                f"Begruendung: {grund!r}"
            )


def test_jeder_endpunkt_mit_rumpf_hat_einen_bauer():
    """Zu jedem JSON-Rumpf gehoert ein Bauer, und zu jedem Bauer ein Endpunkt.

    Ohne Bauer laeuft die Sonde mit ``json=None`` und erhaelt 422 — was die Gegenprobe
    meldet. Diese Zusicherung sagt es fruueher und deutlicher. Die Rueckrichtung faengt
    den Fall, dass ein Endpunkt umbenannt wurde und der Bauer ins Leere zeigt.
    """
    mit_rumpf = {e.name for e in registrierte_endpunkte() if e.rumpfart == "json"}
    ohne_bauer = sorted(mit_rumpf - set(RUMPF))
    assert not ohne_bauer, (
        "Diese Endpunkte haben einen JSON-Rumpf, aber keinen Bauer in sonden.RUMPF:\n  "
        + "\n  ".join(ohne_bauer)
    )
    verwaist = sorted(set(RUMPF) - mit_rumpf)
    assert not verwaist, (
        "Diese Rumpfbauer gehoeren zu keinem Endpunkt mit JSON-Rumpf mehr:\n  "
        + "\n  ".join(verwaist)
    )


def test_jede_kennung_hat_eine_quelle():
    """Jeder Pfadparameter und jedes Rumpffeld laesst sich aus der Pruefumgebung fuellen.

    Fehlte eine Quelle, waere der Wert im Pfad keine Kennung, sondern eine
    Zeichenkette, die zu nichts passt — und die Antwort ein 404, das nichts belegt.
    """
    fehlend: list[str] = []
    for endpunkt in registrierte_endpunkte():
        if endpunkt.name in aeussere.AUSNAHMEN:
            continue
        felder = (*endpunkt.kennungen, *rumpfkennungen(endpunkt))
        for feld in felder:
            name = quelle(endpunkt, feld)
            if name not in QUELLEN and name not in OHNE_MANDANTENBINDUNG:
                fehlend.append(f"{endpunkt.name} → {feld} (als '{name}')")
    assert (
        not fehlend
    ), "Fuer diese Felder gibt es keine Quelle in sonden.QUELLEN:\n  " + "\n  ".join(
        sorted(fehlend)
    )


def test_sonderquellen_zeigen_auf_echte_felder():
    """Jede Abweichung in ``SONDERQUELLEN`` gehoert zu einem Feld, das es gibt.

    ``SONDERQUELLEN`` faengt die Faelle, in denen derselbe Parametername je Route etwas
    anderes bedeutet — ``account_id`` als Bankkonto und als Kontoverbindung eines
    Partners, ``item_id`` als Review-Eintrag und als Planposten. Wer eine solche Route
    umbaut, ohne den Eintrag anzupassen, bekaeme wieder eine Kennung der falschen
    Tabelle und ein 404, das nichts belegt.
    """
    vorhanden = {
        (e.pfad, feld)
        for e in registrierte_endpunkte()
        for feld in (*e.kennungen, *rumpfkennungen(e))
    }
    veraltet = sorted(
        f"{pfad} → {feld}"
        for pfad, feld in SONDERQUELLEN
        if (pfad, feld) not in vorhanden
    )
    assert not veraltet, (
        "Diese Eintraege in SONDERQUELLEN passen zu keinem Feld mehr:\n  "
        + "\n  ".join(veraltet)
    )


def test_jeder_pflicht_query_parameter_hat_einen_wert():
    """Query-Parameter ohne Vorgabewert brauchen einen Wert, sonst antwortet alles 422.

    Heute sind es drei Stellen mit zwei Namen (``section``, ``year``). Ein vierter
    Parameter ohne Vorgabewert wuerde seinen Endpunkt lautlos auf 422 setzen — die
    Gegenprobe faengt das, dieser Test benennt es.
    """
    gebraucht = {name for e in registrierte_endpunkte() for name in e.pflicht_query}
    fehlend = sorted(gebraucht - set(QUERYWERTE))
    assert not fehlend, (
        "Fuer diese Pflicht-Query-Parameter fehlt ein Wert in sonden.QUERYWERTE:\n  "
        + "\n  ".join(fehlend)
    )


def test_die_zugangspruefung_haengt_an_jeder_route_ausser_den_sieben():
    """``require_mandant_access`` an allen mandantengebundenen Routen — bis auf sieben.

    Das ist Befund M1, hier als laufende Zusicherung statt als Momentaufnahme. Die
    sieben sind einzeln begruendet; eine achte muss eingetragen werden und faellt damit
    im Diff auf.
    """
    ohne = {e.name for e in registrierte_endpunkte() if not e.mandantenpruefung}
    neu = sorted(ohne - set(OHNE_ZUGANGSPRUEFUNG))
    assert not neu, (
        "Diese mandantengebundenen Endpunkte haben keine Zugangspruefung und stehen "
        "nicht in OHNE_ZUGANGSPRUEFUNG:\n  " + "\n  ".join(neu)
    )
    verschwunden = sorted(set(OHNE_ZUGANGSPRUEFUNG) - ohne)
    assert not verschwunden, (
        "Diese Endpunkte haben inzwischen eine Zugangspruefung — Eintrag in "
        "OHNE_ZUGANGSPRUEFUNG streichen:\n  " + "\n  ".join(verschwunden)
    )


def test_die_endpunkte_ohne_mandantenbezug_sind_festgehalten():
    """Ein Endpunkt ohne ``{mandant_id}`` im Pfad muss begruendet sein.

    Der stillste denkbare Fehler: ein neuer Endpunkt, der mandantenbezogene Daten
    liefert, seinen Mandanten aber aus dem Token oder dem Rumpf nimmt. Er stuende in
    keiner Sondenliste, weil er den Pfadparameter nicht traegt. Diese Liste ist die
    einzige Stelle, an der er auffaellt.
    """
    gebunden = {e.name for e in registrierte_endpunkte()}
    frei = {e.name for e in alle_endpunkte() if e.name not in gebunden}

    neu = sorted(frei - set(OHNE_MANDANTENBEZUG))
    assert not neu, (
        "Diese Endpunkte tragen keine mandant_id im Pfad und sind nicht begruendet. "
        "Wenn sie mandantenbezogene Daten liefern, ist das ein Befund; wenn nicht, "
        "gehoeren sie mit Grund in OHNE_MANDANTENBEZUG:\n  " + "\n  ".join(neu)
    )
    verschwunden = sorted(set(OHNE_MANDANTENBEZUG) - frei)
    assert not verschwunden, (
        "Diese Eintraege in OHNE_MANDANTENBEZUG gibt es nicht mehr oder sie sind "
        "inzwischen mandantengebunden:\n  " + "\n  ".join(verschwunden)
    )


def test_die_zahl_der_sonden_bleibt_nachvollziehbar():
    """Haelt fest, wie viele Faelle die drei Sonden heute abdecken.

    Nicht als Selbstzweck: Die Zahlen stehen so auch in
    ``docs/mandantenfaehigkeit-plan.md``, und eine Zusicherung ist die einzige Art,
    eine Zahl in einem Dokument haltbar zu machen. Sie duerfen wachsen — schrumpfen
    heisst, dass Sonden verlorengegangen sind.
    """
    gebunden = registrierte_endpunkte()
    assert len(gebunden) >= 89, (
        f"Nur {len(gebunden)} mandantengebundene Endpunkte gefunden, erwartet "
        f"mindestens 89. Sind Routen verschwunden, oder findet die Introspektion sie "
        f"nicht mehr?"
    )
    assert len(aeussere.SONDIERT) >= 84, f"Sonde 1: {len(aeussere.SONDIERT)} Faelle"
    assert (
        len(innere._faelle_pfad()) >= 60
    ), f"Sonde 2: {len(innere._faelle_pfad())} Faelle"
    assert (
        len(innere._faelle_rumpf()) >= 14
    ), f"Sonde 3: {len(innere._faelle_rumpf())} Faelle"
    assert MANDANTENPARAMETER == "mandant_id"


#: Kennungsfelder im Rumpf, die Sonde 3 nicht generisch erreicht — mit Begruendung
#: **und** dem Test, der sie stattdessen von Hand prueft.
#:
#: Ein Eintrag hier ist keine Ausnahme von der Pruefung, sondern ein Verweis auf eine
#: andere. Wer einen hinzufuegt, ohne den genannten Test zu schreiben, hat eine Luecke
#: mit einer Begruendung davor.
RUMPFFELDER_VON_HAND: dict[str, str] = {
    "POST /api/v1/mandants/{mandant_id}/review/{item_id}/adjust → splits[].service_id": (
        "adjust waehlt seinen Weg am Typ des Review-Eintrags, und der kommt aus der "
        "item_id im Pfad: service_assignment nimmt service_id, "
        "manual_service_assignment nimmt splits. Ein Rumpfbauer kann nicht beides "
        "bedienen. Geprueft in test_innere_schicht.py::"
        "test_eine_aufteilung_kann_keine_fremde_leistung_nennen."
    ),
}


def test_jedes_kennungsfeld_im_rumpf_wird_sondiert():
    """Jedes UUID-Feld eines Rumpfschemas ist sondiert oder von Hand geprueft.

    Die Zusicherung, die ``rumpfkennungen()`` allein nicht leisten kann. Diese Liste
    kommt aus den **Rumpfbauern**: Sie schuetzt davor, dass Bauer und Sonde
    auseinanderlaufen, aber nicht davor, dass ein Feld ins **Schema** kommt, das kein
    Bauer je gesehen hat. Wer ``ReassignRequest`` ein ``service_id`` hinzufuegt, hat
    dann nicht eine Sonde weniger — er hat eine, die es nie gab.

    Hier wird deshalb das Schema selbst gelesen. Es ist derselbe Gedanke wie bei der
    Endpunktliste, eine Ebene tiefer: nicht abschreiben, sondern erzeugen.

    Felder ohne Mandantenbindung fallen heraus (``user_id`` — Nutzer sind global).
    """
    fehlend: list[str] = []
    for endpunkt in registrierte_endpunkte():
        sondiert = set(rumpfkennungen(endpunkt))
        for feld in kennungsfelder_im_schema(endpunkt):
            if feld in sondiert:
                continue
            if quelle(endpunkt, feld) in OHNE_MANDANTENBINDUNG:
                continue
            schluessel = f"{endpunkt.name} → {feld}"
            if schluessel in RUMPFFELDER_VON_HAND:
                continue
            fehlend.append(schluessel)

    assert not fehlend, (
        "Diese Kennungsfelder stehen im Rumpfschema, werden von keinem Rumpfbauer "
        "gesetzt und von keinem Test von Hand geprueft:\n  "
        + "\n  ".join(sorted(fehlend))
        + "\n\nEntweder das Feld im zugehoerigen Bauer in sonden.RUMPF ergaenzen "
        "(dann prueft es Sonde 3 von selbst) oder mit Begruendung und dem Namen des "
        "handgeschriebenen Tests in RUMPFFELDER_VON_HAND eintragen."
    )


def test_die_handgeschriebenen_rumpffelder_gibt_es_noch():
    """Jeder Eintrag in ``RUMPFFELDER_VON_HAND`` bezeichnet ein Feld, das es gibt.

    Sonst bliebe eine Ausnahme stehen, deren Grund verschwunden ist — und mit ihr die
    Annahme, hier sei etwas geprueft, was niemand mehr prueft.
    """
    vorhanden = {
        f"{e.name} → {feld}"
        for e in registrierte_endpunkte()
        for feld in kennungsfelder_im_schema(e)
    }
    veraltet = sorted(k for k in RUMPFFELDER_VON_HAND if k not in vorhanden)
    assert not veraltet, (
        "Diese Eintraege in RUMPFFELDER_VON_HAND passen zu keinem Schemafeld mehr:\n  "
        + "\n  ".join(veraltet)
    )
    assert len(RUMPFFELDER_VON_HAND) <= 1, (
        f"{len(RUMPFFELDER_VON_HAND)} Felder werden von Hand geprueft statt von "
        f"Sonde 3. Ratsche wie die uebrigen: Wenn das richtig ist, hebe die Zahl hier "
        f"mit Begruendung an."
    )
