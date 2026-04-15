"""Partner matching service for import pipeline.

Matches a journal line's IBAN/name/text against known active partners.
Produces a PartnerMatchResult and, when appropriate, a ReviewItem.

Matching order (first match wins):
  1. IBAN-Lookup
  2. BLZ + Kontonummer Lookup
  3. Namens-Lookup
  4. Leistungs-Matcher aller aktiver Partner (neu)
  5. Neuer Partner anlegen (nur wenn Partnername bekannt)
     — andernfalls: ReviewItem "no_partner_identified"
  Falls ≥2 Leistungs-Matcher auf verschiedene Partner zeigen:
     → ReviewItem "service_matcher_ambiguous" statt Zuweisung.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.imports.models import JournalLine, ReviewItem, utcnow
from app.partners.models import Partner, PartnerAccount, PartnerIban, PartnerName
from app.services.models import Service, ServiceMatcher, ServiceMatcherType


def _normalize_iban(raw: str) -> str:
    return raw.replace(" ", "").upper()


def _normalize_account(raw: str) -> str:
    """Entfernt führende Nullen und Leerzeichen für konsistenten Vergleich."""
    return raw.strip().lstrip("0") or raw.strip()


class MatchOutcome(StrEnum):
    iban_match = "iban_match"
    account_match = "account_match"            # BLZ + Kontonummer
    name_match = "name_match"
    service_matcher_match = "service_matcher_match"        # eindeutiger Leistungs-Matcher-Treffer
    service_matcher_ambiguous = "service_matcher_ambiguous"  # mehrere Partner getroffen
    no_partner_identified = "no_partner_identified"          # kein Treffer, kein Name
    new_partner = "new_partner"


@dataclass
class PartnerMatchResult:
    partner_id: UUID | None   # None bei ambiguous / no_partner_identified
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
        text_raw: str | None = None,
        excluded_ibans: frozenset[str] = frozenset(),
        excluded_accounts: frozenset[str] = frozenset(),
    ) -> PartnerMatchResult:
        """Match to a partner; create a new one if no match is found.

        Reihenfolge:
        1. IBAN-Lookup (übersprungen wenn IBAN in excluded_ibans)
        2. BLZ + Kontonummer Lookup (übersprungen wenn Konto in excluded_accounts)
        3. Name-Lookup
        4. Leistungs-Matcher aller aktiver Partner prüfen (via text_raw + name_raw)
           → 1 Treffer: Partner zuweisen
           → ≥2 Treffer: ReviewItem "service_matcher_ambiguous"
        5. Neuen Partner anlegen (nur wenn name_raw bekannt)
           → kein Name: ReviewItem "no_partner_identified" statt neuem Partner

        Nach dem Match werden fehlende Identifier automatisch beim Partner ergänzt.
        """

        # Diagnose-Dict – wird von jedem fehlschlagenden Schritt befüllt und
        # bei MatchOutcome.no_partner_identified an den review_context angehängt.
        _diag: dict[str, object] = {}

        # --- Step 1: IBAN lookup ---
        if iban_raw:
            normalized = _normalize_iban(iban_raw)
            if normalized in excluded_ibans:
                _diag["iban"] = {"provided": True, "excluded": True, "normalized": normalized}
            else:
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
                _diag["iban"] = {"provided": True, "excluded": False, "found": False, "normalized": normalized}
        else:
            _diag["iban"] = {"provided": False}

        # --- Step 2: BLZ + Kontonummer Lookup ---
        if account_raw:
            normalized_acct = _normalize_account(account_raw)
            if normalized_acct in excluded_accounts:
                _diag["account"] = {"provided": True, "excluded": True, "normalized": normalized_acct}
            else:
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
                _diag["account"] = {"provided": True, "excluded": False, "found": False, "normalized": normalized_acct}
        else:
            _diag["account"] = {"provided": False}

        # --- Step 3: Name lookup ---
        if name_raw:
            # Suche in PartnerName-Einträgen (Namensvarianten + vom Import angelegte Namen)
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
            # Fallback: Partner.name direkt prüfen (manuell angelegte Partner ohne PartnerName-Eintrag)
            if row_name is None:
                row_name = (
                    await self._session.exec(
                        select(Partner)
                        .where(
                            sa.func.lower(Partner.name) == name_raw.lower(),
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
            _diag["name"] = {"provided": True, "found": False, "value": name_raw}
        else:
            _diag["name"] = {"provided": False}

        # --- Step 4: Leistungs-Matcher aller aktiven Partner prüfen ---
        matched_by_service, svc_diag = await self._find_partners_by_service_matcher(
            mandant_id, text_raw, name_raw
        )
        _diag["service_matchers"] = svc_diag
        if len(matched_by_service) == 1:
            pid, pname = matched_by_service[0]
            await self._maybe_add_iban(pid, iban_raw)
            await self._maybe_add_account(pid, account_raw, blz_raw, bic_raw)
            return PartnerMatchResult(
                partner_id=pid,
                outcome=MatchOutcome.service_matcher_match,
                review_context={"matched_on": "service_matcher", "partner_name": pname},
            )
        if len(matched_by_service) > 1:
            return PartnerMatchResult(
                partner_id=None,
                outcome=MatchOutcome.service_matcher_ambiguous,
                review_context={
                    "candidates": [
                        {"id": str(pid), "name": pname}
                        for pid, pname in matched_by_service
                    ],
                    "raw_text": text_raw,
                    "raw_name": name_raw,
                    "raw_iban": iban_raw,
                },
            )

        # --- Step 5: Neuen Partner anlegen (nur wenn Name bekannt) ---
        if not name_raw:
            return PartnerMatchResult(
                partner_id=None,
                outcome=MatchOutcome.no_partner_identified,
                review_context={
                    "raw_text": text_raw,
                    "raw_iban": iban_raw,
                    "raw_account": account_raw,
                    "diagnosis": _diag,
                },
            )

        desired_name = name_raw
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

        assert new_partner.id is not None
        await ensure_base_service(self._session, new_partner.id)
        # Alle verfügbaren Identifier direkt beim neuen Partner speichern
        if name_raw:
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

    async def _find_partners_by_service_matcher(
        self,
        mandant_id: UUID,
        text_raw: str | None,
        name_raw: str | None,
    ) -> tuple[list[tuple[UUID, str]], dict]:
        """Gibt (partner_id, partner_name)-Paare zurück, deren Leistungs-Matcher passen.

        Sucht in Buchungstext (text_raw) und Partnerrohrname (name_raw).
        Gibt für jeden Partner maximal einen Eintrag zurück.
        Basis-Leistungen (is_base_service=True) werden ignoriert.
        Zweiter Rückgabewert ist ein Diagnose-Dict für den review_context.
        """
        searchable = "\n".join(filter(None, [text_raw or "", name_raw or ""]))
        if not searchable:
            return [], {"skipped": True, "reason": "no_searchable_text"}

        # Aktive Partner dieses Mandanten laden (liefert auch die Namen)
        partners = (
            await self._session.exec(
                select(Partner).where(
                    Partner.mandant_id == mandant_id,
                    Partner.is_active == True,  # noqa: E712
                )
            )
        ).all()
        if not partners:
            return [], {"skipped": False, "total_matchers": 0, "matched": 0, "reason": "no_active_partners"}
        partner_names: dict[UUID, str] = {p.id: p.name for p in partners}  # type: ignore[misc]

        # Nicht-Basis-Leistungen aktiver Partner laden
        services = (
            await self._session.exec(
                select(Service)
                .join(Partner, Partner.id == Service.partner_id)  # type: ignore[arg-type]
                .where(
                    Partner.mandant_id == mandant_id,
                    Partner.is_active == True,   # noqa: E712
                    Service.is_base_service == False,  # noqa: E712
                )
            )
        ).all()
        if not services:
            return [], {"skipped": False, "total_matchers": 0, "matched": 0, "reason": "no_services_configured"}
        svc_to_partner: dict[UUID, UUID] = {s.id: s.partner_id for s in services}  # type: ignore[misc]

        # Leistungs-Matcher über dieselben JOINs laden (kein IN-Operator nötig)
        all_matchers = (
            await self._session.exec(
                select(ServiceMatcher)
                .join(Service, Service.id == ServiceMatcher.service_id)  # type: ignore[arg-type]
                .join(Partner, Partner.id == Service.partner_id)  # type: ignore[arg-type]
                .where(
                    Partner.mandant_id == mandant_id,
                    Partner.is_active == True,    # noqa: E712
                    Service.is_base_service == False,  # noqa: E712
                )
            )
        ).all()
        if not all_matchers:
            return [], {"skipped": False, "total_matchers": 0, "matched": 0, "reason": "no_matchers_configured"}

        # Matcher gruppiert nach Partner
        matchers_by_partner: dict[UUID, list[ServiceMatcher]] = {}
        for m in all_matchers:
            pid = svc_to_partner.get(m.service_id)
            if pid is not None:
                matchers_by_partner.setdefault(pid, []).append(m)

        searchable_lower = searchable.lower()
        matched: list[tuple[UUID, str]] = []
        for pid, matchers in matchers_by_partner.items():
            if _any_matcher_hits(matchers, searchable, searchable_lower):
                matched.append((pid, partner_names.get(pid, "")))

        return matched, {"skipped": False, "total_matchers": len(all_matchers), "matched": len(matched)}

    async def _maybe_update_bic(self, account: PartnerAccount, bic_raw: str | None) -> None:
        """Trägt BIC nach, wenn der Account noch keinen hat."""
        if not bic_raw or account.bic:
            return
        account.bic = bic_raw.strip().upper()
        self._session.add(account)


def _any_matcher_hits(
    matchers: list[ServiceMatcher],
    searchable: str,
    searchable_lower: str,
) -> bool:
    """Gibt True zurück, wenn mindestens ein Matcher auf den Text passt."""
    for m in matchers:
        if m.pattern_type == ServiceMatcherType.string.value:
            if m.pattern.lower() in searchable_lower:
                return True
        else:
            try:
                if re.search(m.pattern, searchable, re.IGNORECASE):
                    return True
            except re.error:
                pass
    return False


class ReviewItemFactory:
    """Creates a ReviewItem when a human should review the partner assignment."""

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
        # Kein Partner identifizierbar (kein Treffer + kein Name)
        if result.outcome == MatchOutcome.no_partner_identified:
            return ReviewItem(
                mandant_id=mandant_id,
                item_type="no_partner_identified",
                journal_line_id=journal_line.id,  # type: ignore[arg-type]
                context=result.review_context,
                status="open",
                created_at=utcnow(),
            )
        # Mehrdeutiger Leistungs-Matcher-Treffer (≥2 Partner)
        if result.outcome == MatchOutcome.service_matcher_ambiguous:
            return ReviewItem(
                mandant_id=mandant_id,
                item_type="service_matcher_ambiguous",
                journal_line_id=journal_line.id,  # type: ignore[arg-type]
                context=result.review_context,
                status="open",
                created_at=utcnow(),
            )
        # Neuer Partner wurde automatisch angelegt – muss geprüft werden
        if result.outcome == MatchOutcome.new_partner:
            return ReviewItem(
                mandant_id=mandant_id,
                item_type="new_partner",
                journal_line_id=journal_line.id,  # type: ignore[arg-type]
                context={
                    "partner_name_raw": journal_line.partner_name_raw,
                    "new_partner_id": str(result.partner_id),
                },
                status="open",
                created_at=utcnow(),
            )
        return None
