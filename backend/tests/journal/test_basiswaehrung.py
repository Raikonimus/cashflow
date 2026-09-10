"""Befund A2-3: Die Basiswaehrung kommt aus den Konten, nicht aus einem Literal.

Was der Befund sagte
--------------------
``base_currency = "EUR"`` stand dreimal als Literal in ``app/journal/service.py``,
obwohl Konten ein eigenes ``currency`` fuehren. Ein Mandant mit einem Konto in CHF
bekam eine vollstaendig leere Auswertung: Alle seine Buchungen fielen unter
„ausgeschlossene Fremdwaehrung". Der Hinweis darauf waere erschienen, es waere also
nicht lautlos gewesen — aber auch nicht als Fehler erkennbar.

Der Befund war als **latent** eingestuft, weil beide Mandanten und alle 20.314
Buchungen der Entwicklungsdatenbank in Euro laufen. Latent heisst nicht harmlos: Der
erste Mandant mit einem Fremdwaehrungskonto haette eine leere Seite gesehen und keinen
Grund dafuer.

Wie der Test das herstellt
--------------------------
Mandant B bekommt ein Konto in CHF und Buchungen in CHF; Mandant A bleibt in Euro.
Damit steht die Ableitung unter Beweis, ohne dass eine Umrechnung ins Spiel kommt —
die es im System bewusst nicht gibt.

Gegen den unbehobenen Stand geprueft: Dort antwortet B mit ``currency: "EUR"`` und
``start_balance: "0.00"``, weil sein Konto als Fremdwaehrung ausgeschlossen wird.
"""

from decimal import Decimal

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.conftest import AnmeldeHelfer, ZweiMandanten


async def _auf_chf_umstellen(session: AsyncSession, welt) -> None:
    """Stellt Konto und Buchungen einer Welt auf CHF um.

    Beides muss umgestellt werden: Das Konto entscheidet ueber die Basiswaehrung, die
    Buchungen darueber, ob sie in die Rechnung eingehen. Nur eines von beiden zu
    aendern waere gerade der Fall „Fremdwaehrung ausgeschlossen" und wuerde die
    Ableitung nicht pruefen.
    """
    welt.konto.currency = "CHF"
    session.add(welt.konto)
    for zeile in welt.zeilen:
        zeile.currency = "CHF"
        session.add(zeile)
    await session.commit()


async def test_ein_mandant_in_chf_bekommt_seine_zahlen(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """B rechnet in CHF und sieht seinen Kontostand — nicht eine leere Seite.

    ``1000,00`` Anfangsbestand plus ``500,00`` minus ``120,00`` ergibt ``1380,00``.
    Genau nachgerechnet und nicht bloss „nicht leer": Eine Zusicherung auf „mehr als
    null" waere auch von einer Fassung erfuellt, die irgendetwas zusammenzaehlt.
    """
    await _auf_chf_umstellen(db_session, zwei_mandanten.b)

    kopf = await anmelden(zwei_mandanten.nutzer_b, zwei_mandanten.b)
    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.b.id}/reports/liquidity", headers=kopf
    )
    assert antwort.status_code == 200, antwort.text
    daten = antwort.json()

    assert daten["currency"] == "CHF", (
        f"Die Auswertung von Mandant B laeuft in {daten['currency']}, obwohl sein "
        f"einziges Konto CHF fuehrt. Dann sind alle seine Buchungen ausgeschlossen und "
        f"die Seite bleibt leer."
    )
    assert Decimal(daten["start_balance"]) == Decimal("1380.00"), (
        f"Kontostand {daten['start_balance']} statt 1380,00 — "
        f"1000,00 Anfangsbestand + 500,00 - 120,00."
    )


async def test_der_euro_mandant_bleibt_unberuehrt(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Die Gegenprobe: A rechnet weiter in Euro, obwohl B auf CHF steht.

    Ohne sie waere der Test oben auch von einer Fassung erfuellt, die die Waehrung
    global aus irgendeinem Konto ableitet — dann bekaeme A die Waehrung von B.
    """
    await _auf_chf_umstellen(db_session, zwei_mandanten.b)

    kopf = await anmelden(zwei_mandanten.nutzer_a, zwei_mandanten.a)
    antwort = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/reports/liquidity", headers=kopf
    )
    assert antwort.status_code == 200, antwort.text
    daten = antwort.json()

    assert daten["currency"] == "EUR", (
        f"Mandant A rechnet in {daten['currency']}, obwohl sein Konto Euro fuehrt — "
        f"die Waehrung von B ist ihm zugelaufen."
    )
    assert Decimal(daten["start_balance"]) == Decimal(
        "1380.00"
    ), f"Kontostand von A: {daten['start_balance']} statt 1380,00."
