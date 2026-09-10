"""Gemeinsame Pruefumgebung mit zwei Mandanten — Stufe 0 des Mandantenfaehigkeitsplans.

Warum dieses Modul existiert
----------------------------
Die Entwicklungs- und Testdatenbanken hatten bisher **einen** Mandanten. Damit ist
alles, was zwischen Mandanten schiefgehen kann, unbeobachtbar: Eine Query, die den
Mandantenfilter vergisst, liefert bei einem Mandanten genau dasselbe Ergebnis wie eine,
die ihn setzt. Beide in Etappe 1 des Code-Reviews gefundenen Lecks waren von dieser
Art — real, ausnutzbar, und trotz 452 gruener Tests unentdeckt.

Dieses Modul stellt deshalb eine Welt mit **zwei** Mandanten bereit, in der jeder
Mandantenfehler einen sichtbaren Unterschied macht. Siehe
``docs/mandantenfaehigkeit-plan.md``, Stufe 0.

Was die Welt absichtlich gleich benennt
---------------------------------------
Mandant A und Mandant B haben einen Partner **gleichen Namens** und darunter eine
Leistung **gleichen Namens**. Das ist keine Bequemlichkeit, sondern der Kern der
Pruefung: Eine Suche, die nach dem Namen filtert und den Mandanten vergisst, findet
zwei Treffer statt einem und faellt auf. Mit unterschiedlichen Namen wuerde derselbe
Fehler unbemerkt bleiben.

Die Datenbank laesst das zu — ``partners`` ist auf ``(mandant_id, name)`` eindeutig,
``services`` auf ``(partner_id, name)``.

Was die Welt absichtlich *nicht* gleich benennt
----------------------------------------------
Die IBANs. Nach ADR-008 ist eine IBAN ueber alle Mandanten hinweg eindeutig; zwei
Mandanten mit derselben IBAN sind deshalb kein Nebenschauplatz, sondern ein eigener
Befund (M13/A1-3) mit eigenen Tests in ``tests/imports/test_tenancy_iban_registration.py``.
Diese Fixture haelt sich daraus heraus und gibt jedem Mandanten seine eigene IBAN.

Verhaeltnis zu den Fixtures der einzelnen Testmodule
----------------------------------------------------
``tests/auth``, ``tests/tenants``, ``tests/partners``, ``tests/imports`` und
``tests/journal`` bringen je eine eigene Kopie von ``setup_db``, ``db_session`` und
``client`` mit — sechs Kopien derselben acht Zeilen. Diese Datei ist die kanonische
Kopie: Sie gilt fuer alle Tests, die keine eigene mitbringen.

Wo ein Modul dieselben Namen selbst definiert, gewinnt das Modul (so loest pytest
Fixtures auf: von der Testdatei nach oben, der erste Treffer zaehlt). Bestehende Tests
laufen deshalb unveraendert weiter, jeder auf seiner eigenen Engine.

Wichtig fuer das Verstaendnis: ``zwei_mandanten`` haengt an ``db_session``, und *dieser*
Name wird aus Sicht der **aufrufenden Testdatei** aufgeloest, nicht aus Sicht dieser
Datei. Ein Test in ``tests/imports/`` bekommt die Fixture also auf der Engine von
``tests/imports`` — genau richtig, denn dort liegen auch seine uebrigen Daten. Die
Hilfsfunktionen unten sind aus demselben Grund gewoehnliche Funktionen mit einem
``session``-Parameter und keine Fixtures: So sind sie von der Engine unabhaengig.

Das Zusammenlegen der sechs Kopien ist **nicht** Teil von Stufe 0 — es beruehrt jede
Testdatei im Projekt und gehoert in einen eigenen Schritt.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import MandantUser, User, UserRole
from app.auth.security import hash_password
from app.imports.models import ImportRun, ImportStatus, JournalLine, JournalLineSplit
from app.main import app
from app.partners.models import Partner, PartnerAccount, PartnerIban, PartnerName
from app.services.models import (
    KeywordTargetType,
    Service,
    ServiceGroup,
    ServiceGroupSection,
    ServiceMatcher,
    ServiceMatcherType,
    ServiceType,
    ServiceTypeKeyword,
)
from app.tenants.models import Account, ColumnMappingConfig, Mandant

# Alle Testnutzer teilen dasselbe Passwort — die Tests pruefen Mandantentrennung,
# nicht Passwortstaerke. Dieselbe Zeichenkette benutzen die Fixtures der Testmodule.
PASSWORT = "password123"

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


def utcnow() -> datetime:
    """Aktueller Zeitpunkt in UTC.

    Die Modelle speichern naive Zeitstempel; hier bleibt die Zeitzone dran, weil die
    bestehenden Test-Hilfsfunktionen es genauso halten und SQLite beides annimmt.
    """
    return datetime.now(UTC)


# ─── Infrastruktur ───────────────────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True, scope="function")
async def setup_db() -> AsyncGenerator[None, None]:
    """Legt das Schema vor jedem Test an und raeumt es danach ab.

    Pro Test ein leeres Schema: Kein Test kann sich auf Daten eines anderen stuetzen,
    und keiner kann einen anderen verunreinigen.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Datenbanksitzung fuer den direkten Zugriff im Test.

    Es ist dieselbe Sitzung, die auch die Anwendung unter ``client`` benutzt. Deshalb
    sieht ein Test Aenderungen, die ein Endpunkt geschrieben hat, ohne neu zu laden —
    und kann pruefen, was ein *abgewiesener* Aufruf eben *nicht* geschrieben hat.
    """
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP-Client gegen die ASGI-App, ohne Netzwerk.

    ``get_session`` wird auf die Sitzung des Tests umgebogen, damit Test und Anwendung
    dieselbe Transaktion sehen.
    """
    from app.core.database import get_session

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        """Gibt der Anwendung die Sitzung des Tests statt einer eigenen."""
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ─── Bausteine ───────────────────────────────────────────────────────────────


