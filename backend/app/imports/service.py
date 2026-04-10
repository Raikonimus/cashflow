import csv
import io
from datetime import datetime
from sqlalchemy.exc import IntegrityError


def _detect_encoding(raw: bytes) -> str:
    """Erkennt Zeichensatz via BOM, dann Trial-decode."""
    if raw[:2] == b'\xff\xfe' or raw[:2] == b'\xfe\xff':
        return 'utf-16'
    if raw[:3] == b'\xef\xbb\xbf':
        return 'utf-8-sig'
    for enc in ('utf-8', 'cp1252', 'latin-1'):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return 'utf-8'


def _detect_delimiter(text: str, fallback: str) -> str:
    """Erkennt das CSV-Trennzeichen via csv.Sniffer (quote-bewusst).
    Fällt auf die konfigurierte Einstellung zurück wenn der Sniffer scheitert."""
    try:
        sample = text[:8192]
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        return dialect.delimiter
    except csv.Error:
        return fallback
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

import structlog
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.imports.matching import PartnerMatchingService, ReviewItemFactory
from app.imports.models import ImportRun, ImportStatus, JournalLine, ReviewItem, utcnow
from app.partners.models import AuditLog
from app.tenants.models import Account, ColumnMappingConfig
from app.tenants.service import AccountService

log = structlog.get_logger()


def _parse_decimal(raw: str, decimal_separator: str) -> Decimal:
    """Parse amount string, handling German/European decimal separators."""
    cleaned = raw.strip()
    if decimal_separator == ",":
        # Remove thousands separator (.) then replace decimal separator
        cleaned = cleaned.replace(".", "").replace(",", ".")
    return Decimal(cleaned)


def _parse_date(raw: str, date_format: str) -> str:
    """Parse date string and return ISO 8601 date string (YYYY-MM-DD)."""
    return datetime.strptime(raw.strip(), date_format).date().isoformat()


class ImportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upload(
        self,
        actor_id: UUID,
        account_id: UUID,
        mandant_id: UUID,
        files: list[UploadFile],
    ) -> list[ImportRun]:
        # Verify account belongs to mandant
        account = await self._session.get(Account, account_id)
        if account is None or account.mandant_id != mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

        # Load column mapping config
        mapping = await self._load_mapping(account_id)
        if mapping is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="No column mapping configured for this account",
            )

        results: list[ImportRun] = []
        for file in files:
            if not self._is_csv(file):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"File '{file.filename}' is not a CSV",
                )
            run = await self._process_file(actor_id, account_id, mandant_id, file, mapping)
            results.append(run)
        return results

    async def _process_file(
        self,
        actor_id: UUID,
        account_id: UUID,
        mandant_id: UUID,
        file: UploadFile,
        mapping: ColumnMappingConfig,
    ) -> ImportRun:
        run = ImportRun(
            account_id=account_id,
            mandant_id=mandant_id,
            user_id=actor_id,
            filename=file.filename or "upload.csv",
            status=ImportStatus.pending.value,
        )
        self._session.add(run)
        await self._session.flush()

        run.status = ImportStatus.processing.value

        content = await file.read()
        encoding = _detect_encoding(content)
        try:
            decoded = content.decode(encoding)
        except UnicodeDecodeError:
            decoded = content.decode('utf-8', errors='replace')

        lines_to_insert: list[dict] = []
        errors: list[dict] = []

        effective_delimiter = _detect_delimiter(decoded, fallback=mapping.delimiter or ";")
        reader = csv.DictReader(
            io.StringIO(decoded),
            delimiter=effective_delimiter,
        )

        for row_num, row in enumerate(reader, start=1 + (mapping.skip_rows or 0)):
            if row_num <= (mapping.skip_rows or 0):
                continue

            try:
                line_data = self._map_row(row, mapping, run.id, account_id, row_num)
                if line_data is None:
                    errors.append({"row": row_num, "error": "required field missing after mapping"})
                    continue
                lines_to_insert.append(line_data)
            except (ValueError, InvalidOperation) as exc:
                errors.append({"row": row_num, "error": str(exc)})

        inserted, skipped, review_items, duplicates = await self._bulk_insert_with_matching(
            lines_to_insert, mandant_id, run.id, account_id
        )

        run.row_count = inserted
        run.skipped_count = skipped
        run.error_count = len(errors)
        run.completed_at = utcnow()

        details: dict = {}
        if errors:
            details["parse_errors"] = errors
        if duplicates:
            details["duplicates"] = duplicates

        if errors and inserted == 0 and skipped == 0 and not duplicates:
            run.status = ImportStatus.failed.value
        else:
            run.status = ImportStatus.completed.value

        run.error_details = details if details else None

        for ri in review_items:
            self._session.add(ri)

        self._session.add(run)
        await self._session.commit()
        await self._session.refresh(run)

        audit_entry = AuditLog(
            mandant_id=mandant_id,
            event_type="import.completed" if run.status == ImportStatus.completed.value else "import.failed",
            actor_id=actor_id,
            payload={
                "import_run_id": str(run.id),
                "account_id": str(account_id),
                "filename": run.filename,
                "rows_inserted": inserted,
                "rows_skipped": skipped,
                "rows_error": len(errors),
                "status": run.status,
            },
        )
        self._session.add(audit_entry)
        await self._session.commit()

        log.info(
            "import_run_completed",
            run_id=str(run.id),
            account_id=str(account_id),
            row_count=inserted,
            skipped=skipped,
            errors=len(errors),
        )
        return run

    def _map_row(
        self,
        row: dict[str, str],
        mapping: ColumnMappingConfig,
        run_id: UUID,
        account_id: UUID,
        row_num: int,
    ) -> dict | None:
        """Map a CSV row using ColumnMappingConfig.

        Wenn ``column_assignments`` gesetzt ist, wird die spaltenbasierte Zuordnung
        verwendet (Multi-Mapping: mehrere Quellspalten → selbes Zielfeld werden mit
        Zeilenumbruch zusammengeführt). Andernfalls greift das Legacy-Mapping.
        """
        assignments = mapping.column_assignments  # list[dict] | None

        if assignments:
            return self._map_row_from_assignments(row, assignments, mapping, run_id, account_id, row_num)
        return self._map_row_legacy(row, mapping, run_id, account_id, row_num)

    def _map_row_from_assignments(
        self,
        row: dict[str, str],
        assignments: list[dict],
        mapping: ColumnMappingConfig,
        run_id: UUID,
        account_id: UUID,
        row_num: int,
    ) -> dict | None:
        """Assignment-based mapping mit Multi-Mapping-Unterstützung."""
        # Gruppiere Quellspalten nach Zielfeld, sortiert nach sort_order
        by_target: dict[str, list[str]] = {}
        for a in sorted(assignments, key=lambda x: x.get("sort_order", 0)):
            target = a.get("target", "")
            if target == "unused":
                continue
            by_target.setdefault(target, []).append(a.get("source", ""))

        def get_concat(target: str) -> str | None:
            sources = by_target.get(target, [])
            parts = [row.get(s, "").strip() for s in sources]
            parts = [p for p in parts if p]
            return "\n".join(parts) if parts else None

        valuta_raw = get_concat("valuta_date")
        booking_raw = get_concat("booking_date")
        amount_raw = get_concat("amount")

        if not valuta_raw or not booking_raw or not amount_raw:
            return None

        try:
            valuta_date = _parse_date(valuta_raw, mapping.date_format)
            booking_date = _parse_date(booking_raw, mapping.date_format)
            amount = _parse_decimal(amount_raw, mapping.decimal_separator)
        except (ValueError, InvalidOperation) as exc:
            raise ValueError(f"Row {row_num}: {exc}") from exc

        # Spalten, die explizit zugeordnet sind (auch "unused")
        assigned_sources = {a.get("source", "") for a in assignments}
        unmapped = {k: v for k, v in row.items() if k not in assigned_sources and v}

        return {
            "_csv_row_num": row_num,
            "account_id": account_id,
            "import_run_id": run_id,
            "valuta_date": valuta_date,
            "booking_date": booking_date,
            "amount": str(amount),
            "currency": (get_concat("currency") or "EUR").strip().upper()[:3],
            "text": get_concat("description"),
            "partner_name_raw": get_concat("partner_name"),
            "partner_iban_raw": get_concat("partner_iban"),
            "partner_account_raw": get_concat("partner_account"),
            "partner_blz_raw": get_concat("partner_blz"),
            "partner_bic_raw": get_concat("partner_bic"),
            "unmapped_data": unmapped if unmapped else None,
        }

    def _map_row_legacy(
        self,
        row: dict[str, str],
        mapping: ColumnMappingConfig,
        run_id: UUID,
        account_id: UUID,
        row_num: int,
    ) -> dict | None:
        """Legacy-Mapping: ein Spaltenname pro Zielfeld (rückwärtskompatibel)."""
        def get(field: str | None) -> str | None:
            if field is None:
                return None
            return row.get(field, "").strip() or None

        valuta_raw = get(mapping.valuta_date_col)
        booking_raw = get(mapping.booking_date_col)
        amount_raw = get(mapping.amount_col)

        if not valuta_raw or not booking_raw or not amount_raw:
            return None

        try:
            valuta_date = _parse_date(valuta_raw, mapping.date_format)
            booking_date = _parse_date(booking_raw, mapping.date_format)
            amount = _parse_decimal(amount_raw, mapping.decimal_separator)
        except (ValueError, InvalidOperation) as exc:
            raise ValueError(f"Row {row_num}: {exc}") from exc

        # Collect unmapped columns
        known_cols = {
            mapping.valuta_date_col,
            mapping.booking_date_col,
            mapping.amount_col,
            mapping.partner_iban_col,
            mapping.partner_name_col,
            mapping.description_col,
        }
        unmapped = {k: v for k, v in row.items() if k not in known_cols and v}

        return {
            "_csv_row_num": row_num,
            "account_id": account_id,
            "import_run_id": run_id,
            "valuta_date": valuta_date,
            "booking_date": booking_date,
            "amount": str(amount),
            "currency": "EUR",
            "text": get(mapping.description_col),
            "partner_name_raw": get(mapping.partner_name_col),
            "partner_iban_raw": get(mapping.partner_iban_col),
            "partner_account_raw": None,  # Legacy-Mapping hat keine Konto-Spalte
            "partner_blz_raw": None,
            "partner_bic_raw": None,
            "unmapped_data": unmapped if unmapped else None,
        }

    async def _bulk_insert_with_matching(
        self,
        rows: list[dict],
        mandant_id: UUID,
        current_run_id: UUID,
        account_id: UUID | None = None,
    ) -> tuple[int, int, list[ReviewItem], list[dict]]:
        """Insert JournalLines with partner matching.

        Duplikaterkennung erfolgt ausschließlich gegen bestehende DB-Einträge
        aus anderen Import-Runs. Innerhalb eines Runs gibt es per Definition
        keine Duplikate. Alle Felder (inkl. unmapped_data) müssen übereinstimmen.
        """
        if not rows:
            return 0, 0, [], []

        # Ausgeschlossene Identifier für das Konto laden (einmalig)
        excluded_ibans: frozenset[str] = frozenset()
        excluded_accounts: frozenset[str] = frozenset()
        if account_id is not None:
            account_svc = AccountService(self._session)
            excluded_ibans, excluded_accounts = await account_svc.get_excluded_sets(account_id)

        matcher = PartnerMatchingService(self._session)
        inserted = 0
        skipped = 0
        review_items: list[ReviewItem] = []
        duplicates: list[dict] = []

        for row in rows:
            # Kandidaten aus vorherigen Runs laden (current_run_id ausschließen)
            candidates_res = await self._session.exec(
                select(JournalLine).where(
                    JournalLine.account_id == row["account_id"],
                    JournalLine.import_run_id != current_run_id,  # type: ignore[arg-type]
                    JournalLine.valuta_date == row["valuta_date"],
                    JournalLine.booking_date == row["booking_date"],
                    JournalLine.amount == Decimal(row["amount"]),
                    JournalLine.currency == row["currency"],
                    JournalLine.text == row.get("text"),
                    JournalLine.partner_name_raw == row.get("partner_name_raw"),
                    JournalLine.partner_iban_raw == row.get("partner_iban_raw"),
                    JournalLine.partner_account_raw == row.get("partner_account_raw"),
                    JournalLine.partner_blz_raw == row.get("partner_blz_raw"),
                    JournalLine.partner_bic_raw == row.get("partner_bic_raw"),
                )
            )
            candidates = candidates_res.all()

            # unmapped_data (JSON) in Python vergleichen
            is_duplicate = any(
                c.unmapped_data == row.get("unmapped_data") for c in candidates
            )

            if is_duplicate:
                skipped += 1
                duplicates.append({
                    "row": row.get("_csv_row_num"),
                    "valuta_date": row["valuta_date"],
                    "booking_date": row["booking_date"],
                    "amount": row["amount"],
                    "text": row.get("text"),
                    "partner_name_raw": row.get("partner_name_raw"),
                })
                continue

            result = await matcher.match(
                mandant_id=mandant_id,
                iban_raw=row.get("partner_iban_raw"),
                name_raw=row.get("partner_name_raw"),
                account_raw=row.get("partner_account_raw"),
                blz_raw=row.get("partner_blz_raw"),
                bic_raw=row.get("partner_bic_raw"),
                excluded_ibans=excluded_ibans,
                excluded_accounts=excluded_accounts,
            )

            line = JournalLine(
                id=uuid4(),
                account_id=row["account_id"],
                import_run_id=row["import_run_id"],
                partner_id=result.partner_id,
                service_id=None,
                service_assignment_mode=None,
                valuta_date=row["valuta_date"],
                booking_date=row["booking_date"],
                amount=Decimal(row["amount"]),
                currency=row["currency"],
                text=row.get("text"),
                partner_name_raw=row.get("partner_name_raw"),
                partner_iban_raw=row.get("partner_iban_raw"),
                partner_account_raw=row.get("partner_account_raw"),
                partner_blz_raw=row.get("partner_blz_raw"),
                partner_bic_raw=row.get("partner_bic_raw"),
                unmapped_data=row.get("unmapped_data"),
            )
            self._session.add(line)
            try:
                await self._session.flush()
            except IntegrityError:
                await self._session.rollback()
                skipped += 1
                duplicates.append({
                    "row": row.get("_csv_row_num"),
                    "valuta_date": row["valuta_date"],
                    "booking_date": row["booking_date"],
                    "amount": row["amount"],
                    "text": row.get("text"),
                    "partner_name_raw": row.get("partner_name_raw"),
                    "_reason": "integrity_error",
                })
                continue

            from app.services.service import ServiceManagementService

            service_svc = ServiceManagementService(self._session)
            await service_svc.auto_assign_journal_line(mandant_id, line)

            ri = ReviewItemFactory.maybe_create(result, line, mandant_id)
            if ri is not None:
                review_items.append(ri)

            inserted += 1

        return inserted, skipped, review_items, duplicates

    async def _bulk_insert(self, rows: list[dict]) -> tuple[int, int]:
        """Insert rows, skipping exact duplicates (portable — works in SQLite and PostgreSQL)."""
        if not rows:
            return 0, 0

        inserted = 0
        skipped = 0
        for row in rows:
            existing = (
                await self._session.exec(
                    select(JournalLine).where(
                        JournalLine.account_id == row["account_id"],
                        JournalLine.valuta_date == row["valuta_date"],
                        JournalLine.booking_date == row["booking_date"],
                        JournalLine.amount == Decimal(row["amount"]),
                        JournalLine.partner_iban_raw == row.get("partner_iban_raw"),
                        JournalLine.partner_name_raw == row.get("partner_name_raw"),
                    )
                )
            ).first()
            if existing is not None:
                skipped += 1
                continue

            line = JournalLine(
                id=uuid4(),
                account_id=row["account_id"],
                import_run_id=row["import_run_id"],
                partner_id=None,
                valuta_date=row["valuta_date"],
                booking_date=row["booking_date"],
                amount=Decimal(row["amount"]),
                currency=row["currency"],
                text=row.get("text"),
                partner_name_raw=row.get("partner_name_raw"),
                partner_iban_raw=row.get("partner_iban_raw"),
                unmapped_data=row.get("unmapped_data"),
            )
            self._session.add(line)
            await self._session.flush()
            inserted += 1

        return inserted, skipped

    def _is_csv(self, file: UploadFile) -> bool:
        ct = (file.content_type or "").lower()
        return ct in ("text/csv", "application/csv") or (
            file.filename or ""
        ).lower().endswith(".csv")

    async def _load_mapping(self, account_id: UUID) -> ColumnMappingConfig | None:
        result = await self._session.exec(
            select(ColumnMappingConfig).where(ColumnMappingConfig.account_id == account_id)
        )
        return result.first()

    async def get_run(self, run_id: UUID, account_id: UUID) -> ImportRun:
        run = await self._session.get(ImportRun, run_id)
        if run is None or run.account_id != account_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import run not found")
        return run

    async def list_runs(
        self,
        account_id: UUID,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[ImportRun], int]:
        size = min(size, 100)
        offset = (page - 1) * size

        all_ids = (
            await self._session.exec(
                select(ImportRun.id).where(ImportRun.account_id == account_id)  # type: ignore[arg-type]
            )
        ).all()
        total = len(all_ids)

        items = (
            await self._session.exec(
                select(ImportRun)
                .where(ImportRun.account_id == account_id)
                .offset(offset)
                .limit(size)
            )
        ).all()

        return list(items), total
