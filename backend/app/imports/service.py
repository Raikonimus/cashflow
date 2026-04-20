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

# Internal import metadata stored alongside user-visible unmapped_data.
# It persists the raw CSV values needed for duplicate detection, but should
# not leak back into user-facing API payloads.
SOURCE_VALUES_KEY = "_cashflow_source_values"


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


def _normalize_source_value(raw: str | None) -> str:
    return (raw or "").strip()


def _merge_source_values_into_unmapped_data(
    unmapped_data: dict[str, str] | None,
    source_values: dict[str, str],
) -> dict[str, object] | None:
    if not source_values:
        return unmapped_data

    merged: dict[str, object] = dict(unmapped_data or {})
    merged[SOURCE_VALUES_KEY] = source_values
    return merged


def _extract_stored_source_values(unmapped_data: object) -> dict[str, str]:
    if not isinstance(unmapped_data, dict):
        return {}

    extracted: dict[str, str] = {
        key: value
        for key, value in unmapped_data.items()
        if isinstance(key, str) and key != SOURCE_VALUES_KEY and isinstance(value, str)
    }

    raw_values = unmapped_data.get(SOURCE_VALUES_KEY)
    if not isinstance(raw_values, dict):
        return extracted

    for key, value in raw_values.items():
        if isinstance(key, str) and isinstance(value, str):
            extracted[key] = value
    return extracted


def _build_duplicate_signature(
    source_values: dict[str, str],
    duplicate_sources: list[str],
) -> tuple[tuple[str, str], ...] | None:
    """Erstellt einen sortierten Fingerabdruck einer Buchungszeile für die Duplikaterkennung.

    Gibt ein stabiles, vergleichbares Tupel aus (Spaltenname, Rohwert)-Paaren zurück,
    das ausschließlich die konfigurierten ``duplicate_check``-Spalten enthält.

    Gibt ``None`` zurück wenn:
    - keine Vergleichsspalten konfiguriert sind, oder
    - mindestens eine Vergleichsspalte im aktuellen Zeilenwerte-Dict fehlt.

    In beiden Fällen wird die Zeile nicht als Duplikat behandelt.
    """
    if not duplicate_sources:
        return None
    if any(source not in source_values for source in duplicate_sources):
        return None
    return tuple(sorted((source, source_values[source]) for source in duplicate_sources))


def _assignment_duplicate_sources(assignments: list[dict]) -> list[str]:
    sources = [
        assignment.get("source", "")
        for assignment in assignments
        if assignment.get("duplicate_check") and assignment.get("source")
    ]
    return sorted(dict.fromkeys(str(source) for source in sources))


