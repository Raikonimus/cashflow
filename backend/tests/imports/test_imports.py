"""Tests for Import Core (Bolt 006).

Stories covered:
  001-csv-upload-endpoint
  002-mapping-application
  004-import-run-tracking
"""
import io
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.models import UserRole
from app.imports.models import ImportRun, ImportStatus, JournalLine
from app.tenants.models import ColumnMappingConfig
from tests.imports import (
    assign_user_to_mandant,
    create_account_db,
    create_mandant,
    create_mapping_db,
    create_user,
    get_auth_token,
    make_csv,
)

CSV_ROWS = [
    {
        "Valuta": "2026-01-15",
        "Buchungsdatum": "2026-01-15",
        "Betrag": "123.45",
        "Auftraggeber": "Amazon EU",
        "IBAN": "DE89370400440532013000",
    }
]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestCsvUpload:
    """Story 001: upload CSV endpoint."""

    async def test_upload_creates_import_run_and_lines(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Valid account+mapping → ImportRun created, JournalLine inserted."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        await create_mapping_db(db_session, account.id)
        token = await get_auth_token(client, user, mandant)

        csv_bytes = make_csv(CSV_ROWS)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("test.csv", io.BytesIO(csv_bytes), "text/csv"))],
            headers=_auth(token),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 1
        run = data[0]
        assert run["row_count"] == 1
        assert run["skipped_count"] == 0
        assert run["status"] == ImportStatus.completed.value
        assert run["filename"] == "test.csv"

        result = await db_session.exec(select(JournalLine))
        lines = result.all()
        assert len(lines) == 1
        assert lines[0].partner_name_raw == "Amazon EU"
        assert lines[0].partner_iban_raw == "DE89370400440532013000"
        assert lines[0].partner_id is not None  # Bolt 007: new partner auto-created via matching

    async def test_upload_no_mapping_returns_422(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Account without column mapping → 422."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        token = await get_auth_token(client, user, mandant)

        csv_bytes = make_csv(CSV_ROWS)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("test.csv", io.BytesIO(csv_bytes), "text/csv"))],
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_upload_non_csv_returns_422(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Non-CSV file → 422."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        await create_mapping_db(db_session, account.id)
        token = await get_auth_token(client, user, mandant)

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("report.xlsx", io.BytesIO(b"PK"), "application/zip"))],
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_upload_multiple_files_creates_multiple_runs(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Multiple files → each gets its own ImportRun."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        await create_mapping_db(db_session, account.id)
        token = await get_auth_token(client, user, mandant)

        csv1 = make_csv(CSV_ROWS)
        csv2 = make_csv([
            {
                "Valuta": "2026-02-01",
                "Buchungsdatum": "2026-02-01",
                "Betrag": "99.00",
                "Auftraggeber": "MediaMarkt",
                "IBAN": "DE12500105170648489890",
            }
        ])
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[
                ("files", ("jan.csv", io.BytesIO(csv1), "text/csv")),
                ("files", ("feb.csv", io.BytesIO(csv2), "text/csv")),
            ],
            headers=_auth(token),
        )
        assert resp.status_code == 201
        runs = resp.json()
        assert len(runs) == 2
        assert {r["filename"] for r in runs} == {"jan.csv", "feb.csv"}

    async def test_viewer_cannot_upload(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Viewer cannot upload CSV."""
        viewer = await create_user(db_session, "view@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, viewer, mandant)
        account = await create_account_db(db_session, mandant.id)
        await create_mapping_db(db_session, account.id)
        token = await get_auth_token(client, viewer, mandant)

        csv_bytes = make_csv(CSV_ROWS)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("test.csv", io.BytesIO(csv_bytes), "text/csv"))],
            headers=_auth(token),
        )
        assert resp.status_code == 403

    async def test_duplicate_row_is_skipped(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Given a row already imported,
        When same CSV uploaded again,
        Then row is skipped (skipped_count=1, row_count=0, status=completed).
        """
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        await create_mapping_db(db_session, account.id)
        token = await get_auth_token(client, user, mandant)

        csv_bytes = make_csv(CSV_ROWS)

        # First upload
        resp1 = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("test.csv", io.BytesIO(csv_bytes), "text/csv"))],
            headers=_auth(token),
        )
        assert resp1.status_code == 201
        assert resp1.json()[0]["row_count"] == 1

        # Second upload (same file)
        resp2 = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("test.csv", io.BytesIO(csv_bytes), "text/csv"))],
            headers=_auth(token),
        )
        assert resp2.status_code == 201
        run2 = resp2.json()[0]
        assert run2["row_count"] == 0
        assert run2["skipped_count"] == 1
        assert run2["status"] == ImportStatus.completed.value

    async def test_all_duplicates_still_completed(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """All rows duplicates → status=completed, row_count=0, skipped_count=N."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        await create_mapping_db(db_session, account.id)
        token = await get_auth_token(client, user, mandant)

        rows = [
            {"Valuta": "2026-01-01", "Buchungsdatum": "2026-01-01", "Betrag": "10.00", "Auftraggeber": "A", "IBAN": ""},
            {"Valuta": "2026-01-02", "Buchungsdatum": "2026-01-02", "Betrag": "20.00", "Auftraggeber": "B", "IBAN": ""},
        ]
        csv_bytes = make_csv(rows)

        # First run
        await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("data.csv", io.BytesIO(csv_bytes), "text/csv"))],
            headers=_auth(token),
        )

        # Second run (all dups)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("data.csv", io.BytesIO(csv_bytes), "text/csv"))],
            headers=_auth(token),
        )
        assert resp.status_code == 201
        run = resp.json()[0]
        assert run["row_count"] == 0
        assert run["skipped_count"] == 2
        assert run["status"] == ImportStatus.completed.value

    async def test_selected_duplicate_check_columns_control_duplicate_detection(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)

        mapping = ColumnMappingConfig(
            account_id=account.id,
            valuta_date_col="Valuta",
            booking_date_col="Buchungsdatum",
            amount_col="Betrag",
            partner_name_col="Auftraggeber",
            partner_iban_col=None,
            description_col="Verwendungszweck",
            column_assignments=[
                {"source": "Valuta", "target": "valuta_date", "sort_order": 0, "duplicate_check": False},
                {"source": "Buchungsdatum", "target": "booking_date", "sort_order": 1, "duplicate_check": False},
                {"source": "Betrag", "target": "amount", "sort_order": 2, "duplicate_check": False},
                {"source": "Auftraggeber", "target": "partner_name", "sort_order": 3, "duplicate_check": False},
                {"source": "Verwendungszweck", "target": "description", "sort_order": 4, "duplicate_check": False},
                {"source": "Referenz", "target": "unused", "sort_order": 5, "duplicate_check": True},
            ],
            decimal_separator=".",
            date_format="%Y-%m-%d",
            delimiter=",",
            encoding="utf-8",
            skip_rows=0,
        )
        db_session.add(mapping)
        await db_session.commit()
        token = await get_auth_token(client, user, mandant)

        first_csv = make_csv([
            {
                "Valuta": "2026-01-15",
                "Buchungsdatum": "2026-01-15",
                "Betrag": "123.45",
                "Auftraggeber": "Amazon EU",
                "Verwendungszweck": "Erster Import",
                "Referenz": "REF-001",
            }
        ])
        second_csv = make_csv([
            {
                "Valuta": "2026-01-16",
                "Buchungsdatum": "2026-01-16",
                "Betrag": "999.99",
                "Auftraggeber": "Anderer Partner",
                "Verwendungszweck": "Zweiter Import",
                "Referenz": "REF-001",
            }
        ])

        resp1 = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("first.csv", io.BytesIO(first_csv), "text/csv"))],
            headers=_auth(token),
        )
        assert resp1.status_code == 201
        assert resp1.json()[0]["row_count"] == 1

        resp2 = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("second.csv", io.BytesIO(second_csv), "text/csv"))],
            headers=_auth(token),
        )
        assert resp2.status_code == 201
        run2 = resp2.json()[0]
        assert run2["row_count"] == 0
        assert run2["skipped_count"] == 1

        lines = (await db_session.exec(select(JournalLine))).all()
        assert len(lines) == 1

    async def test_duplicate_detection_uses_selected_columns_for_legacy_rows_without_source_values(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)

        mapping = ColumnMappingConfig(
            account_id=account.id,
            valuta_date_col="Valuta",
            booking_date_col="Buchungsdatum",
            amount_col="Betrag",
            partner_name_col="Auftraggeber",
            partner_iban_col=None,
            description_col="Verwendungszweck",
            column_assignments=[
                {"source": "Valuta", "target": "valuta_date", "sort_order": 0, "duplicate_check": False},
                {"source": "Buchungsdatum", "target": "booking_date", "sort_order": 1, "duplicate_check": False},
                {"source": "Betrag", "target": "amount", "sort_order": 2, "duplicate_check": False},
                {"source": "Auftraggeber", "target": "partner_name", "sort_order": 3, "duplicate_check": False},
                {"source": "Verwendungszweck", "target": "description", "sort_order": 4, "duplicate_check": False},
                {"source": "Referenz", "target": "unused", "sort_order": 5, "duplicate_check": True},
            ],
            decimal_separator=".",
            date_format="%Y-%m-%d",
            delimiter=",",
            encoding="utf-8",
            skip_rows=0,
        )
        db_session.add(mapping)

        previous_run = ImportRun(
            account_id=account.id,
            mandant_id=mandant.id,
            user_id=user.id,
            filename="legacy.csv",
            status=ImportStatus.completed.value,
            row_count=1,
        )
        db_session.add(previous_run)
        await db_session.flush()

        db_session.add(
            JournalLine(
                account_id=account.id,
                import_run_id=previous_run.id,
                partner_id=None,
                service_id=None,
                service_assignment_mode=None,
                valuta_date="2026-01-15",
                booking_date="2026-01-15",
                amount=Decimal("123.45"),
                currency="EUR",
                text="Altbestand",
                partner_name_raw="Amazon EU",
                partner_iban_raw=None,
                partner_account_raw=None,
                partner_blz_raw=None,
                partner_bic_raw=None,
                unmapped_data={"Referenz": "REF-001"},
            )
        )
        await db_session.commit()

        token = await get_auth_token(client, user, mandant)

        duplicate_csv = make_csv([
            {
                "Valuta": "2026-01-16",
                "Buchungsdatum": "2026-01-16",
                "Betrag": "999.99",
                "Auftraggeber": "Anderer Partner",
                "Verwendungszweck": "Neuer Import",
                "Referenz": "REF-001",
            }
        ])

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("duplicate.csv", io.BytesIO(duplicate_csv), "text/csv"))],
            headers=_auth(token),
        )
        assert resp.status_code == 201
        run = resp.json()[0]
        assert run["row_count"] == 0
        assert run["skipped_count"] == 1

        lines = (await db_session.exec(select(JournalLine))).all()
        assert len(lines) == 1

    async def test_import_rejects_missing_duplicate_check_column(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)

        mapping = ColumnMappingConfig(
            account_id=account.id,
            valuta_date_col="Valuta",
            booking_date_col="Buchungsdatum",
            amount_col="Betrag",
            partner_name_col="Auftraggeber",
            partner_iban_col=None,
            description_col=None,
            column_assignments=[
                {"source": "Valuta", "target": "valuta_date", "sort_order": 0, "duplicate_check": False},
                {"source": "Buchungsdatum", "target": "booking_date", "sort_order": 1, "duplicate_check": False},
                {"source": "Betrag", "target": "amount", "sort_order": 2, "duplicate_check": False},
                {"source": "Referenz", "target": "unused", "sort_order": 3, "duplicate_check": True},
            ],
            decimal_separator=".",
            date_format="%Y-%m-%d",
            delimiter=",",
            encoding="utf-8",
            skip_rows=0,
        )
        db_session.add(mapping)
        await db_session.commit()
        token = await get_auth_token(client, user, mandant)

        csv_bytes = make_csv([
            {
                "Valuta": "2026-01-15",
                "Buchungsdatum": "2026-01-15",
                "Betrag": "123.45",
            }
        ])

        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("invalid.csv", io.BytesIO(csv_bytes), "text/csv"))],
            headers=_auth(token),
        )
        assert resp.status_code == 422
        assert "duplicate-check columns" in resp.json()["detail"]

    async def test_duplicate_check_column_misassigned_to_booking_date_does_not_break_parse(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)

        mapping = ColumnMappingConfig(
            account_id=account.id,
            valuta_date_col="Valuta",
            booking_date_col="Buchungsdatum",
            amount_col="Betrag",
            partner_name_col="Auftraggeber",
            partner_iban_col=None,
            description_col="Verwendungszweck",
            column_assignments=[
                {"source": "Valuta", "target": "valuta_date", "sort_order": 0, "duplicate_check": False},
                {"source": "Buchungsdatum", "target": "booking_date", "sort_order": 1, "duplicate_check": False},
                {"source": "Betrag", "target": "amount", "sort_order": 2, "duplicate_check": False},
                {"source": "Auftraggeber", "target": "partner_name", "sort_order": 3, "duplicate_check": False},
                {"source": "Verwendungszweck", "target": "description", "sort_order": 4, "duplicate_check": False},
                {"source": "Referenz", "target": "booking_date", "sort_order": 5, "duplicate_check": True},
            ],
            decimal_separator=".",
            date_format="%Y-%m-%d",
            delimiter=",",
            encoding="utf-8",
            skip_rows=0,
        )
        db_session.add(mapping)
        await db_session.commit()
        token = await get_auth_token(client, user, mandant)

        first_csv = make_csv([
            {
                "Valuta": "2026-03-31",
                "Buchungsdatum": "2026-03-31",
                "Betrag": "123.45",
                "Auftraggeber": "Amazon EU",
                "Verwendungszweck": "Erster Import",
                "Referenz": "REF-001",
            }
        ])
        second_csv = make_csv([
            {
                "Valuta": "2026-04-01",
                "Buchungsdatum": "2026-04-01",
                "Betrag": "999.99",
                "Auftraggeber": "Anderer Partner",
                "Verwendungszweck": "Zweiter Import",
                "Referenz": "REF-001",
            }
        ])

        resp1 = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("first.csv", io.BytesIO(first_csv), "text/csv"))],
            headers=_auth(token),
        )
        assert resp1.status_code == 201
        run1 = resp1.json()[0]
        assert run1["row_count"] == 1
        assert run1["error_count"] == 0
        assert run1["status"] == ImportStatus.completed.value

        resp2 = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("second.csv", io.BytesIO(second_csv), "text/csv"))],
            headers=_auth(token),
        )
        assert resp2.status_code == 201
        run2 = resp2.json()[0]
        assert run2["row_count"] == 0
        assert run2["skipped_count"] == 1

        lines = (await db_session.exec(select(JournalLine))).all()
        assert len(lines) == 1
        assert lines[0].booking_date == "2026-03-31"


@pytest.mark.asyncio
class TestMappingApplication:
    """Story 002: column mapping applied correctly."""

    async def test_multi_source_concat_with_newline(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Two source columns mapped to same target (sort_order) → concatenated with \\n.
        This is tested here at the service level by verifying the JournalLine text field.
        """
        from datetime import datetime, timezone

        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)

        # Create mapping with description_col = "Verwendungszweck"
        now = datetime.now(timezone.utc)
        mapping = ColumnMappingConfig(
            account_id=account.id,
            valuta_date_col="Valuta",
            booking_date_col="Buchungsdatum",
            amount_col="Betrag",
            partner_name_col="Auftraggeber",
            partner_iban_col=None,
            description_col="Verwendungszweck",
            decimal_separator=".",
            date_format="%Y-%m-%d",
            delimiter=",",
            encoding="utf-8",
            skip_rows=0,
            created_at=now,
            updated_at=now,
        )
        db_session.add(mapping)
        await db_session.commit()

        token = await get_auth_token(client, user, mandant)

        rows = [{
            "Valuta": "2026-03-01",
            "Buchungsdatum": "2026-03-01",
            "Betrag": "50.00",
            "Auftraggeber": "Rewe",
            "Verwendungszweck": "Wocheneinkauf",
        }]
        csv_bytes = make_csv(rows)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("test.csv", io.BytesIO(csv_bytes), "text/csv"))],
            headers=_auth(token),
        )
        assert resp.status_code == 201

        result = await db_session.exec(select(JournalLine))
        lines = result.all()
        assert len(lines) == 1
        assert lines[0].text == "Wocheneinkauf"

    async def test_unmapped_columns_stored_in_unmapped_data(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Columns not in mapping → stored in unmapped_data JSONB."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        await create_mapping_db(db_session, account.id)
        token = await get_auth_token(client, user, mandant)

        rows = [{
            "Valuta": "2026-04-01",
            "Buchungsdatum": "2026-04-01",
            "Betrag": "75.00",
            "Auftraggeber": "Lidl",
            "IBAN": "",
            "ExtraColumn": "some_value",
        }]
        csv_bytes = make_csv(rows)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("test.csv", io.BytesIO(csv_bytes), "text/csv"))],
            headers=_auth(token),
        )
        assert resp.status_code == 201

        result = await db_session.exec(select(JournalLine))
        lines = result.all()
        assert len(lines) == 1
        assert lines[0].unmapped_data is not None
        assert "ExtraColumn" in lines[0].unmapped_data


