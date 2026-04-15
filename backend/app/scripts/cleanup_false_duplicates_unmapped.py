"""Cleanup false import duplicates caused only by enriched unmapped_data.

Usage:
    cd backend
    python -m app.scripts.cleanup_false_duplicates_unmapped --dry-run
    python -m app.scripts.cleanup_false_duplicates_unmapped --apply

Behavior:
    - Finds journal_lines that are equal on the active import duplicate key except
      for unmapped_data.
    - Keeps exactly one baseline row per group when available. Baseline means
      unmapped_data is SQL NULL or the JSON literal null.
    - Reassigns review_items from deleted rows to the kept row.
    - If a review item with the same item_type already exists on the kept row,
      the duplicate review item is deleted instead of reassigned.

Guards:
    - Refuses to run when ENV=production.
    - Defaults to dry-run unless --apply is passed.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text, update
from sqlmodel import delete, select

from app.imports.models import ImportRun, JournalLine, ReviewItem


@dataclass(slots=True)
class CleanupPlanRow:
    group_key: str
    journal_line_id: UUID
    keep_journal_line_id: UUID
    import_run_id: UUID
    action: str
    filename: str
    valuta_date: str
    booking_date: str
    amount: str
    currency: str
    text: str | None
    unmapped_data: str | None
    created_at: str


PLAN_QUERY = text(
    """
        WITH grouped AS (
            SELECT
                jl.account_id,
                jl.valuta_date,
                jl.booking_date,
                ROUND(jl.amount, 2) AS amount_2,
                jl.currency,
                jl.text,
                jl.partner_name_raw,
                jl.partner_iban_raw,
                jl.partner_account_raw,
                jl.partner_blz_raw,
                jl.partner_bic_raw,
                COUNT(*) AS row_count,
                COUNT(DISTINCT COALESCE(CAST(jl.unmapped_data AS TEXT), '__NULL__')) AS unmapped_variants
            FROM journal_lines jl
            GROUP BY
                jl.account_id,
                jl.valuta_date,
                jl.booking_date,
                ROUND(jl.amount, 2),
                jl.currency,
                jl.text,
                jl.partner_name_raw,
                jl.partner_iban_raw,
                jl.partner_account_raw,
                jl.partner_blz_raw,
                jl.partner_bic_raw
            HAVING COUNT(*) > 1
                AND COUNT(DISTINCT COALESCE(CAST(jl.unmapped_data AS TEXT), '__NULL__')) > 1
        ),
        affected AS (
      SELECT
        jl.id,
        jl.import_run_id,
        ir.filename,
        jl.account_id,
        jl.valuta_date,
        jl.booking_date,
        ROUND(jl.amount, 2) AS amount_2,
        jl.currency,
        jl.text,
        jl.partner_name_raw,
        jl.partner_iban_raw,
        jl.partner_account_raw,
        jl.partner_blz_raw,
        jl.partner_bic_raw,
        CASE
          WHEN jl.unmapped_data IS NULL OR jl.unmapped_data = 'null' THEN 0
          ELSE 1
        END AS enriched_rank,
        CAST(jl.unmapped_data AS TEXT) AS unmapped_data_text,
        CAST(jl.created_at AS TEXT) AS created_at_text,
        printf(
          '%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s',
          jl.account_id,
          jl.valuta_date,
          jl.booking_date,
          ROUND(jl.amount, 2),
          COALESCE(jl.currency, ''),
          COALESCE(jl.text, ''),
          COALESCE(jl.partner_name_raw, ''),
          COALESCE(jl.partner_iban_raw, ''),
          COALESCE(jl.partner_account_raw, ''),
          COALESCE(jl.partner_blz_raw, ''),
          COALESCE(jl.partner_bic_raw, '')
        ) AS group_key,
        ROW_NUMBER() OVER (
          PARTITION BY
            jl.account_id,
            jl.valuta_date,
            jl.booking_date,
            ROUND(jl.amount, 2),
            jl.currency,
            jl.text,
            jl.partner_name_raw,
            jl.partner_iban_raw,
            jl.partner_account_raw,
            jl.partner_blz_raw,
            jl.partner_bic_raw
          ORDER BY
            CASE
              WHEN jl.unmapped_data IS NULL OR jl.unmapped_data = 'null' THEN 0
              ELSE 1
            END,
            jl.created_at,
            jl.id
        ) AS keep_rank,
                grouped.row_count,
                grouped.unmapped_variants
      FROM journal_lines jl
      LEFT JOIN import_runs ir ON ir.id = jl.import_run_id
            JOIN grouped
                ON grouped.account_id = jl.account_id
             AND grouped.valuta_date = jl.valuta_date
             AND grouped.booking_date = jl.booking_date
             AND grouped.amount_2 = ROUND(jl.amount, 2)
             AND grouped.currency IS jl.currency
             AND grouped.text IS jl.text
             AND grouped.partner_name_raw IS jl.partner_name_raw
             AND grouped.partner_iban_raw IS jl.partner_iban_raw
             AND grouped.partner_account_raw IS jl.partner_account_raw
             AND grouped.partner_blz_raw IS jl.partner_blz_raw
             AND grouped.partner_bic_raw IS jl.partner_bic_raw
    ),
    dup_groups AS (
      SELECT *
      FROM affected
    ),
    keeper_map AS (
      SELECT group_key, id AS keep_id
      FROM dup_groups
      WHERE keep_rank = 1
    )
    SELECT
      dg.group_key,
      dg.id,
      km.keep_id,
    dg.import_run_id,
      CASE WHEN dg.keep_rank = 1 THEN 'keep' ELSE 'delete' END AS action,
      COALESCE(dg.filename, '') AS filename,
      dg.valuta_date,
      dg.booking_date,
      CAST(dg.amount_2 AS TEXT) AS amount,
      COALESCE(dg.currency, '') AS currency,
      dg.text,
      dg.unmapped_data_text,
      dg.created_at_text
    FROM dup_groups dg
    JOIN keeper_map km ON km.group_key = dg.group_key
    ORDER BY dg.valuta_date, dg.booking_date, dg.amount_2, dg.text, dg.created_at_text, dg.id
    """
)


async def build_cleanup_plan(session: Any) -> list[CleanupPlanRow]:
    rows = (await session.exec(PLAN_QUERY)).mappings().all()
    return [
        CleanupPlanRow(
            group_key=row["group_key"],
            journal_line_id=UUID(str(row["id"])),
            keep_journal_line_id=UUID(str(row["keep_id"])),
            import_run_id=UUID(str(row["import_run_id"])),
            action=str(row["action"]),
            filename=str(row["filename"]),
            valuta_date=str(row["valuta_date"]),
            booking_date=str(row["booking_date"]),
            amount=str(row["amount"]),
            currency=str(row["currency"]),
            text=row["text"],
            unmapped_data=row["unmapped_data_text"],
            created_at=str(row["created_at_text"]),
        )
        for row in rows
    ]


def _rewrite_review_context(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return _rewrite_review_context_dict(value, replacements)
    if isinstance(value, list):
        return [_rewrite_review_context(item, replacements) for item in value]
    return value


def _rewrite_review_context_dict(
    value: dict[Any, Any], replacements: dict[str, str]
) -> dict[Any, Any]:
    updated: dict[Any, Any] = {}
    for key, nested_value in value.items():
        updated[key] = _rewrite_review_context_entry(key, nested_value, replacements)
    return updated


def _rewrite_review_context_entry(
    key: Any, nested_value: Any, replacements: dict[str, str]
) -> Any:
    if key == "journal_line_id" and isinstance(nested_value, str):
        return replacements.get(nested_value, nested_value)
    if key == "current_journal_line_ids" and isinstance(nested_value, list):
        return _rewrite_review_line_id_list(nested_value, replacements)
    return _rewrite_review_context(nested_value, replacements)


def _rewrite_review_line_id_list(
    values: list[Any], replacements: dict[str, str]
) -> list[str]:
    rewritten_ids: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        rewritten_item = replacements.get(item, item)
        if rewritten_item in seen:
            continue
        seen.add(rewritten_item)
        rewritten_ids.append(rewritten_item)
    return rewritten_ids


async def _recount_import_runs(session: Any, import_run_ids: set[UUID]) -> None:
    if not import_run_ids:
        return

    for import_run_id in import_run_ids:
        row_count = len(
            (
                await session.exec(
                    select(JournalLine.id).where(JournalLine.import_run_id == import_run_id)
                )
            ).all()
        )
        await session.exec(
            update(ImportRun.__table__)
            .where(ImportRun.__table__.c.id == import_run_id)
            .values(row_count=row_count)
        )


async def apply_cleanup_plan(session: Any, plan: list[CleanupPlanRow]) -> dict[str, int]:
    keep_rows = [row for row in plan if row.action == "keep"]
    delete_rows = [row for row in plan if row.action == "delete"]
    replacements = {
        str(row.journal_line_id): str(row.keep_journal_line_id)
        for row in delete_rows
    }
    affected_import_run_ids = {row.import_run_id for row in plan}

    deleted_review_items = 0
    moved_review_items = 0
    updated_review_contexts = 0

    for row in delete_rows:
        loser_reviews = (
            await session.exec(select(ReviewItem).where(ReviewItem.journal_line_id == row.journal_line_id))
        ).all()
        for review in loser_reviews:
            existing = (
                await session.exec(
                    select(ReviewItem).where(
                        ReviewItem.journal_line_id == row.keep_journal_line_id,
                        ReviewItem.item_type == review.item_type,
                    )
                )
            ).first()
            if existing is not None:
                await session.delete(review)
                deleted_review_items += 1
                continue
            review.journal_line_id = row.keep_journal_line_id
            review.context = _rewrite_review_context(review.context, replacements)
            session.add(review)
            moved_review_items += 1
            updated_review_contexts += 1

    delete_ids = [row.journal_line_id for row in delete_rows]
    if delete_ids:
        await session.exec(delete(JournalLine).where(JournalLine.__table__.c.id.in_(delete_ids)))

    await _recount_import_runs(session, affected_import_run_ids)

    await session.commit()
    return {
        "groups": len(keep_rows),
        "kept_journal_lines": len(keep_rows),
        "deleted_journal_lines": len(delete_rows),
        "moved_review_items": moved_review_items,
        "deleted_review_items": deleted_review_items,
        "updated_review_contexts": updated_review_contexts,
    }


def export_plan_csv(path: Path, plan: list[CleanupPlanRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "group_key",
                "journal_line_id",
                "keep_journal_line_id",
                "import_run_id",
                "action",
                "filename",
                "valuta_date",
                "booking_date",
                "amount",
                "currency",
                "text",
                "unmapped_data",
                "created_at",
            ]
        )
        for row in plan:
            writer.writerow(
                [
                    row.group_key,
                    str(row.journal_line_id),
                    str(row.keep_journal_line_id),
                    str(row.import_run_id),
                    row.action,
                    row.filename,
                    row.valuta_date,
                    row.booking_date,
                    row.amount,
                    row.currency,
                    row.text or "",
                    row.unmapped_data or "",
                    row.created_at,
                ]
            )


def summarize_plan(plan: list[CleanupPlanRow]) -> dict[str, int]:
    groups = len({row.group_key for row in plan})
    keep_count = sum(1 for row in plan if row.action == "keep")
    delete_count = sum(1 for row in plan if row.action == "delete")
    return {
        "groups": groups,
        "kept_journal_lines": keep_count,
        "deleted_journal_lines": delete_count,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cleanup false duplicates caused only by unmapped_data enrichment."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Apply the cleanup transaction.")
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only. This is the default when no mode is provided.",
    )
    parser.add_argument(
        "--export-csv",
        default="false_duplicates_unmapped_cleanup_plan.csv",
        help="Path for the generated cleanup plan CSV.",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    from app.core.config import settings

    if settings.env == "production":
        print("ERROR: Cleanup script refused to run in production environment.", file=sys.stderr)
        sys.exit(1)

    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        plan = await build_cleanup_plan(session)
        summary = summarize_plan(plan)
        export_plan_csv(Path(args.export_csv), plan)

        print(f"INFO: Found {summary['groups']} affected duplicate groups.")
        print(f"INFO: Keep {summary['kept_journal_lines']} journal lines.")
        print(f"INFO: Delete {summary['deleted_journal_lines']} journal lines.")
        print(f"INFO: Exported cleanup plan to {args.export_csv}.")

        if not args.apply:
            print("INFO: Dry-run only. No database changes applied.")
            return

        result = await apply_cleanup_plan(session, plan)
        print(f"INFO: Deleted {result['deleted_journal_lines']} journal lines.")
        print(f"INFO: Moved {result['moved_review_items']} review items.")
        print(f"INFO: Deleted {result['deleted_review_items']} duplicate review items.")
        print(f"INFO: Updated {result['updated_review_contexts']} review contexts.")


def main() -> None:
    asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    main()