async def erzeuge_mandant(session: AsyncSession, name: str) -> Mandant:
    """Legt einen aktiven Mandanten an."""
    jetzt = utcnow()
    mandant = Mandant(name=name, is_active=True, created_at=jetzt, updated_at=jetzt)
    session.add(mandant)
    await session.commit()
    await session.refresh(mandant)
    return mandant


async def erzeuge_nutzer(
    session: AsyncSession,
    email: str,
    rolle: UserRole = UserRole.accountant,
    *,
    aktiv: bool = True,
) -> User:
    """Legt einen Nutzer mit gesetztem Passwort an (also einen, der sich anmelden kann).

    Ein Nutzer ohne ``password_hash`` gilt als noch nicht eingeladen und wird von
    ``/auth/login`` mit 401 abgewiesen — fuer diesen Fall siehe
    ``tests/auth/conftest.py``, das ``password=None`` zulaesst.
    """
    nutzer = User(
        email=email.lower(),
        password_hash=hash_password(PASSWORT),
        role=rolle.value,
        is_active=aktiv,
    )
    session.add(nutzer)
    await session.commit()
    await session.refresh(nutzer)
    return nutzer


async def ordne_zu(
    session: AsyncSession, nutzer: User, mandant: Mandant
) -> MandantUser:
    """Verknuepft Nutzer und Mandanten — der Vorgang, um den es in diesem Plan geht.

    Genau diese Zeile in ``mandant_users`` entscheidet, auf welche Daten ein Nutzer
    zugreifen darf (``require_mandant_access``) und welche Mandanten ihm nach dem
    Anmelden zur Auswahl stehen (``AuthService._get_mandants_for_user``).
    """
    zuordnung = MandantUser(mandant_id=mandant.id, user_id=nutzer.id)
    session.add(zuordnung)
    await session.commit()
    return zuordnung


# ─── Die Welt eines Mandanten ────────────────────────────────────────────────


