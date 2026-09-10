"""Legt einen zweiten Mandanten in der Entwicklungsdatenbank an — Stufe 0.

Warum
-----
Solange eine Datenbank nur **einen** Mandanten hat, ist die Mandantenauswahl nach dem
Anmelden von Hand nicht sichtbar und jeder Mandantenfehler unbeobachtbar: Eine Query
ohne Mandantenfilter liefert bei einem Mandanten dasselbe Ergebnis wie eine mit. Dieses
Skript schafft die zweite Haelfte, an der ein Unterschied entstehen kann — und, wenn es
sie schon gibt, die Zuordnung, die sie erreichbar macht.

Das Gegenstueck fuer die Tests ist die Fixture ``zwei_mandanten`` in
``tests/conftest.py``. Beide bauen absichtlich dieselbe Welt — ein Konto, ein Partner,
eine Leistung, ein Importlauf, zwei Buchungen —, damit ein Befund aus dem Test von Hand
nachvollziehbar ist und umgekehrt.

Aufruf
------
::

    python scripts/zweiter_mandant.py --trocken   # nur zeigen, was passieren wuerde
    python scripts/zweiter_mandant.py             # anlegen
    python scripts/zweiter_mandant.py --name "Zweite GmbH"

Das Skript ist **idempotent**: Ein zweiter Aufruf legt nichts doppelt an. Es fasst
ausserdem **keine bestehenden Daten an** — es fuegt nur hinzu. Der einzige Eingriff in
Bestehendes ist die Zuordnung vorhandener Nutzer zum neuen Mandanten, und genau die ist
der Zweck: Ohne sie sieht niemand eine Auswahl.

Beispieldaten nur fuer neue Mandanten
-------------------------------------
Gibt es den Mandanten unter diesem Namen **schon**, legt das Skript **keine**
Beispieldaten an und beschraenkt sich auf die Nutzerzuordnung. Grund: Ein vorhandener
Mandant kann echte Daten enthalten, und ein Entwicklungsskript hat dort nichts
einzufuegen. Nur ein vom Skript selbst neu angelegter Mandant wird bestueckt.

Damit deckt derselbe Aufruf beide Faelle ab, die in der Praxis auftreten:

* *Ich brauche einen zweiten Mandanten zum Ausprobieren* — Name existiert nicht, es
  entsteht einer mit Konto, Partner, Leistung und zwei Buchungen.
* *Es gibt schon einen zweiten Mandanten, aber niemand kann ihn auswaehlen* — Name
  existiert, es entsteht nur die fehlende Zuordnung. Genau dieser Zustand ist Befund
  M5: Ein Admin darf laut ``require_mandant_access`` auf jeden Mandanten zugreifen,
  bekommt von ``_get_mandants_for_user`` aber nur die **verknuepften** zur Auswahl.
  Ein Mandant ohne Zuordnung ist dadurch ueber die Oberflaeche unerreichbar, obwohl
  die Berechtigung reicht.

Was es *nicht* tut
------------------
Es legt keine neuen Anmeldenutzer mit Passwort an. Ein zweiter Nutzer zum Durchspielen
des Normalfalls (also eines Nicht-Admins) gehoert ueber die Nutzerverwaltung angelegt —
und dass das heute keine Mandanten zuordnen kann, ist Befund M7 und Gegenstand von
Stufe 2 des Plans.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

# Das Skript liegt in backend/scripts/, die App in backend/app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import select  # noqa: E402
from sqlmodel.ext.asyncio.session import AsyncSession  # noqa: E402

from app.auth.models import MandantUser, User  # noqa: E402
from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.imports.models import (  # noqa: E402
    ImportRun,
    ImportStatus,
    JournalLine,
    JournalLineSplit,
)
from app.partners.models import Partner, PartnerIban  # noqa: E402
from app.services.models import Service, ServiceType  # noqa: E402
from app.tenants.models import Account, Mandant  # noqa: E402

# Voreinstellungen. Die IBAN ist eine Testnummer und absichtlich eine andere als jede
# in der Fixture — nach ADR-008 ist eine IBAN ueber alle Mandanten hinweg eindeutig,
# eine Kollision wuerde also stillschweigend nichts anlegen.
STANDARD_NAME = "Zweite Muster GmbH"
IBAN = "AT483200000012345864"
PARTNER_NAME = "Muster Handels GmbH"
LEISTUNG_NAME = "Wareneinkauf"
KONTO_NAME = "Geschaeftskonto"


def utcnow() -> datetime:
    """Aktueller Zeitpunkt als naiver UTC-Wert — so speichern die Modelle."""
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class Bericht:
    """Sammelt, was das Skript getan hat, damit der Abschlussbericht nicht raet."""

    angelegt: list[str]
    vorhanden: list[str]

    def neu(self, was: str) -> None:
        """Vermerkt einen neu angelegten Datensatz."""
        self.angelegt.append(was)

    def schon_da(self, was: str) -> None:
        """Vermerkt einen Datensatz, den ein frueherer Lauf schon angelegt hat."""
        self.vorhanden.append(was)

    def ausgeben(self) -> None:
        """Gibt den Abschlussbericht aus — was entstand und was unveraendert blieb."""
        if self.angelegt:
            print("\nAngelegt:")
            for eintrag in self.angelegt:
                print(f"  + {eintrag}")
        else:
            print("\nAngelegt: nichts — alles war schon vorhanden.")

        if self.vorhanden:
            print("\nUnveraendert:")
            for eintrag in self.vorhanden:
                print(f"  = {eintrag}")


async def finde_mandant(session: AsyncSession, name: str) -> Mandant | None:
    """Sucht einen Mandanten am Namen — die Grundlage der Idempotenz.

    ``mandants.name`` ist nicht eindeutig; zwei Mandanten duerfen gleich heissen. Fuer
    ein Entwicklungsskript ist der Name trotzdem der richtige Schluessel, weil es
    keinen stabileren gibt, den ein Mensch beim zweiten Aufruf wieder eintippt.
    """
    treffer = await session.exec(select(Mandant).where(Mandant.name == name))
    return treffer.first()


async def lege_welt_an(
    session: AsyncSession, mandant: Mandant, urheber_id: UUID, bericht: Bericht
) -> None:
    """Bestueckt einen Mandanten mit Konto, Partner, Leistung, Importlauf, Buchungen.

    Jeder Schritt prueft zuerst, ob es das Objekt schon gibt. Ein zweiter Aufruf des
    Skripts laeuft deshalb durch, ohne etwas zu verdoppeln.

    ``urheber_id`` landet in ``import_runs.user_id``. Die Spalte haelt fest, wer
    importiert hat, und sagt nichts ueber Zugriffsrechte — die stehen ausschliesslich
    in ``mandant_users``.
    """
    jetzt = utcnow()

    # ── Konto ────────────────────────────────────────────────────────────────
    konto = (
        await session.exec(
            select(Account).where(
                Account.mandant_id == mandant.id, Account.name == KONTO_NAME
            )
        )
    ).first()
    if konto is None:
        konto = Account(
            mandant_id=mandant.id,
            name=KONTO_NAME,
            currency="EUR",
            opening_balance=Decimal("2500.00"),
            created_at=jetzt,
            updated_at=jetzt,
        )
        session.add(konto)
        await session.flush()
        bericht.neu(f"Konto '{KONTO_NAME}' (Anfangsbestand 2.500,00 EUR)")
    else:
        bericht.schon_da(f"Konto '{KONTO_NAME}'")

    # ── Partner ──────────────────────────────────────────────────────────────
    partner = (
        await session.exec(
            select(Partner).where(
                Partner.mandant_id == mandant.id, Partner.name == PARTNER_NAME
            )
        )
    ).first()
    if partner is None:
        partner = Partner(
            mandant_id=mandant.id,
            name=PARTNER_NAME,
            is_active=True,
            created_at=jetzt,
            updated_at=jetzt,
        )
        session.add(partner)
        await session.flush()
        bericht.neu(f"Partner '{PARTNER_NAME}'")
    else:
        bericht.schon_da(f"Partner '{PARTNER_NAME}'")

    # ── IBAN des Partners ────────────────────────────────────────────────────
    # ADR-008: global eindeutig. Gehoert die IBAN schon irgendwem, wird sie
    # uebersprungen — genau das stille Verhalten, das Befund M13/A1-3 beschreibt.
    iban_irgendwo = (
        await session.exec(select(PartnerIban).where(PartnerIban.iban == IBAN))
    ).first()
    if iban_irgendwo is None:
        session.add(
            PartnerIban(
                mandant_id=partner.mandant_id,
                partner_id=partner.id,
                iban=IBAN,
                created_at=jetzt,
            )
        )
        bericht.neu(f"IBAN {IBAN} fuer '{PARTNER_NAME}'")
    elif iban_irgendwo.partner_id == partner.id:
        bericht.schon_da(f"IBAN {IBAN}")
    else:
        bericht.schon_da(
            f"IBAN {IBAN} — gehoert bereits einem anderen Partner (ADR-008), "
            f"wird nicht vergeben"
        )

    # ── Leistung ─────────────────────────────────────────────────────────────
    leistung = (
        await session.exec(
            select(Service).where(
                Service.partner_id == partner.id, Service.name == LEISTUNG_NAME
            )
        )
    ).first()
    if leistung is None:
        leistung = Service(
            partner_id=partner.id,
            name=LEISTUNG_NAME,
            service_type=ServiceType.supplier.value,
            tax_rate=Decimal("20.00"),
            created_at=jetzt,
            updated_at=jetzt,
        )
        session.add(leistung)
        await session.flush()
        bericht.neu(f"Leistung '{LEISTUNG_NAME}' (20 % USt)")
    else:
        bericht.schon_da(f"Leistung '{LEISTUNG_NAME}'")

    # ── Importlauf ───────────────────────────────────────────────────────────
    dateiname = "stufe-0-beispieldaten.csv"
    lauf = (
        await session.exec(
            select(ImportRun).where(
                ImportRun.mandant_id == mandant.id, ImportRun.filename == dateiname
            )
        )
    ).first()
    if lauf is None:
        lauf = ImportRun(
            account_id=konto.id,
            mandant_id=mandant.id,
            user_id=urheber_id,
            filename=dateiname,
            row_count=2,
            status=ImportStatus.completed.value,
            created_at=jetzt,
            completed_at=jetzt,
        )
        session.add(lauf)
        await session.flush()
        bericht.neu(f"Importlauf '{dateiname}'")
    else:
        bericht.schon_da(f"Importlauf '{dateiname}'")
        return  # Buchungen haengen am Lauf und sind damit auch schon da.

    # ── Buchungen ────────────────────────────────────────────────────────────
    # Ein Eingang und ein Ausgang, damit Summen und Salden beide Vorzeichen sehen.
    eingang = JournalLine(
        account_id=konto.id,
        import_run_id=lauf.id,
        partner_id=partner.id,
        valuta_date="2026-02-03",
        booking_date="2026-02-03",
        amount=Decimal("1800.00"),
        currency="EUR",
        text="Kundenzahlung",
        partner_name_raw=PARTNER_NAME,
        partner_iban_raw=IBAN,
        created_at=jetzt,
    )
    ausgang = JournalLine(
        account_id=konto.id,
        import_run_id=lauf.id,
        partner_id=partner.id,
        valuta_date="2026-02-11",
        booking_date="2026-02-11",
        amount=Decimal("-430.50"),
        currency="EUR",
        text="Wareneinkauf",
        partner_name_raw=PARTNER_NAME,
        partner_iban_raw=IBAN,
        created_at=jetzt,
    )
    session.add(eingang)
    session.add(ausgang)
    await session.flush()

    session.add(
        JournalLineSplit(
            journal_line_id=ausgang.id,
            service_id=leistung.id,
            amount=Decimal("-430.50"),
            assignment_mode="auto",
            amount_consistency_ok=True,
            created_at=jetzt,
        )
    )
    bericht.neu(
        "2 Buchungen (+1.800,00 / -430,50 EUR), eine davon der Leistung zugeordnet"
    )


async def ordne_nutzer_zu(
    session: AsyncSession, mandant: Mandant, bericht: Bericht
) -> None:
    """Verknuepft alle aktiven Nutzer mit dem neuen Mandanten.

    Das ist der Schritt, der die Mandantenauswahl sichtbar macht: Erst wenn ein Nutzer
    zwei Zuordnungen hat, liefert ``/auth/login`` ihm eine Liste zur Wahl.

    Hinweis fuer den Admin: Bei Rolle ``admin`` bleibt ``requires_mandant_selection``
    trotzdem ``false`` — das ist Befund M4. Die Auswahlseite erscheint dennoch, weil
    ``MandantRequiredRoute`` im Frontend das fehlende ``mandant_id`` bemerkt und
    umleitet. Wer M4 von Hand sehen will, sieht ihn genau hier.
    """
    nutzer = list(
        (
            await session.exec(select(User).where(User.is_active == True))
        ).all()  # noqa: E712
    )
    if not nutzer:
        bericht.schon_da("keine aktiven Nutzer vorhanden — nichts zuzuordnen")
        return

    for n in nutzer:
        vorhanden = (
            await session.exec(
                select(MandantUser).where(
                    MandantUser.mandant_id == mandant.id,
                    MandantUser.user_id == n.id,
                )
            )
        ).first()
        if vorhanden is None:
            session.add(MandantUser(mandant_id=mandant.id, user_id=n.id))
            bericht.neu(f"Zuordnung {n.email} → '{mandant.name}'")
        else:
            bericht.schon_da(f"Zuordnung {n.email} → '{mandant.name}'")


async def zeige_lage(session: AsyncSession) -> None:
    """Gibt aus, welche Mandanten es gibt und wer zu wie vielen gehoert.

    Laeuft auch im Trockenlauf und ist dort der eigentliche Nutzen: Man sieht die
    Ausgangslage, bevor man etwas aendert.
    """
    mandanten = list((await session.exec(select(Mandant).order_by(Mandant.name))).all())
    print(f"\nMandanten ({len(mandanten)}):")
    for m in mandanten:
        zustand = "aktiv" if m.is_active else "deaktiviert"
        anzahl = len(
            (
                await session.exec(
                    select(MandantUser.user_id).where(MandantUser.mandant_id == m.id)
                )
            ).all()
        )
        print(f"  · {m.name:28} {zustand:12} {anzahl} Nutzer")

    nutzer = list((await session.exec(select(User).order_by(User.email))).all())
    print(f"\nNutzer ({len(nutzer)}):")
    for n in nutzer:
        zuordnungen = list(
            (
                await session.exec(
                    select(Mandant.name)
                    .join(MandantUser, Mandant.id == MandantUser.mandant_id)
                    .where(MandantUser.user_id == n.id)
                    .order_by(Mandant.name)
                )
            ).all()
        )
        if len(zuordnungen) > 1:
            auswahl = "→ Auswahl beim Anmelden"
        elif not zuordnungen:
            auswahl = "→ ohne Mandant (Befund M6)"
        else:
            auswahl = ""
        print(
            f"  · {n.email:34} {n.role:14} "
            f"{', '.join(zuordnungen) or '—':30} {auswahl}"
        )


async def main(name: str, trocken: bool) -> int:
    """Fuehrt den Lauf aus und gibt den Abschlussbericht aus.

    Rueckgabe ist der Exit-Code: 0 bei Erfolg, 1 wenn nichts angelegt werden konnte,
    weil kein Nutzer existiert, an dem ein Importlauf haengen koennte.
    """
    bericht = Bericht(angelegt=[], vorhanden=[])

    async with AsyncSessionLocal() as session:
        await zeige_lage(session)

        if trocken:
            vorhanden = await finde_mandant(session, name)
            print("\nTrockenlauf — es wird nichts geschrieben.")
            if vorhanden is None:
                print(
                    f"Ohne --trocken entstehen: Mandant '{name}' mit Konto, Partner, "
                    f"Leistung, Importlauf und zwei Buchungen; dazu die Zuordnung "
                    f"aller aktiven Nutzer zu diesem Mandanten."
                )
            else:
                print(
                    f"'{name}' gibt es schon. Ohne --trocken entsteht daher **nur** "
                    f"die fehlende Zuordnung der aktiven Nutzer — keine Beispieldaten, "
                    f"weil ein vorhandener Mandant echte Daten enthalten kann."
                )
            return 0

        urheber = (await session.exec(select(User).order_by(User.created_at))).first()
        if urheber is None:
            print(
                "\nFEHLER: Es gibt keinen Nutzer. `import_runs.user_id` ist pflichtig, "
                "also kann ohne Nutzer kein Importlauf angelegt werden. Zuerst einen "
                "Nutzer anlegen (Anwendung starten und Admin einrichten)."
            )
            return 1

        mandant = await finde_mandant(session, name)
        neu_angelegt = mandant is None
        if mandant is None:
            jetzt = utcnow()
            mandant = Mandant(
                name=name, is_active=True, created_at=jetzt, updated_at=jetzt
            )
            session.add(mandant)
            await session.flush()
            bericht.neu(f"Mandant '{name}'")
        else:
            bericht.schon_da(f"Mandant '{name}'")

        # Beispieldaten nur in einen selbst angelegten Mandanten — ein vorhandener
        # kann echte Daten enthalten (siehe Modulkopf).
        if neu_angelegt:
            await lege_welt_an(session, mandant, urheber.id, bericht)
        else:
            bericht.schon_da(
                f"'{name}' bestand bereits — keine Beispieldaten eingefuegt, "
                f"nur die Nutzerzuordnung wird ergaenzt"
            )

        await ordne_nutzer_zu(session, mandant, bericht)

        await session.commit()
        await zeige_lage(session)

    bericht.ausgeben()
    print(
        "\nNaechster Schritt: abmelden und neu anmelden — die Mandantenauswahl "
        "erscheint jetzt."
    )
    return 0


if __name__ == "__main__":
    zerleger = argparse.ArgumentParser(
        description=(
            "Legt einen zweiten Mandanten in der Entwicklungsdatenbank an. "
            "Idempotent — ein zweiter Aufruf verdoppelt nichts."
        )
    )
    zerleger.add_argument(
        "--name",
        default=STANDARD_NAME,
        help=f"Name des zweiten Mandanten (Vorgabe: '{STANDARD_NAME}')",
    )
    zerleger.add_argument(
        "--trocken",
        action="store_true",
        help="Nur die Lage zeigen und was passieren wuerde, nichts schreiben",
    )
    argumente = zerleger.parse_args()

    async def _lauf() -> int:
        """Fuehrt ``main`` aus und gibt die Verbindung in jedem Fall wieder frei."""
        try:
            return await main(argumente.name, argumente.trocken)
        finally:
            await engine.dispose()

    raise SystemExit(asyncio.run(_lauf()))