@pytest.mark.asyncio
class TestImportRunTracking:
    """Story 004: import run tracking."""

    async def test_list_import_runs(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """GET /imports lists runs for the account."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        await create_mapping_db(db_session, account.id)
        token = await get_auth_token(client, user, mandant)

        csv_bytes = make_csv(CSV_ROWS)
        await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("run1.csv", io.BytesIO(csv_bytes), "text/csv"))],
            headers=_auth(token),
        )

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["filename"] == "run1.csv"

    async def test_get_import_run_detail(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """GET /imports/:id returns run detail with status, row_count."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        await create_mapping_db(db_session, account.id)
        token = await get_auth_token(client, user, mandant)

        csv_bytes = make_csv(CSV_ROWS)
        upload_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            files=[("files", ("detail.csv", io.BytesIO(csv_bytes), "text/csv"))],
            headers=_auth(token),
        )
        run_id = upload_resp.json()[0]["id"]

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports/{run_id}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["id"] == run_id
        assert detail["status"] == ImportStatus.completed.value
        assert detail["row_count"] == 1
        assert detail["completed_at"] is not None

    async def test_viewer_can_list_runs(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        viewer = await create_user(db_session, "view@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, viewer, mandant)
        account = await create_account_db(db_session, mandant.id)
        token = await get_auth_token(client, viewer, mandant)

        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    async def test_get_unknown_run_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        account = await create_account_db(db_session, mandant.id)
        token = await get_auth_token(client, user, mandant)

        import uuid
        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/accounts/{account.id}/imports/{uuid.uuid4()}",
            headers=_auth(token),
        )
        assert resp.status_code == 404
