"""Verhalten des Imports, wenn etwas schiefgeht.

Zwei Fragen aus Etappe 3 des Code-Reviews: Bleibt bei einem Fehler mitten in der
Datei ein halber Zustand zurueck? Und was passiert mit bereits verarbeiteten
Dateien, wenn eine spaetere im selben Upload abgelehnt wird?
"""

import io

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.models import UserRole
from app.imports.models import ImportRun, JournalLine
from tests.imports import (  # noqa: F401
    assign_user_to_mandant,
    client,
    create_account_db,
    create_mandant,
    create_mapping_db,
    create_user,
    db_session,
    get_auth_token,
    make_csv,
    setup_db,
)


def _zeile(nr: int, betrag: str) -> dict:
    return {
        "Valuta": f"2026-01-{nr:02d}",
        "Buchungsdatum": f"2026-01-{nr:02d}",
        "Betrag": betrag,
        "Auftraggeber": f"Lieferant {nr}",
        "IBAN": f"DE8937040044053201{nr:04d}",
    }


async def _konto(db_session: AsyncSession, client: AsyncClient):
    user = await create_user(db_session, "imp@test.com", UserRole.accountant)
    mandant = await create_mandant(db_session)
    await assign_user_to_mandant(db_session, user, mandant)
    account = await create_account_db(db_session, mandant.id)
    await create_mapping_db(db_session, account.id)
    token = await get_auth_token(client, user, mandant)
    return mandant, account, {"Authorization": f"Bearer {token}"}


async def test_zweiter_import_derselben_datei_verdoppelt_nichts(
    db_session: AsyncSession, client: AsyncClient
):
    """Die Grundfrage der Idempotenz — mit konfigurierten Vergleichsspalten."""
    mandant, account, headers = await _konto(db_session, client)
    csv_bytes = make_csv([_zeile(1, "100.00"), _zeile(2, "200.00")])
    pfad = f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports"

    for durchlauf in (1, 2):
        resp = await client.post(
            pfad,
            files=[("files", ("a.csv", io.BytesIO(csv_bytes), "text/csv"))],
            headers=headers,
        )
        assert resp.status_code == 201, f"Durchlauf {durchlauf}: {resp.text}"

    zeilen = (
        await db_session.exec(
            select(JournalLine).where(JournalLine.account_id == account.id)
        )
    ).all()
    assert (
        len(zeilen) == 2
    ), f"Nach zwei Importen derselben Datei liegen {len(zeilen)} Zeilen vor"


async def test_abgelehnte_datei_laesst_keine_halb_importierte_zurueck(
    db_session: AsyncSession, client: AsyncClient
):
    """Erste Datei gueltig, zweite keine CSV: der Aufruf scheitert mit 422.

    Die Frage ist, was mit der ersten passiert. Ein Nutzer, der eine
    Fehlermeldung sieht, laedt beide Dateien erneut hoch.
    """
    mandant, account, headers = await _konto(db_session, client)
    gueltig = make_csv([_zeile(1, "100.00")])

    resp = await client.post(
        f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
        files=[
            ("files", ("gut.csv", io.BytesIO(gueltig), "text/csv")),
            ("files", ("notizen.txt", io.BytesIO(b"kein CSV"), "text/plain")),
        ],
        headers=headers,
    )
    assert resp.status_code == 422

    laeufe = (
        await db_session.exec(
            select(ImportRun).where(ImportRun.account_id == account.id)
        )
    ).all()
    zeilen = (
        await db_session.exec(
            select(JournalLine).where(JournalLine.account_id == account.id)
        )
    ).all()
    assert (len(laeufe), len(zeilen)) == (0, 0), (
        f"Der Aufruf meldete einen Fehler, hinterliess aber {len(laeufe)} "
        f"Importlauf/-laeufe mit {len(zeilen)} Buchungszeile(n)."
    )


