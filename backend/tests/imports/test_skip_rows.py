"""skip_rows verwirft Zeilen VOR der Spaltenüberschrift - in Import und Vorschau gleich."""
import io
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.models import UserRole
from app.imports.models import JournalLine, utcnow
from app.imports.service import ImportService
from app.tenants.models import ColumnMappingConfig

from tests.imports import (  # noqa: F401
    assign_user_to_mandant,
    client,
    create_account_db,
    create_mandant,
    create_partner_db,
    create_user,
    db_session,
    get_auth_token,
    setup_db,
)

HEADER = "Buchungsdatum;Valutadatum;Betrag;Buchungs-Details"
ROWS = ["01.02.2026;01.02.2026;-10,50;Miete", "02.02.2026;02.02.2026;-5,25;Strom"]
PREAMBLE = ["Kontoauszug Nr. 4/2026", "Zeitraum 01.02.2026 - 28.02.2026"]


def _mapping(skip_rows: int) -> ColumnMappingConfig:
    return ColumnMappingConfig(
        account_id=uuid4(), valuta_date_col="Valutadatum", booking_date_col="Buchungsdatum",
        amount_col="Betrag", description_col="Buchungs-Details",
        decimal_separator=",", date_format="%d.%m.%Y", encoding="utf-8",
        delimiter=";", skip_rows=skip_rows,
    )


class TestBuildCsvReader:
    def _svc(self) -> ImportService:
        return ImportService.__new__(ImportService)

    def test_ohne_praeambel_bleibt_zeile_eins_die_kopfzeile(self):
        decoded = "\n".join([HEADER, *ROWS])
        reader = self._svc()._build_csv_reader(decoded, _mapping(0))
        assert reader.fieldnames == ["Buchungsdatum", "Valutadatum", "Betrag", "Buchungs-Details"]
        assert len(list(reader)) == 2

    def test_ueberspringt_die_praeambel(self):
        decoded = "\n".join([*PREAMBLE, HEADER, *ROWS])
        reader = self._svc()._build_csv_reader(decoded, _mapping(2))
        assert reader.fieldnames == ["Buchungsdatum", "Valutadatum", "Betrag", "Buchungs-Details"]
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["Buchungs-Details"] == "Miete"

    def test_ohne_ueberspringen_wird_die_praeambel_zur_kopfzeile(self):
        # Das war das Verhalten vor dem Fix - unabhaengig vom eingestellten Wert.
        decoded = "\n".join([*PREAMBLE, HEADER, *ROWS])
        reader = self._svc()._build_csv_reader(decoded, _mapping(0))
        assert reader.fieldnames == ["Kontoauszug Nr. 4/2026"]

    def test_erkennt_das_trennzeichen_erst_nach_der_praeambel(self):
        # Die Praeambel enthaelt Kommas, die Daten Semikolons.
        decoded = "\n".join(["Konto, Zeitraum, Waehrung", HEADER, *ROWS])
        reader = self._svc()._build_csv_reader(decoded, _mapping(1))
        assert reader.fieldnames == ["Buchungsdatum", "Valutadatum", "Betrag", "Buchungs-Details"]

    def test_mehr_ueberspringen_als_zeilen_da_sind_bricht_nicht(self):
        reader = self._svc()._build_csv_reader(HEADER, _mapping(10))
        assert reader.fieldnames is None or reader.fieldnames == []


@pytest.mark.asyncio
class TestSkipRowsEndToEnd:
    async def test_import_liest_die_richtige_kopfzeile(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "skip@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        db_session.add(ColumnMappingConfig(
            account_id=account.id, valuta_date_col="Valutadatum", booking_date_col="Buchungsdatum",
            amount_col="Betrag", description_col="Buchungs-Details",
            decimal_separator=",", date_format="%d.%m.%Y", encoding="utf-8",
            delimiter=";", skip_rows=2,
        ))
        await db_session.commit()

        content = "\n".join([*PREAMBLE, HEADER, *ROWS]).encode("utf-8")
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files={"files": ("auszug.csv", content, "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()[0]["row_count"] == 2

        lines = (await db_session.exec(
            select(JournalLine).where(JournalLine.account_id == account.id))).all()
        assert sorted(str(line.amount) for line in lines) == ["-10.50", "-5.25"]
        assert {line.valuta_date for line in lines} == {"2026-02-01", "2026-02-02"}

    async def test_vorschau_zeigt_dieselben_spalten_wie_der_import_liest(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "skip2@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        await db_session.commit()

        content = "\n".join([*PREAMBLE, HEADER, *ROWS]).encode("utf-8")
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/column-mapping/preview",
            params={"delimiter": ";", "encoding": "utf-8", "skip_rows": 2},
            files={"file": ("auszug.csv", content, "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["columns"] == ["Buchungsdatum", "Valutadatum", "Betrag", "Buchungs-Details"]

        ohne = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/column-mapping/preview",
            params={"delimiter": ";", "encoding": "utf-8", "skip_rows": 0},
            files={"file": ("auszug.csv", content, "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ohne.json()["columns"] == ["Kontoauszug Nr. 4/2026"]