@dataclass(frozen=True)
class MandantWelt:
    """Ein vollstaendig bestueckter Mandant — Konto, Partner, Leistung, Buchungen.

    Die Kette ist absichtlich vollstaendig, weil die Mandantenbindung unterschiedlich
    tief haengt und ein Test alle Tiefen erreichen muss:

    ============================  ========================================
    ``mandant``                   die Wurzel
    ``konto``                     direkt gebunden (``accounts.mandant_id``)
    ``partner``                   direkt gebunden (``partners.mandant_id``)
    ``import_lauf``               direkt gebunden (``import_runs.mandant_id``)
    ``leistung``                  **transitiv** ueber ``partner_id``
    ``zeilen``                    **transitiv** ueber ``account_id``
    ``aufteilung``                **transitiv** ueber ``journal_line_id``/``service_id``
    ``partner_iban``              **transitiv** ueber ``partner_id``
    ``partner_konto``             **transitiv** ueber ``partner_id``
    ``partner_name``              **transitiv** ueber ``partner_id``
    ``matcher``                   **transitiv** ueber ``service_id``
    ``schlagwort``                direkt gebunden (``service_type_keywords.mandant_id``)
    ``gruppe``                    direkt gebunden (``service_groups.mandant_id``)
    ``spaltenzuordnung``          **transitiv** ueber ``account_id``
    ============================  ========================================

    Die Spaltenzuordnung ist aus einem Grund dabei, der beim Schreiben der Tests
    auffiel: Ohne sie antwortet ``GET .../column-mapping`` **immer** mit 404 — auch
    auf das eigene Konto. Ein Angriffstest gegen ein fremdes Konto haette dann
    ebenfalls 404 ergeben und waere gruen geblieben, ohne etwas zu belegen. Erst wenn
    beim fremden Konto tatsaechlich etwas zu holen waere, prueft der Test etwas.

    Die drei Partner-Kennungen gibt es, damit die Endpunkte mit einer **dritten**
    Kennung im Pfad pruefbar sind — ``DELETE .../partners/{partner_id}/ibans/{iban_id}``
    und seine Geschwister. Dort muessen zwei Dinge stimmen: dass der Partner zum
    Mandanten gehoert *und* dass das Kind zum Partner gehoert.

    Die drei transitiv gebundenen sind die interessanten: Sie tragen keine eigene
    ``mandant_id``, ihre Zugehoerigkeit haengt an einem Join oder an einer Pruefung im
    Service. Genau dort meldet ``check_tenancy.py`` die meisten offenen Punkte, und
    genau dort lagen die Lecks aus Etappe 1.
    """

    mandant: Mandant
    konto: Account
    partner: Partner
    leistung: Service
    import_lauf: ImportRun
    zeilen: tuple[JournalLine, ...]
    aufteilung: JournalLineSplit
    iban: str
    partner_iban: PartnerIban
    partner_konto: PartnerAccount
    partner_name: PartnerName
    matcher: ServiceMatcher
    schlagwort: ServiceTypeKeyword
    gruppe: ServiceGroup
    spaltenzuordnung: ColumnMappingConfig

    @property
    def id(self) -> UUID:
        """Die ``mandant_id`` — die Kennung, die in 76 Endpunktpfaden steht."""
        assert self.mandant.id is not None
        return self.mandant.id


# Partner- und Leistungsname sind fuer beide Mandanten gleich (siehe Modulkopf).
PARTNER_NAME = "Muster Handels GmbH"
LEISTUNG_NAME = "Wareneinkauf"
# Auch Muster, Schlagwort und Gruppenname sind in beiden Mandanten gleich — dieselbe
# Absicht wie beim Partnernamen. `service_type_keywords` und `service_groups` sind je
# Mandant eindeutig, `service_matchers` je Leistung; alle drei lassen das zu.
MATCHER_MUSTER = "Wareneinkauf"
SCHLAGWORT_MUSTER = "Lieferung"
GRUPPEN_NAME = "Materialaufwand"


