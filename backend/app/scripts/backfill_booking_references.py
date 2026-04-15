"""Backfill Buchungsreferenz values from an updated CSV into journal_lines.

Usage:
    cd backend
    python -m app.scripts.backfill_booking_references --csv ../data/examples/file.csv --dry-run
    python -m app.scripts.backfill_booking_references --csv ../data/examples/file.csv --apply

Behavior:
    - Detects the account via the CSV column "Eigene IBAN".
    - Matches each CSV row against an existing journal line on the stable raw
      import fields.
    - Uses "Buchungs-Details" for the text match when present.
    - Falls back to "Zahlungsreferenz" when "Buchungs-Details" is empty.
    - Writes the CSV "Buchungsreferenz" into journal_lines.unmapped_data.

Guards:
    - Refuses to run when ENV=production.
    - Defaults to dry-run unless --apply is passed.
    - Aborts without writing if any row is unmatched, ambiguous, or would
      overwrite a different existing Buchungsreferenz.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlmodel import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.tenants.models import Account


MATCH_WITH_TEXT_QUERY = text(
    """
    SELECT jl.id
    FROM journal_lines jl
    WHERE jl.account_id = :account_id
      AND jl.valuta_date = :valuta_date
      AND jl.booking_date = :booking_date
      AND printf('%.2f', jl.amount) = :amount
      AND jl.currency = :currency
      AND jl.partner_name_raw IS :partner_name_raw
      AND jl.partner_iban_raw IS :partner_iban_raw
      AND jl.partner_account_raw IS :partner_account_raw
      AND jl.partner_blz_raw IS :partner_blz_raw
      AND jl.partner_bic_raw IS :partner_bic_raw
      AND jl.text IS :text_value
    ORDER BY jl.created_at, jl.id
    """
)


SELECT_UNMAPPED_DATA_QUERY = text(
    """
    SELECT unmapped_data
    FROM journal_lines
    WHERE id = :journal_line_id
    """
)


UPDATE_UNMAPPED_DATA_QUERY = text(
    """
    UPDATE journal_lines
    SET unmapped_data = :unmapped_data
    WHERE id = :journal_line_id
    """
)


@dataclass(slots=True)
class MatchPlanRow:
    line_number: int
    journal_line_id: UUID
    booking_reference: str
    match_strategy: str


@dataclass(slots=True)
class MatchFailure:
    line_number: int
    booking_reference: str
    reason: str


def _detect_encoding(raw: bytes) -> str:
    if raw[:2] in {b"\xff\xfe", b"\xfe\xff"}:
        return "utf-16"
    if raw[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def _detect_delimiter(text_value: str) -> str:
    sample = text_value[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        return dialect.delimiter
    except csv.Error:
        return ";"


def _normalize_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _normalize_iban(value: str | None) -> str | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    return normalized.replace(" ", "").upper()


def _parse_date(value: str) -> str:
    day, month, year = value.strip().split(".")
    return f"{year}-{month}-{day}"


def _parse_amount(value: str) -> str:
    normalized = value.strip().replace(".", "").replace(",", ".")
    return f"{Decimal(normalized):.2f}"


def _coerce_uuid(value: object) -> UUID:
    if isinstance(value, tuple) and len(value) == 1:
        return _coerce_uuid(value[0])
    if hasattr(value, "_mapping"):
        mapping = getattr(value, "_mapping")
        if len(mapping) == 1:
            return _coerce_uuid(next(iter(mapping.values())))
    if isinstance(value, UUID):
        return value
    if hasattr(value, "hex") and isinstance(getattr(value, "hex"), str):
        return UUID(hex=getattr(value, "hex"))

    text_value = str(value).strip()
    if len(text_value) == 32:
        return UUID(hex=text_value)
    return UUID(text_value)


def _coerce_unmapped_data(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        decoded = json.loads(value)
        if isinstance(decoded, dict):
            return dict(decoded)
    return {}


def _load_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    raw = csv_path.read_bytes()
    encoding = _detect_encoding(raw)
    text_value = raw.decode(encoding)
    delimiter = _detect_delimiter(text_value)
    reader = csv.DictReader(text_value.splitlines(), delimiter=delimiter)
    return [dict(row) for row in reader]


async def _resolve_accounts_by_iban(rows: list[dict[str, str]]) -> dict[str, UUID]:
    own_ibans = sorted(
        {
            iban
            for row in rows
            if (iban := _normalize_iban(row.get("Eigene IBAN"))) is not None
        }
    )
    if not own_ibans:
        raise RuntimeError("CSV enthält keine Werte in 'Eigene IBAN'.")

    async with AsyncSessionLocal() as session:
        result = await session.exec(select(Account).where(Account.iban.in_(own_ibans)))
        accounts = result.all()

        journal_account_rows = (
            await session.exec(
                text(
                    """
                    SELECT DISTINCT account_id
                    FROM journal_lines
                    ORDER BY account_id
                    """
                )
            )
        ).all()

    found = {_normalize_iban(account.iban): account.id for account in accounts if account.id is not None}
    missing = [iban for iban in own_ibans if iban not in found]
    if missing:
        journal_account_ids = [_coerce_uuid(account_id) for account_id in journal_account_rows]
        if len(journal_account_ids) == 1:
            fallback_account_id = journal_account_ids[0]
            for iban in missing:
                found[iban] = fallback_account_id
        else:
            raise RuntimeError(
                "Kein Konto für folgende Eigene-IBAN-Werte gefunden: " + ", ".join(missing)
            )
    return {iban: account_id for iban, account_id in found.items() if account_id is not None}


async def _match_row(
    session: Any,
    account_id: UUID,
    row: dict[str, str],
) -> tuple[MatchPlanRow | None, MatchFailure | None]:
    booking_reference = _normalize_text(row.get("Buchungsreferenz"))
    if booking_reference is None:
        return None, MatchFailure(0, "", "CSV-Zeile ohne Buchungsreferenz")

    params = {
        "account_id": account_id.hex,
        "valuta_date": _parse_date(row["Valutadatum"]),
        "booking_date": _parse_date(row["Buchungsdatum"]),
        "amount": _parse_amount(row["Betrag"]),
        "currency": (_normalize_text(row.get("Währung")) or "EUR")[:3].upper(),
        "partner_name_raw": _normalize_text(row.get("Partnername")),
        "partner_iban_raw": _normalize_text(row.get("Partner IBAN")),
        "partner_account_raw": _normalize_text(row.get("Partner Kontonummer")),
        "partner_blz_raw": _normalize_text(row.get("Bankleitzahl")),
        "partner_bic_raw": _normalize_text(row.get("BIC/SWIFT")),
    }

    strategies = []
    if (details := _normalize_text(row.get("Buchungs-Details"))) is not None:
        strategies.append(("booking-details", details))
    elif (payment_reference := _normalize_text(row.get("Zahlungsreferenz"))) is not None:
        strategies.append(("zahlungsreferenz", payment_reference))

    for strategy_name, text_value in strategies:
        result = await session.execute(MATCH_WITH_TEXT_QUERY, {**params, "text_value": text_value})
        matches = result.fetchall()
        if len(matches) == 1:
            journal_line_id = _coerce_uuid(matches[0])
            return MatchPlanRow(0, journal_line_id, booking_reference, strategy_name), None
        if len(matches) > 1:
            return None, MatchFailure(0, booking_reference, f"Mehrdeutiges Matching via {strategy_name}")

    return None, MatchFailure(0, booking_reference, "Kein eindeutiges Matching gefunden")


async def run_backfill(csv_path: Path, apply: bool) -> int:
    if settings.env == "production":
        print("ERROR: Script refused to run in production environment.", file=sys.stderr)
        return 1

    rows = _load_csv_rows(csv_path)
    account_ids_by_iban = await _resolve_accounts_by_iban(rows)

    plan_rows: list[MatchPlanRow] = []
    failures: list[MatchFailure] = []
    already_set = 0
    skipped_conflicts = 0
    updated = 0
    strategy_counts: dict[str, int] = {}
    planned_references_by_line: dict[UUID, str] = {}

    async with AsyncSessionLocal() as session:
        for line_number, row in enumerate(rows, start=2):
            own_iban = _normalize_iban(row.get("Eigene IBAN"))
            if own_iban is None:
                failures.append(MatchFailure(line_number, "", "Eigene IBAN fehlt"))
                continue

            plan_row, failure = await _match_row(session, account_ids_by_iban[own_iban], row)
            if failure is not None:
                failure.line_number = line_number
                if not failure.booking_reference:
                    failure.booking_reference = _normalize_text(row.get("Buchungsreferenz")) or ""
                failures.append(failure)
                continue

            assert plan_row is not None
            plan_row.line_number = line_number

            previous_planned_reference = planned_references_by_line.get(plan_row.journal_line_id)
            if previous_planned_reference is not None:
                if previous_planned_reference != plan_row.booking_reference:
                    skipped_conflicts += 1
                continue

            current_unmapped_row = (
                await session.execute(
                    SELECT_UNMAPPED_DATA_QUERY,
                    {"journal_line_id": plan_row.journal_line_id.hex},
                )
            ).fetchone()
            if current_unmapped_row is None:
                failures.append(
                    MatchFailure(
                        line_number,
                        plan_row.booking_reference,
                        "Gematchte journal_line existiert nicht mehr",
                    )
                )
                continue

            unmapped_data = _coerce_unmapped_data(current_unmapped_row[0])
            existing_reference = _normalize_text(unmapped_data.get("Buchungsreferenz"))
            if existing_reference is not None and existing_reference != plan_row.booking_reference:
                failures.append(
                    MatchFailure(
                        line_number,
                        plan_row.booking_reference,
                        f"Konflikt mit bestehender Buchungsreferenz '{existing_reference}'",
                    )
                )
                continue

            plan_rows.append(plan_row)
            planned_references_by_line[plan_row.journal_line_id] = plan_row.booking_reference
            strategy_counts[plan_row.match_strategy] = strategy_counts.get(plan_row.match_strategy, 0) + 1

            if existing_reference == plan_row.booking_reference:
                already_set += 1
                continue

            unmapped_data["Buchungsreferenz"] = plan_row.booking_reference
            await session.execute(
                UPDATE_UNMAPPED_DATA_QUERY,
                {
                    "journal_line_id": plan_row.journal_line_id.hex,
                    "unmapped_data": json.dumps(unmapped_data, ensure_ascii=True, sort_keys=True),
                },
            )
            updated += 1

        if failures:
            print(f"FAILURES {len(failures)}")
            for failure in failures[:20]:
                print(
                    f"  line {failure.line_number}: {failure.booking_reference or '<leer>'} -> {failure.reason}"
                )
            print("Aborting without writing.")
            await session.rollback()
            return 1

        if apply:
            await session.commit()
        else:
            await session.rollback()

    print(f"ROWS {len(rows)}")
    print(f"MATCHED {len(plan_rows)}")
    print(f"UPDATED {updated}")
    print(f"ALREADY_SET {already_set}")
    print(f"SKIPPED_CONFLICTS {skipped_conflicts}")
    print(f"MODE {'apply' if apply else 'dry-run'}")
    for strategy_name in sorted(strategy_counts):
        print(f"STRATEGY {strategy_name} {strategy_counts[strategy_name]}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Buchungsreferenz into journal_lines.")
    parser.add_argument("--csv", required=True, help="Pfad zur CSV-Datei mit Buchungsreferenz")
    parser.add_argument("--apply", action="store_true", help="Änderungen wirklich schreiben")
    parser.add_argument("--dry-run", action="store_true", help="Nur prüfen, nichts schreiben")
    args = parser.parse_args()

    apply = args.apply and not args.dry_run
    exit_code = asyncio.run(run_backfill(Path(args.csv), apply=apply))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()