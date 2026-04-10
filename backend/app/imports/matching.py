"""Partner matching service for import pipeline.

Matches a journal line's IBAN/name against known active partners.
Produces a PartnerMatchResult and, when appropriate, a ReviewItem
(ADR-011: inactive partners are ignored; ADR-012: ReviewItem only
when a name-only match exists alongside a raw IBAN value).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.imports.models import JournalLine, ReviewItem, utcnow
from app.partners.models import Partner, PartnerAccount, PartnerIban, PartnerName


def _normalize_iban(raw: str) -> str:
    return raw.replace(" ", "").upper()


def _normalize_account(raw: str) -> str:
    """Entfernt führende Nullen und Leerzeichen für konsistenten Vergleich."""
    return raw.strip().lstrip("0") or raw.strip()


class MatchOutcome(StrEnum):
    iban_match = "iban_match"
    account_match = "account_match"   # BLZ + Kontonummer
    name_match = "name_match"
    new_partner = "new_partner"


@dataclass
class PartnerMatchResult:
    partner_id: UUID
    outcome: MatchOutcome
    review_context: dict | None = field(default=None)


class PartnerMatchingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def match(
        self,
        mandant_id: UUID,
        iban_raw: str | None,
        name_raw: str | None,
        account_raw: str | None = None,
        blz_raw: str | None = None,
        bic_raw: str | None = None,
        excluded_ibans: frozenset[str] = frozenset(),
        excluded_accounts: frozenset[str] = frozenset(),
    ) -> PartnerMatchResult:
        """Match to a partner; create a new one if no match is found.

        Reihenfolge:
        1. IBAN-Lookup (übersprungen wenn IBAN in excluded_ibans)
        2. BLZ + Kontonummer Lookup (übersprungen wenn Konto in excluded_accounts)
        3. Name-Lookup
        4. Neuen Partner anlegen

        Nach dem Match werden fehlende Identifier automatisch beim Partner ergänzt
        (IBAN wenn noch nicht vorhanden, Kontonummer wenn noch nicht vorhanden).
        """

        # --- Step 1: IBAN lookup ---
        if iban_raw:
            normalized = _normalize_iban(iban_raw)
            if normalized not in excluded_ibans:
                row = (
                    await self._session.exec(
                        select(PartnerIban)
                        .join(Partner, Partner.id == PartnerIban.partner_id)  # type: ignore[arg-type]
                        .where(
                            PartnerIban.iban == normalized,
                            Partner.mandant_id == mandant_id,
                            Partner.is_active == True,  # noqa: E712
                        )
                    )
                ).first()
                if row is not None:
                    partner_id = row.partner_id
                    # Auto-Anreicherung: Kontonummer + BIC ergänzen wenn noch nicht bekannt
                    await self._maybe_add_account(partner_id, account_raw, blz_raw, bic_raw)
                    return PartnerMatchResult(partner_id=partner_id, outcome=MatchOutcome.iban_match)

        # --- Step 2: BLZ + Kontonummer Lookup ---
        if account_raw:
            normalized_acct = _normalize_account(account_raw)
            if normalized_acct not in excluded_accounts:
                acct_row = (
                    await self._session.exec(
                        select(PartnerAccount)
                        .join(Partner, Partner.id == PartnerAccount.partner_id)  # type: ignore[arg-type]
                        .where(
                            PartnerAccount.account_number == normalized_acct,
                            Partner.mandant_id == mandant_id,
                            Partner.is_active == True,  # noqa: E712
                        )
                    )
                ).first()
                if acct_row is not None:
                    partner_id = acct_row.partner_id
                    # Auto-Anreicherung: IBAN + BIC ergänzen wenn noch nicht bekannt
                    await self._maybe_add_iban(partner_id, iban_raw)
                    await self._maybe_update_bic(acct_row, bic_raw)
                    return PartnerMatchResult(partner_id=partner_id, outcome=MatchOutcome.account_match)

        # --- Step 3: Name lookup ---
        if name_raw:
            row_name = (
                await self._session.exec(
                    select(Partner)
                    .join(PartnerName, PartnerName.partner_id == Partner.id)  # type: ignore[arg-type]
                    .where(
                        sa.func.lower(sa.literal_column('"partner_names"."name"')) == name_raw.lower(),
                        Partner.mandant_id == mandant_id,
                        Partner.is_active == True,  # noqa: E712
                    )
                )
            ).first()
            if row_name is not None:
                assert row_name.id is not None
                partner_id = row_name.id
                await self._maybe_add_iban(partner_id, iban_raw)
                await self._maybe_add_account(partner_id, account_raw, blz_raw, bic_raw)
                return PartnerMatchResult(
                    partner_id=partner_id,
                    outcome=MatchOutcome.name_match,
                    review_context={"matched_on": "name", "raw_name": name_raw, "raw_iban": iban_raw},
                )

        # --- Step 4: Neuen Partner anlegen ---
        desired_name = name_raw or "Unknown"
        existing_by_name = (
            await self._session.exec(
                select(Partner).where(
                    Partner.mandant_id == mandant_id,
                    Partner.name == desired_name,
                )
            )
        ).first()
        if existing_by_name is not None:
            desired_name = f"{desired_name} [{str(uuid4())[:8]}]"

        new_partner = Partner(
            id=uuid4(),
            mandant_id=mandant_id,
            name=desired_name,
            is_active=True,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        self._session.add(new_partner)
        await self._session.flush()

        from app.services.service import ensure_base_service

        await ensure_base_service(self._session, new_partner.id)
        # Alle verfügbaren Identifier direkt beim neuen Partner speichern
        if name_raw and desired_name != "Unknown":
            self._session.add(PartnerName(partner_id=new_partner.id, name=name_raw, created_at=utcnow()))  # type: ignore[arg-type]
        await self._maybe_add_iban(new_partner.id, iban_raw)  # type: ignore[arg-type]
        await self._maybe_add_account(new_partner.id, account_raw, blz_raw, bic_raw)  # type: ignore[arg-type]
        return PartnerMatchResult(partner_id=new_partner.id, outcome=MatchOutcome.new_partner)  # type: ignore[arg-type]

    async def _maybe_add_iban(self, partner_id: UUID, iban_raw: str | None) -> None:
        """Fügt IBAN zum Partner hinzu, wenn sie noch nicht registriert ist."""
        if not iban_raw:
            return
        normalized = _normalize_iban(iban_raw)
        existing = (await self._session.exec(
            select(PartnerIban).where(PartnerIban.iban == normalized)
        )).first()
        if existing is None:
            self._session.add(PartnerIban(partner_id=partner_id, iban=normalized, created_at=utcnow()))

    async def _maybe_add_account(
        self, partner_id: UUID, account_raw: str | None, blz_raw: str | None, bic_raw: str | None = None
    ) -> None:
        """Fügt BLZ+Kontonummer (+BIC) zum Partner hinzu, wenn noch nicht registriert."""
        if not account_raw:
            return
        normalized_acct = _normalize_account(account_raw)
        normalized_blz = blz_raw.strip() if blz_raw else None
        normalized_bic = bic_raw.strip().upper() if bic_raw else None
        existing = (await self._session.exec(
            select(PartnerAccount).where(
                PartnerAccount.account_number == normalized_acct,
                PartnerAccount.blz == normalized_blz,
            )
        )).first()
        if existing is None:
            self._session.add(PartnerAccount(
                partner_id=partner_id,
                blz=normalized_blz,
                account_number=normalized_acct,
                bic=normalized_bic,
                created_at=utcnow(),
            ))

    async def _maybe_update_bic(self, account: PartnerAccount, bic_raw: str | None) -> None:
        """Trägt BIC nach, wenn der Account noch keinen hat."""
        if not bic_raw or account.bic:
            return
        account.bic = bic_raw.strip().upper()
        self._session.add(account)


class ReviewItemFactory:
    """Creates a ReviewItem only when a human should review the match.

    ADR-012: a ReviewItem is created when the match outcome is NAME_MATCH
    and the journal line carried a raw IBAN value (suggesting the IBAN was
    not yet registered for that partner).
    """

    @staticmethod
    def maybe_create(
        result: PartnerMatchResult,
        journal_line: JournalLine,
        mandant_id: UUID,
    ) -> ReviewItem | None:
        # Review bei Name-Match + unbekannte IBAN
        if result.outcome == MatchOutcome.name_match and journal_line.partner_iban_raw:
            return ReviewItem(
                mandant_id=mandant_id,
                item_type="name_match_with_iban",
                journal_line_id=journal_line.id,  # type: ignore[arg-type]
                context=result.review_context,
                status="open",
                created_at=utcnow(),
            )
        return None