async def erzeuge_mandant_welt(
    session: AsyncSession,
    name: str,
    *,
    urheber: User,
    iban: str,
    kontoname: str,
    blz: str,
    kontonummer: str,
) -> MandantWelt:
    """Baut einen Mandanten samt Konto, Partner, Leistung, Import und Buchungen.

    ``urheber`` wird nur als ``import_runs.user_id`` eingetragen — die Spalte ist
    pflichtig und haelt fest, wer importiert hat. Sie sagt **nichts** ueber
    Zugriffsrechte; die stehen ausschliesslich in ``mandant_users``. Deshalb darf hier
    auch ein Nutzer stehen, der dem Mandanten nicht zugeordnet ist.

    Die beiden Buchungszeilen sind ein Eingang und ein Ausgang, damit Summen- und
    Saldenpfade beide Vorzeichen sehen. Nur die Ausgangszeile ist einer Leistung
    zugeordnet; die Eingangszeile bleibt ohne Aufteilung, damit auch der unzugeordnete
    Fall vorkommt.
    """
    jetzt = utcnow()

    mandant = await erzeuge_mandant(session, name)

    konto = Account(
        mandant_id=mandant.id,
        name=kontoname,
        currency="EUR",
        opening_balance=Decimal("1000.00"),
        created_at=jetzt,
        updated_at=jetzt,
    )
    session.add(konto)

    partner = Partner(
        mandant_id=mandant.id,
        name=PARTNER_NAME,
        is_active=True,
        created_at=jetzt,
        updated_at=jetzt,
    )
    session.add(partner)
    await session.flush()

    partner_iban = PartnerIban(partner_id=partner.id, iban=iban, created_at=jetzt)
    session.add(partner_iban)

    # Kontonummer und BLZ sind nach ADR-008 global eindeutig (auf `(blz,
    # account_number)`), deshalb je Mandant ein eigenes Paar. Der Zusatzname ist
    # nur je Partner eindeutig und darf gleich lauten.
    partner_konto = PartnerAccount(
        partner_id=partner.id,
        blz=blz,
        account_number=kontonummer,
        created_at=jetzt,
    )
    session.add(partner_konto)

    partner_name = PartnerName(
        partner_id=partner.id, name=f"{PARTNER_NAME} (Zusatzname)", created_at=jetzt
    )
    session.add(partner_name)

    leistung = Service(
        partner_id=partner.id,
        name=LEISTUNG_NAME,
        service_type=ServiceType.supplier.value,
        tax_rate=Decimal("20.00"),
        created_at=jetzt,
        updated_at=jetzt,
    )
    session.add(leistung)

    spaltenzuordnung = ColumnMappingConfig(
        account_id=konto.id,
        valuta_date_col="Valuta",
        booking_date_col="Buchung",
        amount_col="Betrag",
        partner_iban_col="IBAN",
        partner_name_col="Empfaenger",
        description_col="Text",
    )
    session.add(spaltenzuordnung)

    matcher = ServiceMatcher(
        service_id=leistung.id,
        pattern=MATCHER_MUSTER,
        pattern_type=ServiceMatcherType.string.value,
        created_at=jetzt,
        updated_at=jetzt,
    )
    session.add(matcher)

    # `service_type_keywords.mandant_id` ist nullbar — ein Schlagwort ohne Mandanten
    # gilt global. Hier bewusst mandantengebunden, weil gerade die Trennung geprueft
    # wird; der globale Fall ist ein eigener Gegenstand.
    schlagwort = ServiceTypeKeyword(
        mandant_id=mandant.id,
        pattern=SCHLAGWORT_MUSTER,
        pattern_type=ServiceMatcherType.string.value,
        # Schlagwoerter zielen auf `KeywordTargetType`, nicht auf `ServiceType` —
        # sie erkennen nur Personengruppen, nicht jede Leistungsart.
        target_service_type=KeywordTargetType.employee.value,
        created_at=jetzt,
        updated_at=jetzt,
    )
    session.add(schlagwort)

    gruppe = ServiceGroup(
        mandant_id=mandant.id,
        section=ServiceGroupSection.expense.value,
        name=GRUPPEN_NAME,
        sort_order=0,
        created_at=jetzt,
        updated_at=jetzt,
    )
    session.add(gruppe)

    import_lauf = ImportRun(
        account_id=konto.id,
        mandant_id=mandant.id,
        user_id=urheber.id,
        filename=f"{name}.csv",
        row_count=2,
        status=ImportStatus.completed.value,
        created_at=jetzt,
        completed_at=jetzt,
    )
    session.add(import_lauf)
    await session.flush()

    eingang = JournalLine(
        account_id=konto.id,
        import_run_id=import_lauf.id,
        partner_id=partner.id,
        valuta_date="2026-01-15",
        booking_date="2026-01-15",
        amount=Decimal("500.00"),
        currency="EUR",
        text=f"Eingang {name}",
        partner_name_raw=PARTNER_NAME,
        partner_iban_raw=iban,
        created_at=jetzt,
    )
    ausgang = JournalLine(
        account_id=konto.id,
        import_run_id=import_lauf.id,
        partner_id=partner.id,
        valuta_date="2026-01-20",
        booking_date="2026-01-20",
        amount=Decimal("-120.00"),
        currency="EUR",
        text=f"Ausgang {name}",
        partner_name_raw=PARTNER_NAME,
        partner_iban_raw=iban,
        created_at=jetzt,
    )
    session.add(eingang)
    session.add(ausgang)
    await session.flush()

    aufteilung = JournalLineSplit(
        journal_line_id=ausgang.id,
        service_id=leistung.id,
        amount=Decimal("-120.00"),
        assignment_mode="auto",
        amount_consistency_ok=True,
        created_at=jetzt,
    )
    session.add(aufteilung)

    await session.commit()
    for objekt in (
        konto,
        partner,
        leistung,
        import_lauf,
        eingang,
        ausgang,
        aufteilung,
        partner_iban,
        partner_konto,
        partner_name,
        matcher,
        schlagwort,
        gruppe,
        spaltenzuordnung,
    ):
        await session.refresh(objekt)

    return MandantWelt(
        mandant=mandant,
        konto=konto,
        partner=partner,
        leistung=leistung,
        import_lauf=import_lauf,
        zeilen=(eingang, ausgang),
        aufteilung=aufteilung,
        iban=iban,
        partner_iban=partner_iban,
        partner_konto=partner_konto,
        partner_name=partner_name,
        matcher=matcher,
        schlagwort=schlagwort,
        gruppe=gruppe,
        spaltenzuordnung=spaltenzuordnung,
    )


