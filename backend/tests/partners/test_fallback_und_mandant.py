"""Befund A1-4, praktisch: Der spaete Mandantenfilter verdraengt den Fallback.

Was der Befund sagte und was er nicht sagte
-------------------------------------------
A1-4 nennt vier Funktionen in ``app/partners/service.py``, die Buchungszeilen **ohne**
Mandantenfilter laden und danach in Python sieben. Der Befund stuft sie als „korrekt,
aber auf fragile Weise" ein: Das Risiko sei die naechste Aenderung.

Beim Umsetzen von Stufe 5 zeigte sich, dass die Reihenfolge schon heute das Ergebnis
aendert. Die Funktionen suchen in zwei Anlaeufen:

```python
lines = <exakte Uebereinstimmung>
if not lines:
    lines = <ILIKE-Teiltreffer>        # Fallback
lines = [ln for ln in lines if ...]    # Mandantenfilter, danach
```

Die Entscheidung `if not lines` faellt **vor** dem Filter. Findet der exakte Anlauf
also Zeilen, die einem **anderen** Mandanten gehoeren, gilt er als erfolgreich, der
Fallback wird uebersprungen — und der Filter raeumt danach alles weg. Der eigene
Mandant sieht eine leere Vorschau, obwohl der Fallback in seinen eigenen Daten etwas
gefunden haette.

Das ist kein Datenabfluss: Zu sehen bekommt niemand etwas Fremdes. Es ist die andere
Richtung — fremde Daten bestimmen, was der eigene Mandant **nicht** sieht.

Wie der Test das herstellt
--------------------------
========================  ==================================  ====================
Mandant                   ``partner_iban_raw`` der Buchung     exakt / Teiltreffer
Mandant A (fremd)         ``DE11...`` — genau die gesuchte      exakt
Mandant B (eigener)       ``VOR DE11... NACH`` — eingebettet    nur Teiltreffer
========================  ==================================  ====================

Aus Sicht von B: Der exakte Anlauf findet A's Zeile, der Fallback entfaellt, der Filter
loescht A's Zeile — Ergebnis leer. Mit dem Filter **in** der Query findet der exakte
Anlauf fuer B nichts, der Fallback laeuft, und B sieht seine eigene Zeile.

Gegen den unbehobenen Stand geprueft: Der Test schlaegt dort mit „0 Zeilen" fehl.
"""

from decimal import Decimal

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.imports.models import JournalLine, utcnow
from tests.conftest import AnmeldeHelfer, MandantWelt, ZweiMandanten

#: Die gesuchte IBAN. Bewusst eine dritte, die keiner der beiden Mandanten als
#: Partner-IBAN registriert hat — sonst wuerde das Anlegen an ADR-008 scheitern.
GESUCHTE_IBAN = "DE11500105170648489890"


async def _zeile(
    session: AsyncSession, welt: MandantWelt, iban_roh: str, text: str
) -> JournalLine:
    """Legt eine Buchungszeile ohne Partner mit dieser Roh-IBAN an.

    Ohne Partner, damit sie in der Vorschau auftaucht: ``preview_iban`` zeigt gerade
    die Zeilen, die **nicht** zum angefragten Partner gehoeren.
    """
    zeile = JournalLine(
        account_id=welt.konto.id,
        import_run_id=welt.import_lauf.id,
        partner_id=None,
        valuta_date="2026-03-01",
        booking_date="2026-03-01",
        amount=Decimal("-33.00"),
        currency="EUR",
        text=text,
        partner_name_raw="Unbekannt",
        partner_iban_raw=iban_roh,
        created_at=utcnow(),
    )
    session.add(zeile)
    await session.commit()
    await session.refresh(zeile)
    return zeile


async def test_fremde_zeile_verdraengt_den_eigenen_fallback_nicht(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """B sieht seinen Teiltreffer, obwohl A die IBAN exakt traegt.

    Der Kern des Tests ist die Reihenfolge, nicht die Trennung: Beide Zeilen gehoeren
    dorthin, wo sie liegen, und keine wird sichtbar, die es nicht sein soll. Geprueft
    wird, dass A's Zeile den Fallback von B nicht verschluckt.
    """
    await _zeile(db_session, zwei_mandanten.a, GESUCHTE_IBAN, "Zeile von A")
    eigene = await _zeile(
        db_session,
        zwei_mandanten.b,
        f"VOR{GESUCHTE_IBAN}NACH",
        "Zeile von B",
    )

    kopf = await anmelden(zwei_mandanten.nutzer_b, zwei_mandanten.b)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.b.id}"
        f"/partners/{zwei_mandanten.b.partner.id}/ibans/preview",
        headers=kopf,
        json={"iban": GESUCHTE_IBAN},
    )
    assert antwort.status_code == 200, antwort.text
    daten = antwort.json()

    kennungen = {zeile["journal_line_id"] for zeile in daten["matched_lines"]}
    assert str(eigene.id) in kennungen, (
        "B sieht seine eigene Teiltreffer-Zeile nicht. Der exakte Anlauf hat die Zeile "
        "von Mandant A gefunden, damit den Fallback uebersprungen, und der spaete "
        "Mandantenfilter hat A's Zeile danach entfernt — uebrig bleibt nichts. "
        f"Gesehen: {daten['matched_lines']}"
    )


async def test_die_vorschau_zeigt_keine_fremden_zeilen(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Die Gegenrichtung: A's Zeile darf in B's Vorschau nicht erscheinen.

    Ohne diese Zusicherung koennte der Test oben auch von einer Fassung erfuellt
    werden, die den Mandantenfilter einfach weglaesst — dann saehe B beide Zeilen und
    „seine eigene ist dabei" waere weiterhin wahr.
    """
    fremde = await _zeile(db_session, zwei_mandanten.a, GESUCHTE_IBAN, "Zeile von A")
    await _zeile(db_session, zwei_mandanten.b, f"VOR{GESUCHTE_IBAN}NACH", "Zeile von B")

    kopf = await anmelden(zwei_mandanten.nutzer_b, zwei_mandanten.b)

    antwort = await client.post(
        f"/api/v1/mandants/{zwei_mandanten.b.id}"
        f"/partners/{zwei_mandanten.b.partner.id}/ibans/preview",
        headers=kopf,
        json={"iban": GESUCHTE_IBAN},
    )
    assert antwort.status_code == 200, antwort.text

    kennungen = {zeile["journal_line_id"] for zeile in antwort.json()["matched_lines"]}
    assert (
        str(fremde.id) not in kennungen
    ), "B sieht eine Buchungszeile von Mandant A in der IBAN-Vorschau."
