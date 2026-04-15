from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import select

from app.imports.models import ImportRun, JournalLine, ReviewItem
from app.scripts.cleanup_false_duplicates_unmapped import (
    apply_cleanup_plan,
    build_cleanup_plan,
    summarize_plan,
)


@pytest.mark.asyncio
async def test_cleanup_plan_keeps_baseline_and_moves_reviews(db_session):
    base_group = {
        "account_id": uuid4(),
        "valuta_date": "2026-03-20",
        "booking_date": "2026-03-20",
        "amount": Decimal("-20.00"),
        "currency": "EUR",
        "text": "E-COMM 20,00 DE K2 19.03. 14:09 SIPGATE DUSSELDORF 40217 280",
        "partner_name_raw": "SIPGATE",
        "partner_iban_raw": None,
        "partner_account_raw": "40100101600",
        "partner_blz_raw": "20111",
        "partner_bic_raw": None,
    }

    baseline_run = ImportRun(
        account_id=base_group["account_id"],
        mandant_id=uuid4(),
        user_id=uuid4(),
        filename="baseline.csv",
        status="completed",
    )
    enriched_run = ImportRun(
        account_id=base_group["account_id"],
        mandant_id=baseline_run.mandant_id,
        user_id=baseline_run.user_id,
        filename="enriched.csv",
        status="completed",
    )
    db_session.add(baseline_run)
    db_session.add(enriched_run)
    await db_session.commit()
    await db_session.refresh(baseline_run)
    await db_session.refresh(enriched_run)

    keep_line = JournalLine(import_run_id=baseline_run.id, unmapped_data=None, **base_group)
    extra_baseline = JournalLine(import_run_id=baseline_run.id, unmapped_data="null", **base_group)
    enriched_line = JournalLine(
        import_run_id=enriched_run.id,
        unmapped_data={"Eigene IBAN": "AT112011184376189300"},
        **base_group,
    )
    db_session.add(keep_line)
    db_session.add(extra_baseline)
    db_session.add(enriched_line)
    await db_session.commit()
    await db_session.refresh(keep_line)
    await db_session.refresh(extra_baseline)
    await db_session.refresh(enriched_line)

    review = ReviewItem(
        mandant_id=baseline_run.mandant_id,
        item_type="service_assignment",
        journal_line_id=enriched_line.id,
        context={
            "current_journal_line_ids": [str(enriched_line.id), str(extra_baseline.id)],
            "journal_line_id": str(enriched_line.id),
        },
    )
    db_session.add(review)
    await db_session.commit()

    plan = await build_cleanup_plan(db_session)
    summary = summarize_plan(plan)

    assert summary == {
        "groups": 1,
        "kept_journal_lines": 1,
        "deleted_journal_lines": 2,
    }
    keep_rows = [row for row in plan if row.action == "keep"]
    delete_rows = [row for row in plan if row.action == "delete"]
    assert len(keep_rows) == 1
    assert keep_rows[0].journal_line_id == keep_line.id
    assert {row.journal_line_id for row in delete_rows} == {extra_baseline.id, enriched_line.id}

    result = await apply_cleanup_plan(db_session, plan)
    assert result["groups"] == 1
    assert result["deleted_journal_lines"] == 2
    assert result["moved_review_items"] == 1
    assert result["deleted_review_items"] == 0
    assert result["updated_review_contexts"] == 1

    remaining_lines = (await db_session.exec(select(JournalLine))).all()
    assert [line.id for line in remaining_lines] == [keep_line.id]

    await db_session.refresh(baseline_run)
    await db_session.refresh(enriched_run)
    assert baseline_run.row_count == 1
    assert enriched_run.row_count == 0

    remaining_review = (await db_session.exec(select(ReviewItem))).one()
    assert remaining_review.journal_line_id == keep_line.id
    assert remaining_review.context == {
        "current_journal_line_ids": [str(keep_line.id)],
        "journal_line_id": str(keep_line.id),
    }