def _legacy_duplicate_sources(mapping: ColumnMappingConfig) -> list[str]:
    sources = [
        mapping.valuta_date_col,
        mapping.booking_date_col,
        mapping.amount_col,
        mapping.partner_iban_col,
        mapping.partner_name_col,
        mapping.description_col,
    ]
    return [source for source in sources if source]


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

        decoded = await self._decode_upload(file)
        reader = self._build_csv_reader(decoded, mapping)
        self._validate_duplicate_check_columns(reader.fieldnames, mapping)
        lines_to_insert, errors = self._collect_lines_to_insert(reader, mapping, run.id, account_id)

        inserted, skipped, review_items, duplicates, zero_skipped = await self._bulk_insert_with_matching(
            lines_to_insert, mandant_id, run.id, account_id
        )
        self._finalize_run(run, inserted, skipped, errors, duplicates, zero_skipped)

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

    async def _decode_upload(self, file: UploadFile) -> str:
        content = await file.read()
        encoding = _detect_encoding(content)
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            return content.decode('utf-8', errors='replace')

    def _build_csv_reader(
        self,
        decoded: str,
        mapping: ColumnMappingConfig,
    ) -> csv.DictReader:
        effective_delimiter = _detect_delimiter(decoded, fallback=mapping.delimiter or ";")
        return csv.DictReader(io.StringIO(decoded), delimiter=effective_delimiter)

    def _collect_lines_to_insert(
        self,
        reader: csv.DictReader,
        mapping: ColumnMappingConfig,
        run_id: UUID,
        account_id: UUID,
    ) -> tuple[list[dict], list[dict]]:
        lines_to_insert: list[dict] = []
        errors: list[dict] = []

        for row_num, row in enumerate(reader, start=1 + (mapping.skip_rows or 0)):
            if row_num <= (mapping.skip_rows or 0):
                continue

            try:
                line_data = self._map_row(row, mapping, run_id, account_id, row_num)
                if line_data is None:
                    errors.append({"row": row_num, "error": "required field missing after mapping"})
                    continue
                lines_to_insert.append(line_data)
            except (ValueError, InvalidOperation) as exc:
                errors.append({"row": row_num, "error": str(exc)})

        return lines_to_insert, errors

    def _finalize_run(
        self,
        run: ImportRun,
        inserted: int,
        skipped: int,
        errors: list[dict],
        duplicates: list[dict],
        zero_skipped: int = 0,
    ) -> None:
        run.row_count = inserted
        run.skipped_count = skipped
        run.error_count = len(errors)
        run.completed_at = utcnow()

        details: dict = {}
        if errors:
            details["parse_errors"] = errors
        if duplicates:
            details["duplicates"] = duplicates
        if zero_skipped:
            details["zero_amount_skipped"] = zero_skipped

        if errors and inserted == 0 and skipped == 0 and not duplicates:
            run.status = ImportStatus.failed.value
        else:
            run.status = ImportStatus.completed.value

        run.error_details = details if details else None

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

        def get_values(target: str) -> list[str]:
            sources = by_target.get(target, [])
            parts = [row.get(s, "").strip() for s in sources]
            return [part for part in parts if part]

        def get_concat(target: str) -> str | None:
            values = get_values(target)
            return "\n".join(values) if values else None

        def get_first(target: str) -> str | None:
            values = get_values(target)
            return values[0] if values else None

        valuta_raw = get_first("valuta_date")
        booking_raw = get_first("booking_date")
        amount_raw = get_first("amount")

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
        source_values = {
            source: _normalize_source_value(row.get(source))
            for source in assigned_sources
            if source
        }
        duplicate_sources = _assignment_duplicate_sources(assignments)

        return {
            "_csv_row_num": row_num,
            "_duplicate_sources": duplicate_sources,
            "_duplicate_signature": _build_duplicate_signature(source_values, duplicate_sources),
            "account_id": account_id,
            "import_run_id": run_id,
            "valuta_date": valuta_date,
            "booking_date": booking_date,
            "amount": str(amount),
            "currency": (get_first("currency") or "EUR").strip().upper()[:3],
            "text": get_concat("description"),
            "partner_name_raw": get_concat("partner_name"),
            "partner_iban_raw": get_concat("partner_iban"),
            "partner_account_raw": get_concat("partner_account"),
            "partner_blz_raw": get_concat("partner_blz"),
            "partner_bic_raw": get_concat("partner_bic"),
            "unmapped_data": _merge_source_values_into_unmapped_data(
                unmapped if unmapped else None,
                source_values,
            ),
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
        source_values = {
            source: _normalize_source_value(row.get(source))
            for source in _legacy_duplicate_sources(mapping)
        }
        duplicate_sources = list(source_values.keys())

        return {
            "_csv_row_num": row_num,
            "_duplicate_sources": duplicate_sources,
            "_duplicate_signature": _build_duplicate_signature(source_values, duplicate_sources),
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
            "unmapped_data": _merge_source_values_into_unmapped_data(
                unmapped if unmapped else None,
                source_values,
            ),
        }

    async def _bulk_insert_with_matching(
        self,
        rows: list[dict],
        mandant_id: UUID,
        current_run_id: UUID,
        account_id: UUID | None = None,
    ) -> tuple[int, int, list[ReviewItem], list[dict], int]:
        """Insert JournalLines with partner matching.

        Duplikaterkennung erfolgt ausschließlich gegen bestehende DB-Einträge
        aus anderen Import-Runs. Innerhalb eines Runs gibt es per Definition
        keine Duplikate.

        Verglichen werden nur die CSV-Quellspalten, die in der
        Spaltenkonfiguration mit ``duplicate_check=true`` markiert sind.
        Die zugehörigen Rohwerte werden intern in ``_cashflow_source_values``
        gespeichert; für Legacy-Zeilen ohne diesen Block wird auf top-level
        String-Werte in ``unmapped_data`` zurückgefallen.
        """
        if not rows:
            return 0, 0, [], [], 0

        # Ausgeschlossene Identifier für das Konto laden (einmalig)
        excluded_ibans: frozenset[str] = frozenset()
        excluded_accounts: frozenset[str] = frozenset()
        if account_id is not None:
            account_svc = AccountService(self._session)
            excluded_ibans, excluded_accounts = await account_svc.get_excluded_sets(account_id)

        matcher = PartnerMatchingService(self._session)
        inserted = 0
        skipped = 0
        zero_skipped = 0
        review_items: list[ReviewItem] = []
        duplicates: list[dict] = []
        existing_rows: list[JournalLine] = []
        if account_id is not None:
            existing_rows = (
                await self._session.exec(
                    select(JournalLine).where(
                        JournalLine.account_id == account_id,
                        JournalLine.import_run_id != current_run_id,  # type: ignore[arg-type]
                    )
                )
            ).all()

        for row in rows:
            # Buchungszeilen mit Betrag 0.00 werden ignoriert
            if Decimal(row["amount"]) == Decimal("0"):
                skipped += 1
                zero_skipped += 1
                continue

            duplicate_sources = row.get("_duplicate_sources", [])
            current_signature = row.get("_duplicate_signature")
            is_duplicate = False
            if current_signature is not None and duplicate_sources:
                is_duplicate = any(
                    _build_duplicate_signature(
                        _extract_stored_source_values(candidate.unmapped_data),
                        duplicate_sources,
                    )
                    == current_signature
                    for candidate in existing_rows
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
                text_raw=row.get("text"),
                excluded_ibans=excluded_ibans,
                excluded_accounts=excluded_accounts,
            )

            line = JournalLine(
                id=uuid4(),
                account_id=row["account_id"],
                import_run_id=row["import_run_id"],
                partner_id=result.partner_id,
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

            existing_rows.append(line)

            from app.services.service import ServiceManagementService

            service_svc = ServiceManagementService(self._session)
            await service_svc.auto_assign_journal_line(mandant_id, line)

            ri = ReviewItemFactory.maybe_create(result, line, mandant_id)
            if ri is not None:
                review_items.append(ri)

            inserted += 1

        return inserted, skipped, review_items, duplicates, zero_skipped

    def _validate_duplicate_check_columns(
        self,
        fieldnames: list[str] | None,
        mapping: ColumnMappingConfig,
    ) -> None:
        assignments = mapping.column_assignments or []
        if not assignments:
            return

        required_sources = _assignment_duplicate_sources(assignments)
        if not required_sources:
            return

        available = set(fieldnames or [])
        missing = [source for source in required_sources if source not in available]
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"CSV is missing duplicate-check columns: {missing_list}",
            )

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
