"""Loeschen einer Leistung mit zugeordneten Buchungen.

Regressionstest zu einem Befund aus Stufe 3 des Mandantenfaehigkeitsplans, gefunden
am 2026-09-10 durch die Gegenprobe in ``test_tenancy_services.py``.

Was schiefging
--------------
``delete_service`` loescht die Leistung, **committet**, und ruft danach die
Neubewertung des Partners auf::

    await self._session.delete(service)
    await self._session.commit()          # ← ab hier ist es endgueltig
    await self._trigger_revalidation(partner_id)

Die Neubewertung sammelt in ``touched_service_ids`` die Kennungen aller Leistungen,
auf die Aufteilungen der Buchungszeilen zeigen — und darin steht die gerade geloeschte
Leistung, weil die Aufteilung sie eben noch nannte. Fuer jede dieser Kennungen ruft
sie ``detect_service_type_for_service``, das ueber ``_get_service`` nachlaedt und bei
einer unbekannten Kennung 404 wirft.

Zwei Folgen, die zweite ist die schwerere:

1. **Die Leistung war geloescht, die Antwort lautete 404 „Service not found".** Der
   Aufrufer bekam einen Fehlschlag fuer einen Vorgang, der stattgefunden hatte.
2. Die Neubewertung brach an dieser Stelle ab, **bevor** ihr abschliessendes
   ``commit()`` lief. Alles, was sie bis dahin im Arbeitsspeicher zurechtgelegt hatte
   — die Umhaengung der Aufteilungen auf die Basisleistung, das Aufraeumen der
   Review-Eintraege —, ging beim Schliessen der Sitzung verloren. Zurueck blieben
   Aufteilungen, die auf eine Leistung zeigen, die es nicht mehr gibt.

Warum es niemandem auffiel
--------------------------
Der Fall braucht eine Leistung mit **mindestens einer zugeordneten Buchung**. Ohne
Aufteilung steht keine Kennung in ``touched_service_ids``, und alles laeuft durch.
``app/services/service.py`` stand bei 41 % Abdeckung; dieser Pfad war nicht darunter.

Die Behebung uebergeht in der Schleife Kennungen, die nicht mehr aufloesbar sind —
eine gesammelte Kennung darf im selben Durchlauf verschwinden.

Warum alles in *einem* Test steht
---------------------------------
Erster Entwurf hatte drei Tests: Statuscode, verwaiste Aufteilungen, Zuordnung der
Buchung. Die Probe gegen den unbehobenen Stand zeigte, dass nur der erste anschlug —
die anderen zwei blieben gruen, **obwohl der Fehler da war**.

Der Grund liegt im Testaufbau: Test und Anwendung teilen dieselbe Datenbanksitzung.
Die Umhaengungen der Neubewertung standen darin als ausstehende Aenderungen und waren
fuer den Test sichtbar, obwohl sie nie committet wurden. Im Betrieb schliesst die
Dependency die Sitzung nach der Ausnahme, und sie sind weg. Zwei Tests prueften also
etwas, was sie nicht pruefen konnten — genau die Sorte Pruefschritt, nach der Frage 5
des Merge-Checks sucht.

Deshalb stehen die Folgepruefungen jetzt **hinter** der Zusicherung auf 204 im selben
Test. Sie werden nur erreicht, wenn der Aufruf Erfolg gemeldet hat, und sind dann
aussagekraeftig.
"""

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.imports.models import JournalLineSplit
from app.services.models import Service
from tests.conftest import AnmeldeHelfer, ZweiMandanten


async def test_leistung_mit_buchungen_wird_geloescht_und_meldet_erfolg(
    client: AsyncClient,
    zwei_mandanten: ZweiMandanten,
    anmelden: AnmeldeHelfer,
    db_session: AsyncSession,
):
    """Der Befund und seine Folgen, in der Reihenfolge ihrer Aussagekraft.

    Die Leistung der Fixture hat eine zugeordnete Buchung — genau die Voraussetzung,
    unter der der Fehler auftrat. Gegen den unbehobenen Stand geprueft: Die
    Zusicherung auf 204 schlaegt an.
    """
    leistung_id = zwei_mandanten.a.leistung.id
    zeile_mit_zuordnung = zwei_mandanten.a.zeilen[1]
    header = await anmelden(zwei_mandanten.nutzer_a)

    # Voraussetzung nachweisen: es gibt eine Aufteilung auf diese Leistung. Ohne sie
    # prueft der Test einen anderen, harmlosen Pfad.
    aufteilungen = (
        await db_session.exec(
            select(JournalLineSplit).where(JournalLineSplit.service_id == leistung_id)
        )
    ).all()
    assert aufteilungen, (
        "Die Leistung hat keine zugeordnete Buchung — dann trifft dieser Test den "
        "Befund nicht."
    )

    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/services/{leistung_id}",
        headers=header,
    )

    # 1. Der Befund selbst: Erfolg meldet Erfolg.
    assert antwort.status_code == 204, (
        f"Loeschen einer Leistung mit Buchungen meldet {antwort.status_code}: "
        f"{antwort.text}"
    )
    assert await db_session.get(Service, leistung_id) is None

    # 2. Ab hier ist belegt, dass der Aufruf durchlief — die Folgepruefungen sind
    #    also aussagekraeftig (siehe Modulkopf).
    verwaist = (
        await db_session.exec(
            select(JournalLineSplit).where(JournalLineSplit.service_id == leistung_id)
        )
    ).all()
    assert (
        not verwaist
    ), f"{len(verwaist)} Aufteilungen zeigen noch auf die geloeschte Leistung."

    # 3. Die Buchung darf nicht unzugeordnet zurueckbleiben — sonst fehlt sie in
    #    jeder Auswertung, und das findet nur eine Summenpruefung.
    danach = (
        await db_session.exec(
            select(JournalLineSplit).where(
                JournalLineSplit.journal_line_id == zeile_mit_zuordnung.id
            )
        )
    ).all()
    assert danach, "Die Buchung hat nach dem Loeschen keine Zuordnung mehr."

    ziel = await db_session.get(Service, danach[0].service_id)
    assert ziel is not None
    assert (
        ziel.is_base_service
    ), f"Die Buchung haengt an {ziel.name!r} statt an der Basisleistung."


async def test_basisleistung_bleibt_unloeschbar(
    client: AsyncClient, zwei_mandanten: ZweiMandanten, anmelden: AnmeldeHelfer
):
    """Die Basisleistung ist der Auffangpunkt und darf nicht verschwinden.

    Sie entsteht erst durch das Loeschen oben — vorher hat der Partner der Fixture
    keine. Deshalb wird sie hier zuerst erzeugt und dann angegriffen.
    """
    header = await anmelden(zwei_mandanten.nutzer_a)

    await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/services/{zwei_mandanten.a.leistung.id}",
        headers=header,
    )

    liste = await client.get(
        f"/api/v1/mandants/{zwei_mandanten.a.id}"
        f"/partners/{zwei_mandanten.a.partner.id}/services",
        headers=header,
    )
    assert liste.status_code == 200, liste.text
    daten = liste.json()
    eintraege = daten["items"] if isinstance(daten, dict) else daten
    basis = [e for e in eintraege if e["is_base_service"]]
    assert len(basis) == 1, f"Erwartet genau eine Basisleistung, gefunden {len(basis)}"

    antwort = await client.delete(
        f"/api/v1/mandants/{zwei_mandanten.a.id}/services/{basis[0]['id']}",
        headers=header,
    )
    assert antwort.status_code == 409, antwort.text
