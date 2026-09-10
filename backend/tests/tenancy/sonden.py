"""Die Sonden: wie ein Endpunkt bedient und wie er angegriffen wird.

Die drei Fragen, die Stufe 4 stellt
-----------------------------------
Fuer jeden der 89 mandantengebundenen Endpunkte, mit dem Token eines Nutzers, der zu
Mandant A gehoert und zu B **nicht**:

**Sonde 1 — die aeussere Schicht.** Vollstaendig gueltige Anfrage an Mandant B. Muss
403 ergeben, und zwar aus ``require_mandant_access``. Geprueft in
``test_aeussere_schicht.py``.

**Sonde 2 — die innere Schicht, Kennung im Pfad.** Eigene ``mandant_id``, aber eine
Objektkennung aus B. Muss 403 oder 404 ergeben. Hier lagen die beiden Lecks aus
Etappe 1 des Code-Reviews. Geprueft in ``test_innere_schicht.py``.

**Sonde 3 — die innere Schicht, Kennung im Rumpf.** Eigene ``mandant_id``, eigene
Pfadkennungen, aber eine Objektkennung aus B **im Rumpf**. Das ist die Klasse, zu der
M16 gehoerte: ``bulk-assign`` prueft die Buchungszeilen gegen den Mandanten, das
Zuordnungsziel ``partner_id`` aber nicht. Zehn Endpunkte nehmen eine mandantengebundene
Kennung im Rumpf, vierzehn Felder insgesamt. Geprueft in ``test_innere_schicht.py``.

Warum ``check_tenancy.py`` diese Klasse nicht findet: Die Query trug ihren Filter, was
fehlte war eine **Validierung**. Eine statische Pruefung sieht, ob eine ``mandant_id``
im Statement vorkommt, nicht ob das benannte Objekt zu ihr gehoert.

Zu jeder Sonde gehoert eine Gegenprobe
--------------------------------------
Ein Test, der nur „403" verlangt, bleibt auch bei einem Endpunkt gruen, der
grundsaetzlich verweigert — weil der Rumpf ungueltig ist, weil das Objekt fehlt, weil
die Rolle nicht reicht. In Stufe 3 hat die Gegenprobe **dreimal** einen Test entlarvt,
der nichts prueft. Deshalb fuehrt jede Sonde denselben Aufruf zusaetzlich gegen die
**eigenen** Daten und verlangt, dass er *nicht* an der Mandantenpruefung scheitert.

Die Gegenprobe verlangt bewusst **nicht** 2xx, sondern „nicht 403, nicht 404, nicht
422, kein Serverfehler". Ein fachliches 409 („Partner existiert bereits") belegt
gerade, dass die Mandantenpruefung passiert wurde — das ist eine gueltige Antwort auf
die Frage, die hier gestellt wird. Siehe ``erwartungen.py``.

Warum die Rumpffelder zweimal ermittelt werden
---------------------------------------------
``rumpfkennungen()`` erfaehrt die kennungstragenden Rumpffelder, indem es den
Rumpfbauer mit einem mitschreibenden Holer aufruft. Damit kann die Liste nicht von den
Rumpfbauern abweichen. Eine handgeschriebene Liste waere nach der ersten
Schema-Aenderung falsch, und zwar still.

Das genuegt aber nur zur Haelfte: Es schuetzt davor, dass Bauer und Sonde auseinander
laufen, nicht davor, dass ein Feld ins **Schema** kommt, das kein Bauer je gesehen hat.
Wer ``ReassignRequest`` ein ``service_id`` hinzufuegt, hat dann nicht eine Sonde
weniger — er hat eine, die es nie gab. Das ist derselbe Fehler wie eine abgeschriebene
Endpunktliste, eine Ebene tiefer.

Deshalb liest ``kennungsfelder_im_schema()`` die Pydantic-Schemata selbst, rekursiv,
und ``test_endpunktliste.py`` haelt beide Listen gegeneinander. Was das Schema hergibt
und kein Bauer setzt, muss von Hand geprueft und in ``RUMPFFELDER_VON_HAND``
eingetragen sein — heute ein einziges Feld.

Was die Pruefumgebung nicht hergibt
-----------------------------------
``zwei_mandanten`` aus ``tests/conftest.py`` traegt je Mandant Konto, Partner,
Leistung, Matcher, Schlagwort, Gruppe, Spaltenzuordnung, Partner-IBAN/-Konto/-Name,
Importlauf und zwei Buchungen. Acht Satzarten fehlen ihr, die Endpunkte aus Stufe 4
brauchen. Sie kommen aus ``erweitere_welt()`` und **nicht** aus der gemeinsamen
Fixture: Ein zusaetzlicher Review-Eintrag oder Planposten in ``zwei_mandanten``
veraendert die Ausgangslage jedes Tests, der Eintraege zaehlt — und davon gibt es in
``tests/review`` und ``tests/journal`` mehrere. Die Erweiterung gehoert deshalb hierhin,
wo nur Stufe 4 sie sieht.

Dass die fehlenden Saetze ueberhaupt angelegt werden, ist kein Beiwerk. Fehlt der Satz
im **fremden** Mandanten, antwortet der Angriff mit 404, ohne etwas zu belegen — genau
der Fall, an dem in Stufe 3 die Spaltenzuordnungs-Pruefung beinahe wertlos geblieben
waere.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from itertools import count
from typing import Any, get_args
from uuid import UUID, uuid4

from fastapi.routing import APIRoute
from httpx import AsyncClient, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import User
from app.forecast.models import ForecastPlannedItem, ForecastSnapshot
from app.imports.models import ReviewItem, utcnow
from app.partners.models import Partner
from app.services.models import (
    ServiceGroup,
    ServiceGroupAssignment,
    ServiceGroupSection,
)
from app.tenants.models import AccountExcludedIdentifier
from tests.conftest import MandantWelt, ZweiMandanten
from tests.tenancy.endpunkte import Endpunkt

# ─── Frische Werte ───────────────────────────────────────────────────────────

_zaehler = count(1)


def frisch(vorsatz: str) -> str:
    """Eine in diesem Prozess einmalige Zeichenkette.

    Namen, Muster und IBANs muessen frisch sein, weil viele Endpunkte auf
    Eindeutigkeit pruefen. Ein wiederverwendeter Name ergaebe 409 — was die Gegenprobe
    zwar durchlaesst (siehe Modulkopf), aber den Test schwerer lesbar macht als noetig.
    """
    return f"{vorsatz}-{next(_zaehler):04d}-{uuid4().hex[:6]}"


def frische_iban() -> str:
    """Eine syntaktisch brauchbare, im Prozess einmalige IBAN.

    Die Schemata verlangen 15 bis 34 Zeichen und pruefen keine Pruefsumme. Nach
    ADR-008 ist eine IBAN ueber alle Mandanten hinweg eindeutig, deshalb darf hier
    keine wiederkehren.
    """
    return f"DE{next(_zaehler):020d}"


def frische_kontonummer() -> str:
    """Eine im Prozess einmalige Kontonummer — ADR-008 gilt auch fuer ``(blz, nr)``."""
    return f"{next(_zaehler):010d}"


# ─── Was der Pruefumgebung fehlt ─────────────────────────────────────────────


@dataclass(frozen=True)
class Zusatzwelt:
    """Die Satzarten, die ``zwei_mandanten`` nicht mitbringt.

    ==========================  =========================================================
    ``zweiter_partner``         fuer ``partners/merge`` — verschmelzen braucht zwei
    ``zweite_gruppe``           fuer ``reassign_to_group_id`` beim Loeschen einer Gruppe
    ``ausgeschlossene_kennung`` fuer ``excluded-identifiers/{identifier_id}``
    ``pruefposten``             Review-Eintrag ``service_assignment`` — der reichste Typ
    ``unbekannt_posten``        Review-Eintrag ``no_partner_identified`` fuer die
                                Gruppenaufloesung
    ``planposten``              fuer ``forecast/planned-items/{item_id}``
    ``momentaufnahme``          fuer ``forecast/snapshots/{snapshot_id}``
    ``gruppenzuordnung``        damit ``DELETE .../service-groups/{group_id}`` sein
                                ``reassign_to_group_id`` ueberhaupt liest — siehe unten
    ==========================  =========================================================

    ``gruppenzuordnung`` ist der Fall, der beim Bauen dieser Sonden aufgefallen ist.
    ``delete_service_group`` prueft die Zielgruppe gegen den Mandanten — aber nur
    **innerhalb** von ``if assignments and ...``. Ohne eine zugeordnete Leistung gibt
    es nichts umzuhaengen, das Feld wird nie gelesen, und der Aufruf antwortet mit 204,
    obwohl er eine fremde Gruppe nennt. Der Angriff waere durchgegangen und der Test
    haette einen Befund gemeldet, den es nicht gibt. Mit der Zuordnung greift die
    Pruefung, und die Sonde sagt etwas aus.

    Alle acht haengen an **einem** Mandanten und werden fuer beide Welten angelegt.
    Nur so hat der Angriff auf die fremde Kennung ueberhaupt ein Ziel.
    """

    zweiter_partner: Partner
    zweite_gruppe: ServiceGroup
    ausgeschlossene_kennung: AccountExcludedIdentifier
    pruefposten: ReviewItem
    unbekannt_posten: ReviewItem
    planposten: ForecastPlannedItem
    momentaufnahme: ForecastSnapshot
    gruppenzuordnung: ServiceGroupAssignment


async def erweitere_welt(
    session: AsyncSession, welt: MandantWelt, *, urheber: User
) -> Zusatzwelt:
    """Legt die acht fehlenden Satzarten fuer eine Welt an.

    ``urheber`` landet in ``created_by`` — die Spalten sind nullbar, aber ein
    nachvollziehbarer Wert ist besser als ``None``, wenn ein Endpunkt ihn ausliest.

    Die Review-Eintraege haengen an verschiedenen Buchungszeilen, weil
    ``review_items`` auf ``(journal_line_id, item_type)`` eindeutig ist und der
    Ausgangsbuchung schon eine Aufteilung anhaengt.
    """
    jetzt = utcnow()

    zweiter_partner = Partner(
        mandant_id=welt.id,
        name=frisch("Zweitpartner"),
        is_active=True,
        created_at=jetzt,
        updated_at=jetzt,
    )
    session.add(zweiter_partner)

    zweite_gruppe = ServiceGroup(
        mandant_id=welt.id,
        section=ServiceGroupSection.expense.value,
        name=frisch("Zweitgruppe"),
        sort_order=1,
        created_at=jetzt,
        updated_at=jetzt,
    )
    session.add(zweite_gruppe)

    ausgeschlossene_kennung = AccountExcludedIdentifier(
        account_id=welt.konto.id,
        identifier_type="iban",
        value=frische_iban(),
        label="Eigene IBAN des Kontos",
        created_at=jetzt,
    )
    session.add(ausgeschlossene_kennung)

    # `service_assignment` ist der Typ, den `adjust` mit einer `service_id` im Rumpf
    # bedient — genau die Kennung, die Sonde 3 austauscht.
    pruefposten = ReviewItem(
        mandant_id=welt.id,
        item_type="service_assignment",
        journal_line_id=welt.zeilen[1].id,
        context={"partner_name_raw": welt.partner.name},
        status="open",
        created_at=jetzt,
        updated_at=jetzt,
    )
    session.add(pruefposten)

    unbekannt_posten = ReviewItem(
        mandant_id=welt.id,
        item_type="no_partner_identified",
        journal_line_id=welt.zeilen[0].id,
        context={"partner_name_raw": welt.partner.name},
        status="open",
        created_at=jetzt,
        updated_at=jetzt,
    )
    session.add(unbekannt_posten)

    planposten = ForecastPlannedItem(
        mandant_id=welt.id,
        service_id=welt.leistung.id,
        period="2027-03",
        amount=Decimal("250.00"),
        note="Planposten der Pruefumgebung",
        created_by=urheber.id,
        created_at=jetzt,
        updated_at=jetzt,
    )
    session.add(planposten)

    momentaufnahme = ForecastSnapshot(
        mandant_id=welt.id,
        label="Momentaufnahme der Pruefumgebung",
        scenario="expected",
        as_of="2026-01-31",
        currency="EUR",
        start_balance=Decimal("1000.00"),
        months=[],
        created_by=urheber.id,
        created_at=jetzt,
    )
    session.add(momentaufnahme)

    # Die Leistung dieser Welt haengt in der Gruppe dieser Welt. Beide Abschnitte sind
    # `expense`; `delete_service_group` verlangt beim Umhaengen denselben Abschnitt.
    gruppenzuordnung = ServiceGroupAssignment(
        mandant_id=welt.id,
        service_id=welt.leistung.id,
        service_group_id=welt.gruppe.id,
        created_at=jetzt,
        updated_at=jetzt,
    )
    session.add(gruppenzuordnung)

    await session.commit()
    for objekt in (
        zweiter_partner,
        zweite_gruppe,
        ausgeschlossene_kennung,
        pruefposten,
        unbekannt_posten,
        planposten,
        momentaufnahme,
        gruppenzuordnung,
    ):
        await session.refresh(objekt)

    return Zusatzwelt(
        zweiter_partner=zweiter_partner,
        zweite_gruppe=zweite_gruppe,
        ausgeschlossene_kennung=ausgeschlossene_kennung,
        pruefposten=pruefposten,
        unbekannt_posten=unbekannt_posten,
        planposten=planposten,
        momentaufnahme=momentaufnahme,
        gruppenzuordnung=gruppenzuordnung,
    )


@dataclass(frozen=True)
class Seite:
    """Eine Mandantenseite: Welt, Erweiterung und der Nutzer, der nur zu ihr gehoert.

    Die Sonden reden nie ueber „Mandant A" oder „Mandant B", sondern ueber die eigene
    und die fremde Seite. Damit laesst sich derselbe Test in beide Richtungen fahren —
    was in Stufe 3 wichtig war, weil eine einseitige Pruefung nur die halbe Aussage
    macht.
    """

    welt: MandantWelt
    zusatz: Zusatzwelt
    nutzer: User

    @property
    def id(self) -> UUID:
        """Die ``mandant_id`` dieser Seite."""
        return self.welt.id


@dataclass(frozen=True)
class Pruefstand:
    """Beide Seiten samt der Nutzer, die es nur einmal gibt."""

    a: Seite
    b: Seite
    nutzer_beide: User
    nutzer_ohne: User
    mandant_admin_a: User
    admin: User
    umgebung: ZweiMandanten


# ─── Woher eine Kennung kommt ────────────────────────────────────────────────

#: Logischer Name → wie er aus einer Seite geholt wird.
#:
#: Derselbe Name gilt fuer Pfadparameter **und** Rumpffelder. Das ist Absicht: Ein
#: ``partner_id`` im Rumpf bezeichnet dasselbe wie eines im Pfad, und beide Sonden
#: sollen dieselbe Quelle benutzen.
QUELLEN: dict[str, Callable[[Seite], UUID]] = {
    "account_id": lambda s: _kennung(s.welt.konto),
    "identifier_id": lambda s: _kennung(s.zusatz.ausgeschlossene_kennung),
    "run_id": lambda s: _kennung(s.welt.import_lauf),
    "item_id": lambda s: _kennung(s.zusatz.pruefposten),
    "snapshot_id": lambda s: _kennung(s.zusatz.momentaufnahme),
    "partner_id": lambda s: _kennung(s.welt.partner),
    "iban_id": lambda s: _kennung(s.welt.partner_iban),
    "name_id": lambda s: _kennung(s.welt.partner_name),
    "service_id": lambda s: _kennung(s.welt.leistung),
    "group_id": lambda s: _kennung(s.welt.gruppe),
    "matcher_id": lambda s: _kennung(s.welt.matcher),
    "keyword_id": lambda s: _kennung(s.welt.schlagwort),
    # Die Ausgangsbuchung — sie traegt eine Leistungsaufteilung, und mehrere
    # Endpunkte (`.../lines/{line_id}/ok`) brauchen genau das.
    "line_id": lambda s: _kennung(s.welt.zeilen[1]),
    "user_id": lambda s: _kennung(s.nutzer),
    # Nur im Rumpf:
    "source_partner_id": lambda s: _kennung(s.zusatz.zweiter_partner),
    "target_partner_id": lambda s: _kennung(s.welt.partner),
    "service_group_id": lambda s: _kennung(s.welt.gruppe),
    "reassign_to_group_id": lambda s: _kennung(s.zusatz.zweite_gruppe),
    "split_service_id": lambda s: _kennung(s.welt.leistung),
    "gruppen_item_id": lambda s: _kennung(s.zusatz.unbekannt_posten),
    # Mehrzahlfelder im Rumpf: Der Holer wird mit dem **Schemafeldnamen** aufgerufen
    # (siehe `rumpfkennungen`), deshalb stehen sie hier in der Mehrzahl.
    "line_ids": lambda s: _kennung(s.welt.zeilen[1]),
    "item_ids": lambda s: _kennung(s.zusatz.unbekannt_posten),
}

#: ``(pfad, feld)`` → abweichender logischer Name.
#:
#: Zwei Parameternamen bedeuten je nach Route etwas anderes. Wer das uebersieht,
#: schickt eine Kennung der falschen Tabelle und erhaelt 404 — der Test blieb gruen und
#: prueft nichts. Deshalb steht jede Abweichung hier ausdruecklich und wird von
#: ``test_endpunktliste.py`` gegen die Routen gehalten.
SONDERQUELLEN: dict[tuple[str, str], str] = {
    # Hier ist `account_id` **kein** Bankkonto des Mandanten, sondern eine
    # Kontoverbindung des Partners (`partner_accounts`).
    (
        "/api/v1/mandants/{mandant_id}/partners/{partner_id}/accounts/{account_id}",
        "account_id",
    ): "partner_account_id",
    # Hier ist `item_id` ein Planposten der Prognose, kein Review-Eintrag.
    (
        "/api/v1/mandants/{mandant_id}/forecast/planned-items/{item_id}",
        "item_id",
    ): "planposten_id",
}

QUELLEN["partner_account_id"] = lambda s: _kennung(s.welt.partner_konto)
QUELLEN["planposten_id"] = lambda s: _kennung(s.zusatz.planposten)

#: Logische Namen, deren Objekt **keinem** Mandanten gehoert.
#:
#: ``users`` ist eine globale Tabelle; die Zuordnung steht in ``mandant_users``. Eine
#: „fremde Nutzerkennung" gibt es deshalb nicht, und Sonde 2 und 3 haben an diesen
#: Feldern nichts zu holen. Was hier zu pruefen ist — wer wen welchem Mandanten
#: zuordnen darf —, prueft Stufe 2 in ``tests/auth/test_mandantenzuordnung.py``.
OHNE_MANDANTENBINDUNG = {"user_id"}


def _kennung(objekt: Any) -> UUID:
    """Holt die Primaerkennung eines Datensatzes und stellt sicher, dass sie da ist.

    Die Modelle deklarieren ``id`` als ``UUID | None`` (weil SQLModel den Wert erst
    beim Anlegen setzt). Ohne diese Zusicherung wuerde ein ``None`` als Zeichenkette
    ``"None"`` in den Pfad geraten und ein 422 ausloesen, das nach einer bestandenen
    Pruefung aussieht.
    """
    kennung = getattr(objekt, "id", None)
    assert kennung is not None, f"{type(objekt).__name__} ohne Kennung"
    return kennung


def quelle(endpunkt: Endpunkt, feld: str) -> str:
    """Der logische Name, unter dem ``feld`` dieses Endpunkts aufzuloesen ist."""
    return SONDERQUELLEN.get((endpunkt.pfad, feld), feld)


def loese_auf(endpunkt: Endpunkt, feld: str, seite: Seite) -> str:
    """Die Kennung fuer ``feld`` dieses Endpunkts aus ``seite``, als Zeichenkette."""
    name = quelle(endpunkt, feld)
    hole = QUELLEN.get(name)
    assert hole is not None, (
        f"Keine Quelle fuer '{name}' ({endpunkt.name}). Entweder in QUELLEN "
        f"ergaenzen oder in SONDERQUELLEN auf einen vorhandenen Namen abbilden."
    )
    return str(hole(seite))


# ─── Pflicht-Query ───────────────────────────────────────────────────────────

#: Query-Parameter ohne Vorgabewert und ein brauchbarer Wert dafuer.
#:
#: Fehlt einer, antwortet der Endpunkt mit 422 — und ein 422 sagt nichts ueber die
#: Mandantentrennung. Es sind nur drei; ``test_endpunktliste.py`` haelt sie gegen die
#: Routen, damit ein vierter nicht still durchfaellt.
QUERYWERTE: dict[str, str] = {
    "section": ServiceGroupSection.expense.value,
    "year": "2026",
}


# ─── Rumpf ───────────────────────────────────────────────────────────────────

#: Ein Holer liefert die Kennung eines logischen Feldes als Zeichenkette.
Holer = Callable[[str], str]

#: Eine CSV, die zur Spaltenzuordnung der Pruefumgebung passt.
#:
#: Die Fixture legt je Konto eine ``ColumnMappingConfig`` mit genau diesen
#: Spaltennamen an, Trennzeichen ``;``, Dezimaltrenner ``,`` und Datumsformat
#: ``%d.%m.%Y``. Mit einer beliebigen CSV wuerde der Import auf den eigenen Daten
#: scheitern, und die Gegenprobe waere wertlos.
CSV_INHALT = (
    b"Valuta;Buchung;Betrag;IBAN;Empfaenger;Text\n"
    b"05.02.2026;05.02.2026;-42,00;DE02120300000000202051;Sonde;Sonde Stufe 4\n"
)


def _rumpf_mandant_zuordnen(hole: Holer) -> dict[str, Any]:
    """``POST /mandants/{mandant_id}/users`` — Nutzer dem Mandanten zuordnen."""
    return {"user_id": hole("user_id")}


def _rumpf_mandant_aendern(hole: Holer) -> dict[str, Any]:
    """``PATCH /mandants/{mandant_id}`` — Mandanten umbenennen."""
    return {"name": frisch("Mandant")}


def _rumpf_aufraeumen(hole: Holer) -> dict[str, Any]:
    """``POST /mandants/{mandant_id}/cleanup`` — der schaerfste Endpunkt des Systems.

    ``mode="selected"`` mit **leerer** Auswahl: Der Rumpf ist gueltig, aber es gibt
    nichts zu loeschen. Sonde 1 scheitert ohnehin an der Rollenpruefung, doch ein
    versehentlich durchgehender Aufruf soll keinen Mandanten mitnehmen.
    """
    return {"mode": "selected", "scopes": []}


def _rumpf_konto_anlegen(hole: Holer) -> dict[str, Any]:
    """``POST .../accounts`` — Konto ohne IBAN, damit ADR-008 nicht dazwischenkommt."""
    return {"name": frisch("Konto"), "opening_balance": "0.00"}


def _rumpf_konto_aendern(hole: Holer) -> dict[str, Any]:
    """``PATCH .../accounts/{account_id}`` — nur der Name, das genuegt fuer die Frage."""
    return {"name": frisch("Konto")}


def _rumpf_spaltenzuordnung(hole: Holer) -> dict[str, Any]:
    """``PUT .../column-mapping`` — dieselben Spalten, die die Fixture eingetragen hat."""
    return {
        "valuta_date_col": "Valuta",
        "booking_date_col": "Buchung",
        "amount_col": "Betrag",
        "partner_iban_col": "IBAN",
        "partner_name_col": "Empfaenger",
        "description_col": "Text",
    }


def _rumpf_kennung_ausschliessen(hole: Holer) -> dict[str, Any]:
    """``POST .../excluded-identifiers`` — eine IBAN von der Erkennung ausnehmen."""
    return {"identifier_type": "iban", "value": frische_iban(), "label": "Sonde"}


def _rumpf_partner_anlegen(hole: Holer) -> dict[str, Any]:
    """``POST .../partners`` — neuer Partner mit frischem Namen."""
    return {"name": frisch("Partner")}


def _rumpf_partner_aendern(hole: Holer) -> dict[str, Any]:
    """``PATCH .../partners/{partner_id}`` — Anzeigename setzen."""
    return {"display_name": frisch("Anzeige")}


def _rumpf_iban(hole: Holer) -> dict[str, Any]:
    """``POST .../partners/{partner_id}/ibans`` und dessen Vorschau."""
    return {"iban": frische_iban()}


def _rumpf_partnerkonto(hole: Holer) -> dict[str, Any]:
    """``POST .../partners/{partner_id}/accounts`` und dessen Vorschau."""
    return {"account_number": frische_kontonummer(), "blz": "50010517"}


def _rumpf_partnername(hole: Holer) -> dict[str, Any]:
    """``POST .../partners/{partner_id}/names`` — zusaetzlicher Schreibname."""
    return {"name": frisch("Schreibname")}


def _rumpf_verschmelzen(hole: Holer) -> dict[str, Any]:
    """``POST .../partners/merge`` — zwei Kennungen im Rumpf, beide angreifbar.

    Der interessanteste Rumpf des Systems: Verschmelzen zieht alle Buchungen,
    Leistungen und Kennungen des einen Partners auf den anderen. Steht eine der beiden
    Kennungen in einem fremden Mandanten, wanderten Geschaeftsdaten ueber die Grenze.
    """
    return {
        "source_partner_id": hole("source_partner_id"),
        "target_partner_id": hole("target_partner_id"),
    }


def _rumpf_leistung_anlegen(hole: Holer) -> dict[str, Any]:
    """``POST .../partners/{partner_id}/services`` — neue Leistung am Partner."""
    return {"name": frisch("Leistung")}


def _rumpf_leistung_aendern(hole: Holer) -> dict[str, Any]:
    """``PATCH .../services/{service_id}`` — Beschreibung setzen."""
    return {"description": frisch("Beschreibung")}


def _rumpf_matcher(hole: Holer) -> dict[str, Any]:
    """``POST .../services/{service_id}/matchers`` und dessen Vorschau."""
    return {"pattern": frisch("Muster"), "pattern_type": "string"}


def _rumpf_matcher_aendern(hole: Holer) -> dict[str, Any]:
    """``PATCH .../services/{service_id}/matchers/{matcher_id}``."""
    return {"pattern": frisch("Muster")}


def _rumpf_schlagwort(hole: Holer) -> dict[str, Any]:
    """``POST .../settings/service-keywords`` — Schlagwort fuer die Typerkennung.

    ``target_service_type`` zielt auf ``KeywordTargetType`` und nicht auf
    ``ServiceType``: Schlagwoerter erkennen nur Personengruppen.
    """
    return {
        "pattern": frisch("Schlagwort"),
        "pattern_type": "string",
        "target_service_type": "employee",
    }


def _rumpf_schlagwort_aendern(hole: Holer) -> dict[str, Any]:
    """``PATCH .../settings/service-keywords/{keyword_id}``."""
    return {"pattern": frisch("Schlagwort")}


def _rumpf_gruppe_anlegen(hole: Holer) -> dict[str, Any]:
    """``POST .../service-groups`` — neue Gliederungsgruppe."""
    return {"section": ServiceGroupSection.expense.value, "name": frisch("Gruppe")}


def _rumpf_gruppe_aendern(hole: Holer) -> dict[str, Any]:
    """``PATCH .../service-groups/{group_id}``."""
    return {"name": frisch("Gruppe")}


def _rumpf_gruppe_loeschen(hole: Holer) -> dict[str, Any]:
    """``DELETE .../service-groups/{group_id}`` — mit Umhaengen der Leistungen.

    ``reassign_to_group_id`` ist eine Kennung im Rumpf eines **Loeschaufrufs**: Wer
    hier eine fremde Gruppe nennt, haengt Leistungen in einen anderen Mandanten um.
    """
    return {"reassign_to_group_id": hole("reassign_to_group_id")}


def _rumpf_gruppenzuordnung(hole: Holer) -> dict[str, Any]:
    """``POST .../services/{service_id}/group-assignment``."""
    return {"service_group_id": hole("service_group_id")}


def _rumpf_gruppe_aufloesen(hole: Holer) -> dict[str, Any]:
    """``POST .../review/unidentified-groups/resolve`` — Sammelaufloesung.

    Drei Kennungen auf einmal: die Eintraege, der Partner und die Leistung. Damit ist
    dies der Endpunkt mit der breitesten Rumpf-Angriffsflaeche des Systems.

    ``service_id`` ist nicht wirklich wahlfrei: Das Schema verlangt entweder
    ``service_id`` oder ``service_name``. Die erste Fassung dieser Sonde liess beide
    weg — und die Gegenprobe hat es gemeldet (422 auf den eigenen Daten). Ohne sie
    waere der Angriff mit 422 gescheitert und der Test gruen geblieben, ohne etwas zu
    pruefen.
    """
    return {
        "item_ids": [hole("item_ids")],
        "pattern": frisch("Muster"),
        "partner_id": hole("partner_id"),
        "service_id": hole("service_id"),
    }


def _rumpf_review_anpassen(hole: Holer) -> dict[str, Any]:
    """``POST .../review/{item_id}/adjust`` — Leistung eines Eintrags korrigieren."""
    return {"service_id": hole("service_id")}


def _rumpf_review_umhaengen(hole: Holer) -> dict[str, Any]:
    """``POST .../review/{item_id}/reassign`` — Buchung einem anderen Partner geben."""
    return {"partner_id": hole("partner_id")}


def _rumpf_review_neuer_partner(hole: Holer) -> dict[str, Any]:
    """``POST .../review/{item_id}/new-partner`` — Partner aus dem Eintrag anlegen."""
    return {"name": frisch("Partner")}


def _rumpf_sammelzuordnung(hole: Holer) -> dict[str, Any]:
    """``POST .../journal/bulk-assign`` — der Endpunkt, an dem M16 hing.

    Die Buchungszeilen wurden gegen den Mandanten geprueft, das Zuordnungsziel
    ``partner_id`` nicht. Sonde 3 tauscht genau dieses Feld.
    """
    return {"line_ids": [hole("line_ids")], "partner_id": hole("partner_id")}


def _rumpf_leistung_zuordnen(hole: Holer) -> dict[str, Any]:
    """``POST .../journal/{line_id}/assign-service``."""
    return {"service_id": hole("service_id")}


def _rumpf_prognoseregel(hole: Holer) -> dict[str, Any]:
    """``PUT .../services/{service_id}/forecast-rule``."""
    return {"mode": "auto"}


def _rumpf_planposten_anlegen(hole: Holer) -> dict[str, Any]:
    """``POST .../forecast/planned-items`` — bekannter Betrag in einem Monat."""
    return {
        "service_id": hole("service_id"),
        "period": "2027-06",
        "amount": "123.45",
    }


def _rumpf_planposten_aendern(hole: Holer) -> dict[str, Any]:
    """``PATCH .../forecast/planned-items/{item_id}``."""
    return {"amount": "234.56"}


def _rumpf_momentaufnahme(hole: Holer) -> dict[str, Any]:
    """``POST .../forecast/snapshots`` — Prognose einfrieren."""
    return {"label": frisch("Momentaufnahme"), "scenario": "expected"}


def _rumpf_betragspruefung(hole: Holer) -> dict[str, Any]:
    """``POST .../settings/tests/.../lines/{line_id}/ok`` — Abweichung abhaken."""
    return {"split_service_id": hole("split_service_id"), "is_ok": True}


#: Endpunktname → Rumpfbauer. Deckt alle 37 Endpunkte mit JSON-Rumpf ab;
#: ``test_endpunktliste.py`` prueft die Vollstaendigkeit gegen die Routen.
RUMPF: dict[str, Callable[[Holer], dict[str, Any]]] = {
    "POST /api/v1/mandants/{mandant_id}/users": _rumpf_mandant_zuordnen,
    "PATCH /api/v1/mandants/{mandant_id}": _rumpf_mandant_aendern,
    "POST /api/v1/mandants/{mandant_id}/cleanup": _rumpf_aufraeumen,
    "POST /api/v1/mandants/{mandant_id}/accounts": _rumpf_konto_anlegen,
    "PATCH /api/v1/mandants/{mandant_id}/accounts/{account_id}": _rumpf_konto_aendern,
    "PUT /api/v1/mandants/{mandant_id}/accounts/{account_id}/column-mapping": _rumpf_spaltenzuordnung,
    "POST /api/v1/mandants/{mandant_id}/accounts/{account_id}/excluded-identifiers": _rumpf_kennung_ausschliessen,
    "POST /api/v1/mandants/{mandant_id}/partners": _rumpf_partner_anlegen,
    "PATCH /api/v1/mandants/{mandant_id}/partners/{partner_id}": _rumpf_partner_aendern,
    "POST /api/v1/mandants/{mandant_id}/partners/{partner_id}/ibans": _rumpf_iban,
    "POST /api/v1/mandants/{mandant_id}/partners/{partner_id}/ibans/preview": _rumpf_iban,
    "POST /api/v1/mandants/{mandant_id}/partners/{partner_id}/accounts": _rumpf_partnerkonto,
    "POST /api/v1/mandants/{mandant_id}/partners/{partner_id}/accounts/preview": _rumpf_partnerkonto,
    "POST /api/v1/mandants/{mandant_id}/partners/{partner_id}/names": _rumpf_partnername,
    "POST /api/v1/mandants/{mandant_id}/partners/merge": _rumpf_verschmelzen,
    "POST /api/v1/mandants/{mandant_id}/partners/{partner_id}/services": _rumpf_leistung_anlegen,
    "PATCH /api/v1/mandants/{mandant_id}/services/{service_id}": _rumpf_leistung_aendern,
    "POST /api/v1/mandants/{mandant_id}/services/{service_id}/matchers": _rumpf_matcher,
    "POST /api/v1/mandants/{mandant_id}/services/{service_id}/matchers/preview": _rumpf_matcher,
    "PATCH /api/v1/mandants/{mandant_id}/services/{service_id}/matchers/{matcher_id}": _rumpf_matcher_aendern,
    "POST /api/v1/mandants/{mandant_id}/settings/service-keywords": _rumpf_schlagwort,
    "PATCH /api/v1/mandants/{mandant_id}/settings/service-keywords/{keyword_id}": _rumpf_schlagwort_aendern,
    "POST /api/v1/mandants/{mandant_id}/service-groups": _rumpf_gruppe_anlegen,
    "PATCH /api/v1/mandants/{mandant_id}/service-groups/{group_id}": _rumpf_gruppe_aendern,
    "DELETE /api/v1/mandants/{mandant_id}/service-groups/{group_id}": _rumpf_gruppe_loeschen,
    "POST /api/v1/mandants/{mandant_id}/services/{service_id}/group-assignment": _rumpf_gruppenzuordnung,
    "POST /api/v1/mandants/{mandant_id}/review/unidentified-groups/resolve": _rumpf_gruppe_aufloesen,
    "POST /api/v1/mandants/{mandant_id}/review/{item_id}/adjust": _rumpf_review_anpassen,
    "POST /api/v1/mandants/{mandant_id}/review/{item_id}/reassign": _rumpf_review_umhaengen,
    "POST /api/v1/mandants/{mandant_id}/review/{item_id}/new-partner": _rumpf_review_neuer_partner,
    "POST /api/v1/mandants/{mandant_id}/journal/bulk-assign": _rumpf_sammelzuordnung,
    "POST /api/v1/mandants/{mandant_id}/journal/{line_id}/assign-service": _rumpf_leistung_zuordnen,
    "PUT /api/v1/mandants/{mandant_id}/services/{service_id}/forecast-rule": _rumpf_prognoseregel,
    "POST /api/v1/mandants/{mandant_id}/forecast/planned-items": _rumpf_planposten_anlegen,
    "PATCH /api/v1/mandants/{mandant_id}/forecast/planned-items/{item_id}": _rumpf_planposten_aendern,
    "POST /api/v1/mandants/{mandant_id}/forecast/snapshots": _rumpf_momentaufnahme,
    "POST /api/v1/mandants/{mandant_id}/settings/tests/service-amount-consistency/lines/{line_id}/ok": _rumpf_betragspruefung,
}


def rumpfkennungen(endpunkt: Endpunkt) -> tuple[str, ...]:
    """Welche mandantengebundenen Kennungen der Rumpf dieses Endpunkts traegt.

    Ermittelt durch einen Probelauf des Rumpfbauers mit einem mitschreibenden Holer.
    Eine handgeschriebene Liste waere nach der ersten Schema-Aenderung falsch — und
    zwar still, weil ein fehlendes Feld einfach eine Sonde weniger bedeutet.

    Felder ohne Mandantenbindung (siehe ``OHNE_MANDANTENBINDUNG``) fallen heraus: Bei
    ihnen gibt es keine „fremde" Kennung, die man einsetzen koennte.
    """
    bauer = RUMPF.get(endpunkt.name)
    if bauer is None:
        return ()
    gesehen: list[str] = []

    def merke(feld: str) -> str:
        """Schreibt das abgefragte Feld mit und gibt eine wegwerfbare Kennung zurueck."""
        gesehen.append(feld)
        return str(uuid4())

    bauer(merke)
    return tuple(
        feld
        for feld in dict.fromkeys(gesehen)
        if quelle(endpunkt, feld) not in OHNE_MANDANTENBINDUNG
    )


# ─── Die Anfrage stellen ─────────────────────────────────────────────────────


async def stelle(
    client: AsyncClient,
    endpunkt: Endpunkt,
    *,
    kopf: dict[str, str],
    mandant_id: UUID | str,
    kennungen: dict[str, str],
    rumpf: dict[str, Any] | None = None,
) -> Response:
    """Setzt die Anfrage zusammen und schickt sie ab.

    ``kennungen`` enthaelt die Pfadparameter ausser ``mandant_id``; welche das sind,
    sagt ``endpunkt.kennungen``. Fehlt einer, schlaegt ``str.format`` fehl — laut und
    an der richtigen Stelle, statt spaeter als raetselhaftes 404.

    Dateiendpunkte bekommen die CSV aus ``CSV_INHALT`` statt eines JSON-Rumpfes. Mit
    ``json=`` waere die Antwort ein 422, und ein 422 ist keine Aussage ueber die
    Mandantentrennung.
    """
    pfad = endpunkt.pfad.format(mandant_id=mandant_id, **kennungen)
    query = {name: QUERYWERTE[name] for name in endpunkt.pflicht_query}

    if endpunkt.rumpfart == "multipart":
        feld = "files" if endpunkt.pfad.endswith("/imports") else "file"
        return await client.request(
            endpunkt.methode,
            pfad,
            headers=kopf,
            params=query,
            files=[(feld, ("sonde.csv", CSV_INHALT, "text/csv"))],
        )

    return await client.request(
        endpunkt.methode,
        pfad,
        headers=kopf,
        params=query,
        json=rumpf,
    )


# ─── Akteur und Rumpf fuer eine Sonde ────────────────────────────────────────

#: Rollen, fuer die es einen Akteur gibt, dessen Mandantenzuordnung beschraenkt ist.
#:
#: ``admin`` fehlt mit Absicht: Nach ADR-001 umgeht ein Admin die Mandantenpruefung.
#: Fuer die fuenf Endpunkte, die ``admin`` verlangen, gibt es deshalb keinen Akteur,
#: der rollenmaessig darf und mandantenmaessig beschraenkt ist — sie stehen in der
#: Ausnahmeliste von ``test_aeussere_schicht.py``.
BESCHRAENKTE_AKTEURE = {"viewer", "accountant", "mandant_admin"}


def akteur(pruefstand: Pruefstand, endpunkt: Endpunkt) -> User:
    """Der Nutzer, mit dem dieser Endpunkt zu sondieren ist.

    Gewaehlt wird der **schwaechste** Nutzer, dessen Rolle fuer den Endpunkt reicht und
    der nur zu Mandant A gehoert. Der Grund ist die Beweiskraft: Reicht die Rolle
    nicht, kommt das 403 aus ``require_role`` und sagt nichts ueber die
    Mandantentrennung.

    Wirft ``AssertionError`` bei ``admin`` — dieser Fall gehoert in die Ausnahmeliste
    und darf nicht stillschweigend mit einem Admin-Token gefahren werden, der ohnehin
    ueberall hindarf.
    """
    assert endpunkt.mindestrolle in BESCHRAENKTE_AKTEURE, (
        f"{endpunkt.name} verlangt die Rolle '{endpunkt.mindestrolle}'. Dafuer gibt es "
        f"keinen mandantenbeschraenkten Akteur (ADR-001). Der Endpunkt gehoert in die "
        f"Ausnahmeliste, nicht in diese Sonde."
    )
    if endpunkt.mindestrolle == "mandant_admin":
        return pruefstand.mandant_admin_a
    return pruefstand.a.nutzer


def baue_rumpf(
    endpunkt: Endpunkt,
    seite: Seite,
    *,
    fremd: Seite | None = None,
    feld: str | None = None,
) -> dict[str, Any] | None:
    """Der Rumpf fuer diesen Endpunkt, mit Kennungen aus ``seite``.

    Sind ``fremd`` und ``feld`` gesetzt, kommt **genau dieses eine** Feld aus der
    fremden Seite und alle uebrigen aus ``seite`` — das ist Sonde 3. Nur ein Feld auf
    einmal, weil sonst nicht zu erkennen waere, welche Pruefung gegriffen hat.

    Gibt ``None`` zurueck, wenn der Endpunkt keinen JSON-Rumpf hat.
    """
    bauer = RUMPF.get(endpunkt.name)
    if bauer is None:
        return None

    def hole(name: str) -> str:
        """Liefert die Kennung — aus der fremden Seite, wenn dieses Feld gemeint ist."""
        if fremd is not None and name == feld:
            return loese_auf(endpunkt, name, fremd)
        return loese_auf(endpunkt, name, seite)

    return bauer(hole)


def pfadkennungen(
    endpunkt: Endpunkt,
    seite: Seite,
    *,
    fremd: Seite | None = None,
    feld: str | None = None,
) -> dict[str, str]:
    """Die Pfadparameter ausser ``mandant_id``, aus ``seite``.

    Wie ``baue_rumpf``: Sind ``fremd`` und ``feld`` gesetzt, kommt genau dieser eine
    Pfadparameter aus der fremden Seite. Das ist Sonde 2.
    """
    ergebnis: dict[str, str] = {}
    for name in endpunkt.kennungen:
        if fremd is not None and name == feld:
            ergebnis[name] = loese_auf(endpunkt, name, fremd)
        else:
            ergebnis[name] = loese_auf(endpunkt, name, seite)
    return ergebnis


def angreifbare_pfadkennungen(endpunkt: Endpunkt) -> tuple[str, ...]:
    """Die Pfadparameter, bei denen ein Austausch gegen B etwas belegen kann.

    ``user_id`` fliegt heraus: Nutzer sind global, es gibt keinen fremden. Was dort zu
    pruefen ist, prueft Stufe 2.
    """
    return tuple(
        name
        for name in endpunkt.kennungen
        if quelle(endpunkt, name) not in OHNE_MANDANTENBINDUNG
    )


# ─── Was das Schema hergibt ──────────────────────────────────────────────────


def _rumpfschema(endpunkt: Endpunkt) -> Any | None:
    """Das Pydantic-Modell des Rumpfes dieses Endpunkts, oder ``None``.

    Geholt aus der registrierten Route, nicht aus einem Import: So bleibt es dieselbe
    Quelle, aus der auch die Endpunktliste kommt.
    """
    from app.main import app

    for route in app.routes:
        if not isinstance(route, APIRoute) or route.body_field is None:
            continue
        if route.path != endpunkt.pfad:
            continue
        if endpunkt.methode not in route.methods:
            continue
        return route.body_field.field_info.annotation
    return None


def kennungsfelder_im_schema(endpunkt: Endpunkt) -> tuple[str, ...]:
    """Jedes Feld des Rumpfschemas, dessen Typ eine ``UUID`` enthaelt — auch verschachtelt.

    Warum das noetig ist, obwohl ``rumpfkennungen()`` schon eine Liste liefert: Die
    kommt aus den **Rumpfbauern**. Sie ist damit gegen Abweichungen zwischen Bauer und
    Sonde gefeit, aber nicht gegen ein Feld, das ins **Schema** kommt und das kein
    Bauer je gesehen hat. Das ist derselbe Fehler wie eine abgeschriebene
    Endpunktliste, eine Ebene tiefer: Wer ``AdjustReviewRequest`` ein
    ``partner_id`` hinzufuegt, hat keine Sonde weniger — er hat eine, die es nie gab.

    ``test_endpunktliste.py`` haelt beide Listen gegeneinander.

    Verschachtelte Modelle werden mitgelesen und mit ``[]`` im Pfad benannt, etwa
    ``splits[].service_id``. Listen von UUIDs (``item_ids: list[UUID]``) zaehlen als
    das Feld selbst.
    """
    schema = _rumpfschema(endpunkt)
    if schema is None:
        return ()
    return tuple(_uuid_felder(schema))


def _uuid_felder(modell: Any, vorsatz: str = "", tiefe: int = 0) -> list[str]:
    """Rekursionsschritt fuer ``kennungsfelder_im_schema``.

    ``tiefe`` begrenzt den Abstieg. Die Schemata sind flach (hoechstens ein
    verschachteltes Modell), und eine Begrenzung ist billiger als die Ueberlegung, ob
    ein Modell sich selbst enthalten kann.
    """
    if tiefe > 3:
        return []
    felder = getattr(modell, "model_fields", None)
    if felder is None:
        return []

    treffer: list[str] = []
    for name, feld in felder.items():
        bestandteile = _typbestandteile(feld.annotation)
        if any(teil is UUID for teil in bestandteile):
            treffer.append(f"{vorsatz}{name}")
        for teil in bestandteile:
            if hasattr(teil, "model_fields"):
                treffer.extend(_uuid_felder(teil, f"{vorsatz}{name}[].", tiefe + 1))
    return treffer


def _typbestandteile(annotation: Any) -> list[Any]:
    """Der Typ selbst und alles, was in ihm steckt — ``list[X] | None`` ergibt X.

    Ohne dieses Auseinandernehmen wuerde ``list[UUID] | None`` nicht als
    Kennungsfeld erkannt, und ``list[ServiceSplitEntry] | None`` nicht als
    verschachteltes Modell.
    """
    teile = [annotation]
    offen = list(get_args(annotation))
    while offen:
        teil = offen.pop()
        teile.append(teil)
        offen.extend(get_args(teil))
    return teile