# ─── Die Welt mit zwei Mandanten ─────────────────────────────────────────────


@dataclass(frozen=True)
class ZweiMandanten:
    """Zwei bestueckte Mandanten und fuenf Nutzer, die jeder einen Fall abdecken.

    ==================  ==============  ==========================================
    Nutzer              Zuordnung       welcher Fall damit pruefbar wird
    ==================  ==============  ==========================================
    ``nutzer_a``        nur A           der Normalfall: fremde Daten muessen 403/404 ergeben
    ``nutzer_b``        nur B           die Gegenrichtung — sonst prueft man nur eine Seite
    ``nutzer_beide``    A **und** B     der Fall, den es bisher nie gab: Auswahl beim
                                        Anmelden, Wechsel, und die Frage aus M10, ob ein
                                        fuer A gewaehltes Token auf B wirkt
    ``nutzer_ohne``     keine           die Sackgasse aus M6 — jeder neu eingeladene
                                        Nutzer ist in diesem Zustand
    ``mandant_admin_a`` nur A           Entscheidung E2: darf Nutzer *seinem* Mandanten
                                        zuordnen, aber nicht Mandant B
    ``admin``           keine           volle Reichweite laut ADR-001, obwohl ohne
                                        Zuordnung; deckt M4 und M5 auf
    ==================  ==============  ==========================================

    ``nutzer_ohne`` ist bewusst ``viewer`` und nicht ``accountant``: Die Sackgasse aus
    M6 trifft die schwaechste Rolle zuerst, weil sie am haeufigsten neu eingeladen wird.
    """

    a: MandantWelt
    b: MandantWelt
    nutzer_a: User
    nutzer_b: User
    nutzer_beide: User
    nutzer_ohne: User
    mandant_admin_a: User
    admin: User


# Zwei verschiedene IBANs — siehe Modulkopf zu ADR-008.
IBAN_A = "DE89370400440532013000"
IBAN_B = "AT611904300234573201"


@pytest_asyncio.fixture
async def zwei_mandanten(db_session: AsyncSession) -> ZweiMandanten:
    """Die gemeinsame Pruefumgebung: zwei Mandanten, fuenf Nutzer.

    Reihenfolge mit Absicht: Erst der Admin, weil ``import_runs.user_id`` einen
    existierenden Nutzer braucht, bevor die Welten gebaut werden koennen.
    """
    admin = await erzeuge_nutzer(db_session, "admin@example.com", UserRole.admin)

    welt_a = await erzeuge_mandant_welt(
        db_session,
        "Mandant A",
        urheber=admin,
        iban=IBAN_A,
        kontoname="Konto A",
        blz="10000",
        kontonummer="1111111",
    )
    welt_b = await erzeuge_mandant_welt(
        db_session,
        "Mandant B",
        urheber=admin,
        iban=IBAN_B,
        kontoname="Konto B",
        blz="20000",
        kontonummer="2222222",
    )

    nutzer_a = await erzeuge_nutzer(db_session, "a@example.com", UserRole.accountant)
    nutzer_b = await erzeuge_nutzer(db_session, "b@example.com", UserRole.accountant)
    nutzer_beide = await erzeuge_nutzer(
        db_session, "beide@example.com", UserRole.accountant
    )
    nutzer_ohne = await erzeuge_nutzer(db_session, "ohne@example.com", UserRole.viewer)
    mandant_admin_a = await erzeuge_nutzer(
        db_session, "ma-a@example.com", UserRole.mandant_admin
    )

    await ordne_zu(db_session, nutzer_a, welt_a.mandant)
    await ordne_zu(db_session, nutzer_b, welt_b.mandant)
    await ordne_zu(db_session, nutzer_beide, welt_a.mandant)
    await ordne_zu(db_session, nutzer_beide, welt_b.mandant)
    await ordne_zu(db_session, mandant_admin_a, welt_a.mandant)
    # nutzer_ohne und admin bekommen absichtlich keine Zuordnung.

    return ZweiMandanten(
        a=welt_a,
        b=welt_b,
        nutzer_a=nutzer_a,
        nutzer_b=nutzer_b,
        nutzer_beide=nutzer_beide,
        nutzer_ohne=nutzer_ohne,
        mandant_admin_a=mandant_admin_a,
        admin=admin,
    )