async def test_integritaetsfehler_verwirft_nicht_die_vorherigen_zeilen(
    db_session: AsyncSession, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """Scheitert eine Zeile, sollen die davor verarbeiteten erhalten bleiben.

    Der Code faengt IntegrityError ab, zaehlt die Zeile als Dublette und macht
    weiter — ruft dazu aber `session.rollback()`, was die gesamte Transaktion
    verwirft, nicht nur die fehlgeschlagene Zeile. Erreichbar ist das etwa, wenn
    zwei Importe gleichzeitig dieselbe neue IBAN registrieren: `partner_ibans.iban`
    ist global eindeutig.
    """
    mandant, account, headers = await _konto(db_session, client)
    # Vor dem Aufruf festhalten: der rollback() im Import entwertet die Objekte
    # dieser Session, danach loest jeder Attributzugriff ein Nachladen aus.
    konto_id = account.id
    csv_bytes = make_csv(
        [_zeile(1, "100.00"), _zeile(2, "200.00"), _zeile(3, "300.00")]
    )

    echtes_flush = AsyncSession.flush
    zustand = {"zeilen_fluesse": 0, "geworfen": False}

    async def flush_mit_stoerung(self, *args, **kwargs):
        # Der Import kapselt jede Buchungszeile in einen Savepoint. Genau den
        # zweiten davon stoeren — so, wie es eine gleichzeitig von einem anderen
        # Import registrierte IBAN taete (partner_ibans.iban ist global eindeutig).
        if self.in_nested_transaction():
            zustand["zeilen_fluesse"] += 1
            if zustand["zeilen_fluesse"] == 2 and not zustand["geworfen"]:
                zustand["geworfen"] = True
                raise IntegrityError("simuliert", None, Exception("UNIQUE"))
        return await echtes_flush(self, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "flush", flush_mit_stoerung)

    resp = await client.post(
        f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
        files=[("files", ("a.csv", io.BytesIO(csv_bytes), "text/csv"))],
        headers=headers,
    )
    monkeypatch.undo()

    assert zustand["geworfen"], "Der Fehlerpfad wurde nicht durchlaufen"
    assert resp.status_code == 201, resp.text
    gemeldet = resp.json()[0]["row_count"]

    zeilen = (
        await db_session.exec(
            select(JournalLine).where(JournalLine.account_id == konto_id)
        )
    ).all()
    assert len(zeilen) == gemeldet, (
        f"Der Lauf meldet {gemeldet} importierte Zeilen, in der Datenbank "
        f"liegen {len(zeilen)}."
    )


async def test_ohne_vergleichsspalte_wird_der_import_abgelehnt(
    db_session: AsyncSession, client: AsyncClient
):
    """Ohne Dublettenpruefung wuerde ein wiederholter Import alles verdoppeln.

    Die Fehlermeldung muss sagen, was zu tun ist — sonst ist der Nutzer geblockt.
    """
    from app.tenants.models import ColumnMappingConfig

    user = await create_user(db_session, "ohnedup@test.com", UserRole.accountant)
    mandant = await create_mandant(db_session)
    await assign_user_to_mandant(db_session, user, mandant)
    account = await create_account_db(db_session, mandant.id)
    db_session.add(
        ColumnMappingConfig(
            account_id=account.id,
            valuta_date_col="Valuta",
            booking_date_col="Buchungsdatum",
            amount_col="Betrag",
            partner_name_col="Auftraggeber",
            partner_iban_col="IBAN",
            date_format="%Y-%m-%d",
            decimal_separator=".",
            delimiter=",",
            column_assignments=[
                {
                    "source": "Valuta",
                    "target": "valuta_date",
                    "sort_order": 0,
                    "duplicate_check": False,
                },
                {
                    "source": "Buchungsdatum",
                    "target": "booking_date",
                    "sort_order": 1,
                    "duplicate_check": False,
                },
                {
                    "source": "Betrag",
                    "target": "amount",
                    "sort_order": 2,
                    "duplicate_check": False,
                },
            ],
        )
    )
    await db_session.commit()
    token = await get_auth_token(client, user, mandant)

    resp = await client.post(
        f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
        files=[
            (
                "files",
                ("a.csv", io.BytesIO(make_csv([_zeile(1, "100.00")])), "text/csv"),
            )
        ],
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 422, resp.text
    assert "Dublettenpruefung" in resp.json()["detail"]


async def test_abgebrochener_import_wird_protokolliert(
    db_session: AsyncSession, client: AsyncClient
):
    """ADR-017: import.failed gehoert ins Audit-Log — auch auf dem Ausnahmepfad."""
    from app.partners.models import AuditLog
    from app.tenants.models import ColumnMappingConfig

    user = await create_user(db_session, "abbruch@test.com", UserRole.accountant)
    mandant = await create_mandant(db_session)
    await assign_user_to_mandant(db_session, user, mandant)
    account = await create_account_db(db_session, mandant.id)
    mandant_id = mandant.id
    db_session.add(
        ColumnMappingConfig(
            account_id=account.id,
            valuta_date_col="Valuta",
            booking_date_col="Buchungsdatum",
            amount_col="Betrag",
            date_format="%Y-%m-%d",
            decimal_separator=".",
            delimiter=",",
            column_assignments=[
                {
                    "source": "Valuta",
                    "target": "valuta_date",
                    "sort_order": 0,
                    "duplicate_check": True,
                },
                {
                    "source": "Buchungsreferenz",
                    "target": "unused",
                    "sort_order": 1,
                    "duplicate_check": True,
                },
            ],
        )
    )
    await db_session.commit()
    token = await get_auth_token(client, user, mandant)

    # Die CSV traegt die konfigurierte Vergleichsspalte "Buchungsreferenz" nicht —
    # das bricht die Verarbeitung mitten im Lauf ab.
    resp = await client.post(
        f"/api/v1/mandants/{mandant_id}/accounts/{account.id}/imports",
        files=[
            (
                "files",
                ("a.csv", io.BytesIO(make_csv([_zeile(1, "100.00")])), "text/csv"),
            )
        ],
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422, resp.text
    assert "duplicate-check" in resp.json()["detail"]

    eintraege = (
        await db_session.exec(select(AuditLog).where(AuditLog.mandant_id == mandant_id))
    ).all()
    fehlgeschlagen = [e for e in eintraege if e.event_type == "import.failed"]
    assert fehlgeschlagen, (
        "Der Import brach ab, ohne einen import.failed-Eintrag zu hinterlassen. "
        f"Vorhanden: {[e.event_type for e in eintraege]}"
    )
    assert fehlgeschlagen[0].payload["filename"] == "a.csv"
