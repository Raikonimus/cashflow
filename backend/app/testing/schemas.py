from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AssignmentTestJournalLine(BaseModel):
    id: UUID
    account_id: UUID
    import_run_id: UUID
    partner_id: UUID | None
    service_id: UUID | None
    service_assignment_mode: str | None
    valuta_date: str
    booking_date: str
    amount: Decimal
    currency: str
    text: str | None
    partner_name_raw: str | None
    partner_iban_raw: str | None
    partner_account_raw: str | None
    partner_blz_raw: str | None
    partner_bic_raw: str | None
    unmapped_data: Any | None
    created_at: Any


class AssignmentMismatchItem(BaseModel):
    reason_code: str
    reason_text: str
    expected_outcome: str
    expected_partner_id: UUID | None
    expected_partner_name: str | None
    current_partner_id: UUID | None
    current_partner_name: str | None
    current_service_id: UUID | None
    current_service_name: str | None
    journal_line: AssignmentTestJournalLine


class PartnerAssignmentTestResponse(BaseModel):
    total_checked: int
    mismatches: list[AssignmentMismatchItem]