# ─── Anmelden ────────────────────────────────────────────────────────────────

AnmeldeHelfer = Callable[..., Awaitable[dict[str, str]]]


@pytest_asyncio.fixture
async def anmelden(client: AsyncClient) -> AnmeldeHelfer:
    """Liefert eine Funktion ``anmelden(nutzer, mandant=None) -> Header``.

    Sie geht den echten Weg ueber ``/auth/login`` und — wenn noetig —
    ``/auth/select-mandant``, statt ein Token selbst zu bauen. Das ist der Punkt:
    Ein Test, der sich sein Token schnitzt, prueft die Auswahllogik nicht mit. Genau
    dort sitzen die Befunde M4, M5 und M9.

    ``mandant`` waehlt aus, welcher Mandant ins Token kommt. Bei genau einem Mandanten
    ist die Angabe unnoetig, weil ``login`` ihn schon einsetzt. Bei mehreren ist sie
    pflichtig — ohne sie bliebe das Token ohne ``mandant_id`` und jeder Aufruf danach
    liefe ins Leere.

    Wirft ``AssertionError``, sobald das Anmelden nicht klappt oder am Ende kein
    ``mandant_id`` im Token steht. Ein Test soll an der Stelle scheitern, an der etwas
    fehlt, und nicht erst drei Aufrufe spaeter an einem 401, das niemand erklaeren kann.
    """

    async def _anmelden(
        nutzer: User,
        mandant: Mandant | MandantWelt | None = None,
        *,
        mandant_erwartet: bool = True,
    ) -> dict[str, str]:
        """Meldet den Nutzer an und liefert den Authorization-Header.

        ``mandant_erwartet=False`` schaltet die Zusicherung ab — nur fuer Tests, die
        gerade den Zustand *ohne* Mandanten untersuchen wollen (Befund M6).
        """
        antwort = await client.post(
            "/api/v1/auth/login",
            json={"email": nutzer.email, "password": PASSWORT},
        )
        assert antwort.status_code == 200, (
            f"Anmelden von {nutzer.email} fehlgeschlagen: "
            f"{antwort.status_code} {antwort.text}"
        )
        daten = antwort.json()
        token = daten["access_token"]

        gewuenschte_id = _mandant_id(mandant)
        if gewuenschte_id is not None:
            antwort2 = await client.post(
                "/api/v1/auth/select-mandant",
                json={"mandant_id": str(gewuenschte_id)},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert antwort2.status_code == 200, (
                f"Mandantenauswahl fuer {nutzer.email} fehlgeschlagen: "
                f"{antwort2.status_code} {antwort2.text}"
            )
            token = antwort2.json()["access_token"]

        if mandant_erwartet:
            assert _token_mandant(token) is not None, (
                f"Das Token von {nutzer.email} hat keine mandant_id. Bei mehreren "
                f"Mandanten muss `mandant=` angegeben werden."
            )

        return {"Authorization": f"Bearer {token}"}

    return _anmelden


def _mandant_id(mandant: Mandant | MandantWelt | None) -> UUID | None:
    """Nimmt Mandant oder ``MandantWelt`` und gibt die ``mandant_id`` heraus."""
    if mandant is None:
        return None
    if isinstance(mandant, MandantWelt):
        return mandant.id
    return mandant.id


def _token_mandant(token: str) -> str | None:
    """Liest die ``mandant_id`` aus einem Token, ohne die Signatur zu pruefen.

    Nur fuer Zusicherungen im Test. Die Signatur hat die Anwendung schon geprueft, als
    sie das Token ausgegeben hat.
    """
    from app.auth.security import decode_access_token

    return decode_access_token(token).get("mandant_id")
