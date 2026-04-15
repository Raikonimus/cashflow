from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from sqlalchemy.exc import IntegrityError

from app.auth.models import MandantUser
from app.imports.models import ImportRun, JournalLine, ReviewItem
from app.partners.models import AuditLog, Partner, PartnerAccount, PartnerIban, PartnerName
from app.services.models import Service, ServiceMatcher, ServiceTypeKeyword
from app.services.service import ServiceManagementService
from app.tenants.models import Account, AccountExcludedIdentifier, ColumnMappingConfig, Mandant
from app.tenants.schemas import (
    CleanupPreviewItem,
    CleanupPreviewSection,
    ColumnMappingRequest,
    CreateAccountRequest,
    CreateMandantRequest,
    ExecuteMandantCleanupRequest,
    ExecuteMandantCleanupResponse,
    ExcludedIdentifierCreate,
    MandantCleanupPreviewResponse,
    UpdateAccountRequest,
    UpdateMandantRequest,
)

log = structlog.get_logger()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MandantService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_mandants(self) -> list[Mandant]:
        result = await self._session.exec(select(Mandant))
        return list(result.all())

    async def get_mandant(self, mandant_id: UUID) -> Mandant:
        mandant = await self._session.get(Mandant, mandant_id)
        if mandant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant not found")
        return mandant

    async def create_mandant(self, data: CreateMandantRequest) -> Mandant:
        now = _utcnow()
        mandant = Mandant(name=data.name, created_at=now, updated_at=now)
        self._session.add(mandant)
        await self._session.commit()
        await self._session.refresh(mandant)
        log.info("mandant_created", mandant_id=str(mandant.id), name=mandant.name)
        return mandant

    async def update_mandant(self, mandant_id: UUID, data: UpdateMandantRequest) -> Mandant:
        mandant = await self.get_mandant(mandant_id)
        if data.name is not None:
            mandant.name = data.name
        mandant.updated_at = _utcnow()
        self._session.add(mandant)
        await self._session.commit()
        await self._session.refresh(mandant)
        return mandant

    async def deactivate_mandant(self, mandant_id: UUID) -> None:
        """Soft cascade: deactivate mandant + all its accounts (ADR-006)."""
        mandant = await self.get_mandant(mandant_id)
        mandant.is_active = False
        mandant.updated_at = _utcnow()
        self._session.add(mandant)

        # Cascade deactivation to all accounts
        result = await self._session.exec(
            select(Account).where(Account.mandant_id == mandant_id, Account.is_active == True)  # noqa: E712
        )
        accounts = result.all()
        for account in accounts:
            account.is_active = False
            account.updated_at = _utcnow()
            self._session.add(account)

        await self._session.commit()
        log.info("mandant_deactivated", mandant_id=str(mandant_id), accounts_deactivated=len(accounts))

    async def get_cleanup_preview(self, mandant_id: UUID) -> MandantCleanupPreviewResponse:
        mandant = await self.get_mandant(mandant_id)
        inventory = await self._collect_inventory(mandant_id)

        return MandantCleanupPreviewResponse(
            mandant_id=mandant.id,
            mandant_name=mandant.name,
            delete_mandant=self._build_section(
                key="delete_mandant",
                label="Mandant löschen",
                description="Löscht den Mandanten selbst inklusive aller mandantenspezifischen Daten und Zuweisungen.",
                items=self._delete_mandant_items(inventory),
            ),
            delete_data=self._build_section(
                key="delete_data",
                label="Nur alle Daten dieses Mandanten löschen",
                description="Behält den Mandantenstammsatz, löscht aber alle fachlichen Daten und Konfigurationen dieses Mandanten.",
                items=self._delete_data_items(inventory),
            ),
            selectable_sections=[
                self._build_section(
                    key="journal_data",
                    label="Journaldaten",
                    description="Löscht Importläufe, Buchungszeilen und die daran hängenden Review-Einträge dieses Mandanten.",
                    items=self._journal_scope_items(inventory),
                ),
                self._build_section(
                    key="partner_service_data",
                    label="Leistungen und Partnerdaten",
                    description="Löscht Partner, Partnermerkmale, Leistungen, Matcher und alle daran hängenden Buchungs- und Review-Daten.",
                    items=self._partner_scope_items(inventory),
                ),
                self._build_section(
                    key="audit_data",
                    label="Auditdaten",
                    description="Löscht alle Audit-Log-Einträge dieses Mandanten.",
                    items=self._audit_scope_items(inventory),
                ),
                self._build_section(
                    key="review_data",
                    label="Reviewdaten",
                    description="Löscht alle Review-Einträge dieses Mandanten, unabhängig von ihrem Ursprung.",
                    items=self._review_scope_items(inventory),
                ),
            ],
        )

    async def execute_cleanup(
        self,
        mandant_id: UUID,
        body: ExecuteMandantCleanupRequest,
    ) -> ExecuteMandantCleanupResponse:
        await self.get_mandant(mandant_id)
        deleted_items: dict[str, CleanupPreviewItem] = {}
        executed_sections: list[str] = []
        deleted_mandant = False

        if body.mode == "delete_mandant":
            executed_sections.append("delete_mandant")
            for item in await self._delete_all_data(mandant_id):
                deleted_items[item.key] = item
            for item in await self._delete_mandant_record(mandant_id):
                deleted_items[item.key] = item
            deleted_mandant = True
        elif body.mode == "delete_data":
            executed_sections.append("delete_data")
            for item in await self._delete_all_data(mandant_id):
                deleted_items[item.key] = item
        else:
            for scope in body.scopes:
                if scope in executed_sections:
                    continue
                executed_sections.append(scope)
                if scope == "journal_data":
                    deleted = await self._delete_journal_scope(mandant_id)
                elif scope == "partner_service_data":
                    deleted = await self._delete_partner_scope(mandant_id)
                elif scope == "audit_data":
                    deleted = await self._delete_audit_scope(mandant_id)
                else:
                    deleted = await self._delete_review_scope(mandant_id)
                for item in deleted:
                    deleted_items[item.key] = item

        return ExecuteMandantCleanupResponse(
            mode=body.mode,
            deleted_mandant=deleted_mandant,
            executed_sections=executed_sections,
            items=list(deleted_items.values()),
        )

    async def _collect_inventory(self, mandant_id: UUID) -> dict[str, int]:
        account_ids = await self._select_ids(Account.id, Account.mandant_id == mandant_id)
        partner_ids = await self._select_ids(Partner.id, Partner.mandant_id == mandant_id)
        service_ids = await self._select_ids_for_values(Service.id, Service.partner_id, partner_ids)
        journal_line_ids_all = await self._select_ids_for_values(JournalLine.id, JournalLine.account_id, account_ids)
        journal_line_ids_partner = await self._select_ids_for_values(JournalLine.id, JournalLine.partner_id, partner_ids)
        review_ids_journal = await self._select_ids_for_values(ReviewItem.id, ReviewItem.journal_line_id, journal_line_ids_all)
        review_ids_partner = await self._select_ids_for_values(ReviewItem.id, ReviewItem.journal_line_id, journal_line_ids_partner)
        review_ids_service = await self._select_ids_for_values(ReviewItem.id, ReviewItem.service_id, service_ids)

        return {
            "mandant": 1,
            "mandant_users": len(await self._select_ids(MandantUser.user_id, MandantUser.mandant_id == mandant_id)),
            "accounts": len(account_ids),
            "column_mapping_configs": len(await self._select_ids_for_values(ColumnMappingConfig.id, ColumnMappingConfig.account_id, account_ids)),
            "account_excluded_identifiers": len(await self._select_ids_for_values(AccountExcludedIdentifier.id, AccountExcludedIdentifier.account_id, account_ids)),
            "import_runs": len(await self._select_ids(ImportRun.id, ImportRun.mandant_id == mandant_id)),
            "journal_lines_all": len(journal_line_ids_all),
            "journal_lines_partner": len(journal_line_ids_partner),
            "review_items_all": len(await self._select_ids(ReviewItem.id, ReviewItem.mandant_id == mandant_id)),
            "review_items_journal": len(review_ids_journal),
            "review_items_partner": len(set(review_ids_partner) | set(review_ids_service)),
            "partners": len(partner_ids),
            "partner_ibans": len(await self._select_ids_for_values(PartnerIban.id, PartnerIban.partner_id, partner_ids)),
            "partner_accounts": len(await self._select_ids_for_values(PartnerAccount.id, PartnerAccount.partner_id, partner_ids)),
            "partner_names": len(await self._select_ids_for_values(PartnerName.id, PartnerName.partner_id, partner_ids)),
            "services": len(service_ids),
            "service_matchers": len(await self._select_ids_for_values(ServiceMatcher.id, ServiceMatcher.service_id, service_ids)),
            "service_type_keywords": len(await self._select_ids(ServiceTypeKeyword.id, ServiceTypeKeyword.mandant_id == mandant_id)),
            "audit_log": len(await self._select_ids(AuditLog.id, AuditLog.mandant_id == mandant_id)),
        }

    async def _delete_all_data(self, mandant_id: UUID) -> list[CleanupPreviewItem]:
        deleted_items: list[CleanupPreviewItem] = []
        deleted_items.extend(await self._delete_review_scope(mandant_id))
        deleted_items.extend(await self._delete_journal_scope(mandant_id, include_related_reviews=False))
        deleted_items.extend(await self._delete_partner_scope(mandant_id, include_related_reviews=False))
        deleted_items.extend(await self._delete_audit_scope(mandant_id))

        account_ids = await self._select_ids(Account.id, Account.mandant_id == mandant_id)
        deleted_items.append(await self._delete_for_values(ColumnMappingConfig, ColumnMappingConfig.account_id, account_ids, "column_mapping_configs", "Spalten-Mappings"))
        deleted_items.append(await self._delete_for_values(AccountExcludedIdentifier, AccountExcludedIdentifier.account_id, account_ids, "account_excluded_identifiers", "Ausgeschlossene Konto-Identifikatoren"))
        deleted_items.append(await self._delete_where(ServiceTypeKeyword, ServiceTypeKeyword.mandant_id == mandant_id, "service_type_keywords", "Mandanten-Keyword-Regeln"))
        deleted_items.append(await self._delete_where(Account, Account.mandant_id == mandant_id, "accounts", "Konten"))

        await self._session.commit()
        return [item for item in deleted_items if item.count > 0]

    async def _delete_mandant_record(self, mandant_id: UUID) -> list[CleanupPreviewItem]:
        deleted_items = [
            await self._delete_where(MandantUser, MandantUser.mandant_id == mandant_id, "mandant_users", "Mandantenzuweisungen"),
            await self._delete_where(Mandant, Mandant.id == mandant_id, "mandant", "Mandant"),
        ]
        await self._session.commit()
        return [item for item in deleted_items if item.count > 0]

    async def _delete_journal_scope(self, mandant_id: UUID, include_related_reviews: bool = True) -> list[CleanupPreviewItem]:
        account_ids = await self._select_ids(Account.id, Account.mandant_id == mandant_id)
        journal_line_ids = await self._select_ids_for_values(JournalLine.id, JournalLine.account_id, account_ids)
        touched_service_ids = await self._select_ids_for_values(JournalLine.service_id, JournalLine.account_id, account_ids, skip_none=True)
        deleted_items: list[CleanupPreviewItem] = []

        if include_related_reviews:
            deleted_items.append(await self._delete_for_values(ReviewItem, ReviewItem.journal_line_id, journal_line_ids, "review_items_journal", "Review-Einträge zu Buchungen"))
        deleted_items.append(await self._delete_for_values(JournalLine, JournalLine.id, journal_line_ids, "journal_lines", "Buchungszeilen"))
        deleted_items.append(await self._delete_where(ImportRun, ImportRun.mandant_id == mandant_id, "import_runs", "Importläufe"))

        service_svc = ServiceManagementService(self._session)
        for service_id in touched_service_ids:
            await service_svc.detect_service_type_for_service(mandant_id, service_id)

        await self._session.commit()
        return [item for item in deleted_items if item.count > 0]

    async def _delete_partner_scope(self, mandant_id: UUID, include_related_reviews: bool = True) -> list[CleanupPreviewItem]:
        partner_ids = await self._select_ids(Partner.id, Partner.mandant_id == mandant_id)
        service_ids = await self._select_ids_for_values(Service.id, Service.partner_id, partner_ids)
        journal_line_ids = await self._select_ids_for_values(JournalLine.id, JournalLine.partner_id, partner_ids)
        deleted_items: list[CleanupPreviewItem] = []

        if include_related_reviews:
            deleted_items.append(await self._delete_for_values(ReviewItem, ReviewItem.journal_line_id, journal_line_ids, "review_items_partner_journal", "Review-Einträge zu Partner-Buchungen"))
            deleted_items.append(await self._delete_for_values(ReviewItem, ReviewItem.service_id, service_ids, "review_items_partner_service", "Review-Einträge zu Leistungen"))
        deleted_items.append(await self._delete_for_values(JournalLine, JournalLine.id, journal_line_ids, "partner_journal_lines", "Partnerbezogene Buchungszeilen"))
        deleted_items.append(await self._delete_for_values(ServiceMatcher, ServiceMatcher.service_id, service_ids, "service_matchers", "Leistungs-Matcher"))
        deleted_items.append(await self._delete_for_values(Service, Service.id, service_ids, "services", "Leistungen"))
        deleted_items.append(await self._delete_for_values(PartnerIban, PartnerIban.partner_id, partner_ids, "partner_ibans", "Partner-IBANs"))
        deleted_items.append(await self._delete_for_values(PartnerAccount, PartnerAccount.partner_id, partner_ids, "partner_accounts", "Partner-Konten"))
        deleted_items.append(await self._delete_for_values(PartnerName, PartnerName.partner_id, partner_ids, "partner_names", "Namensvarianten"))
        deleted_items.append(await self._delete_for_values(Partner, Partner.id, partner_ids, "partners", "Partner"))

        await self._session.commit()
        return [item for item in deleted_items if item.count > 0]

    async def _delete_audit_scope(self, mandant_id: UUID) -> list[CleanupPreviewItem]:
        item = await self._delete_where(AuditLog, AuditLog.mandant_id == mandant_id, "audit_log", "Audit-Log-Einträge")
        await self._session.commit()
        return [item] if item.count > 0 else []

    async def _delete_review_scope(self, mandant_id: UUID) -> list[CleanupPreviewItem]:
        item = await self._delete_where(ReviewItem, ReviewItem.mandant_id == mandant_id, "review_items", "Review-Einträge")
        await self._session.commit()
        return [item] if item.count > 0 else []

    async def _select_ids(self, field, *conditions):
        return list((await self._session.exec(select(field).where(*conditions))).all())

    async def _select_ids_for_values(self, field, match_field, values: list[UUID], skip_none: bool = False):
        if not values:
            return []
        result = list((await self._session.exec(select(field).where(or_(*[match_field == value for value in values])))).all())
        if skip_none:
            return [value for value in result if value is not None]
        return result

    async def _delete_where(self, model, condition, key: str, label: str) -> CleanupPreviewItem:
        count = len((await self._session.exec(select(model).where(condition))).all())
        if count > 0:
            await self._session.exec(sa_delete(model).where(condition))
        return CleanupPreviewItem(key=key, label=label, count=count)

    async def _delete_for_values(self, model, match_field, values: list[UUID], key: str, label: str) -> CleanupPreviewItem:
        if not values:
            return CleanupPreviewItem(key=key, label=label, count=0)
        condition = or_(*[match_field == value for value in values])
        count = len((await self._session.exec(select(model).where(condition))).all())
        if count > 0:
            await self._session.exec(sa_delete(model).where(condition))
        return CleanupPreviewItem(key=key, label=label, count=count)

    def _build_section(self, key: str, label: str, description: str, items: list[CleanupPreviewItem]) -> CleanupPreviewSection:
        return CleanupPreviewSection(key=key, label=label, description=description, items=[item for item in items if item.count > 0])

    def _delete_mandant_items(self, inventory: dict[str, int]) -> list[CleanupPreviewItem]:
        return [
            CleanupPreviewItem(key="mandant", label="Mandant", count=inventory["mandant"]),
            CleanupPreviewItem(key="mandant_users", label="Mandantenzuweisungen", count=inventory["mandant_users"]),
            *self._delete_data_items(inventory),
        ]

    def _delete_data_items(self, inventory: dict[str, int]) -> list[CleanupPreviewItem]:
        return [
            CleanupPreviewItem(key="accounts", label="Konten", count=inventory["accounts"]),
            CleanupPreviewItem(key="column_mapping_configs", label="Spalten-Mappings", count=inventory["column_mapping_configs"]),
            CleanupPreviewItem(key="account_excluded_identifiers", label="Ausgeschlossene Konto-Identifikatoren", count=inventory["account_excluded_identifiers"]),
            CleanupPreviewItem(key="import_runs", label="Importläufe", count=inventory["import_runs"]),
            CleanupPreviewItem(key="journal_lines_all", label="Buchungszeilen", count=inventory["journal_lines_all"]),
            CleanupPreviewItem(key="review_items_all", label="Review-Einträge", count=inventory["review_items_all"]),
            CleanupPreviewItem(key="partners", label="Partner", count=inventory["partners"]),
            CleanupPreviewItem(key="partner_ibans", label="Partner-IBANs", count=inventory["partner_ibans"]),
            CleanupPreviewItem(key="partner_accounts", label="Partner-Konten", count=inventory["partner_accounts"]),
            CleanupPreviewItem(key="partner_names", label="Namensvarianten", count=inventory["partner_names"]),
            CleanupPreviewItem(key="services", label="Leistungen", count=inventory["services"]),
            CleanupPreviewItem(key="service_matchers", label="Leistungs-Matcher", count=inventory["service_matchers"]),
            CleanupPreviewItem(key="service_type_keywords", label="Mandanten-Keyword-Regeln", count=inventory["service_type_keywords"]),
            CleanupPreviewItem(key="audit_log", label="Audit-Log-Einträge", count=inventory["audit_log"]),
        ]

    def _journal_scope_items(self, inventory: dict[str, int]) -> list[CleanupPreviewItem]:
        return [
            CleanupPreviewItem(key="import_runs", label="Importläufe", count=inventory["import_runs"]),
            CleanupPreviewItem(key="journal_lines", label="Buchungszeilen", count=inventory["journal_lines_all"]),
            CleanupPreviewItem(key="review_items_journal", label="Review-Einträge zu Buchungen", count=inventory["review_items_journal"]),
        ]

    def _partner_scope_items(self, inventory: dict[str, int]) -> list[CleanupPreviewItem]:
        return [
            CleanupPreviewItem(key="partners", label="Partner", count=inventory["partners"]),
            CleanupPreviewItem(key="partner_ibans", label="Partner-IBANs", count=inventory["partner_ibans"]),
            CleanupPreviewItem(key="partner_accounts", label="Partner-Konten", count=inventory["partner_accounts"]),
            CleanupPreviewItem(key="partner_names", label="Namensvarianten", count=inventory["partner_names"]),
            CleanupPreviewItem(key="services", label="Leistungen", count=inventory["services"]),
            CleanupPreviewItem(key="service_matchers", label="Leistungs-Matcher", count=inventory["service_matchers"]),
            CleanupPreviewItem(key="journal_lines_partner", label="Partnerbezogene Buchungszeilen", count=inventory["journal_lines_partner"]),
            CleanupPreviewItem(key="review_items_partner", label="Review-Einträge zu Partnern und Leistungen", count=inventory["review_items_partner"]),
        ]

    def _audit_scope_items(self, inventory: dict[str, int]) -> list[CleanupPreviewItem]:
        return [CleanupPreviewItem(key="audit_log", label="Audit-Log-Einträge", count=inventory["audit_log"])]

    def _review_scope_items(self, inventory: dict[str, int]) -> list[CleanupPreviewItem]:
        return [CleanupPreviewItem(key="review_items", label="Review-Einträge", count=inventory["review_items_all"])]


class AccountService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_accounts(self, mandant_id: UUID) -> list[Account]:
        result = await self._session.exec(
            select(Account).where(Account.mandant_id == mandant_id)
        )
        return list(result.all())

    async def get_account(self, account_id: UUID, mandant_id: UUID) -> Account:
        account = await self._session.get(Account, account_id)
        # Return 404 even if account exists but belongs to a different mandant (no info-leak)
        if account is None or account.mandant_id != mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        return account

    async def create_account(self, mandant_id: UUID, data: CreateAccountRequest) -> Account:
        if data.iban is not None:
            normalized_iban = data.iban.replace(" ", "").upper()
            existing = await self._session.exec(
                select(Account).where(Account.iban == normalized_iban)
            )
            if existing.first() is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="IBAN already in use")
        else:
            normalized_iban = None

        now = _utcnow()
        account = Account(
            mandant_id=mandant_id,
            name=data.name,
            iban=normalized_iban,
            currency=data.currency.upper(),
            created_at=now,
            updated_at=now,
        )
        self._session.add(account)
        await self._session.commit()
        await self._session.refresh(account)
        log.info("account_created", account_id=str(account.id), mandant_id=str(mandant_id))
        return account

    async def update_account(self, account_id: UUID, mandant_id: UUID, data: UpdateAccountRequest) -> Account:
        account = await self.get_account(account_id, mandant_id)

        if data.name is not None:
            account.name = data.name
        if data.iban is not None:
            normalized_iban = data.iban.replace(" ", "").upper()
            existing = await self._session.exec(
                select(Account).where(Account.iban == normalized_iban, Account.id != account_id)
            )
            if existing.first() is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="IBAN already in use")
            account.iban = normalized_iban
        if data.is_active is not None:
            account.is_active = data.is_active

        account.updated_at = _utcnow()
        self._session.add(account)
        await self._session.commit()
        await self._session.refresh(account)
        return account

    async def get_column_mapping(self, account_id: UUID) -> Optional[ColumnMappingConfig]:
        result = await self._session.exec(
            select(ColumnMappingConfig).where(ColumnMappingConfig.account_id == account_id)
        )
        return result.first()

    async def set_column_mapping(self, account_id: UUID, data: ColumnMappingRequest) -> ColumnMappingConfig:
        existing = await self.get_column_mapping(account_id)
        now = _utcnow()

        # Wenn column_assignments angegeben → Legacy-Felder daraus ableiten
        if data.column_assignments is not None:
            def first_source(target: str) -> str:
                for a in sorted(data.column_assignments, key=lambda x: x.sort_order):  # type: ignore[arg-type]
                    if a.target == target:
                        return a.source
                return ""

            valuta_date_col = first_source("valuta_date")
            booking_date_col = first_source("booking_date")
            amount_col = first_source("amount")
            partner_iban_col = first_source("partner_iban") or None
            partner_name_col = first_source("partner_name") or None
            description_col = first_source("description") or None
            assignments_data = [a.model_dump() for a in data.column_assignments]
        else:
            valuta_date_col = data.valuta_date_col or ""
            booking_date_col = data.booking_date_col or ""
            amount_col = data.amount_col or ""
            partner_iban_col = data.partner_iban_col
            partner_name_col = data.partner_name_col
            description_col = data.description_col
            assignments_data = None

        if existing is not None:
            existing.valuta_date_col = valuta_date_col
            existing.booking_date_col = booking_date_col
            existing.amount_col = amount_col
            existing.partner_iban_col = partner_iban_col
            existing.partner_name_col = partner_name_col
            existing.description_col = description_col
            existing.column_assignments = assignments_data
            existing.decimal_separator = data.decimal_separator
            existing.date_format = data.date_format
            existing.encoding = data.encoding
            existing.delimiter = data.delimiter
            existing.skip_rows = data.skip_rows
            existing.updated_at = now
            self._session.add(existing)
            await self._session.commit()
            await self._session.refresh(existing)
            return existing
        else:
            config = ColumnMappingConfig(
                account_id=account_id,
                valuta_date_col=valuta_date_col,
                booking_date_col=booking_date_col,
                amount_col=amount_col,
                partner_iban_col=partner_iban_col,
                partner_name_col=partner_name_col,
                description_col=description_col,
                column_assignments=assignments_data,
                decimal_separator=data.decimal_separator,
                date_format=data.date_format,
                encoding=data.encoding,
                delimiter=data.delimiter,
                skip_rows=data.skip_rows,
                created_at=now,
                updated_at=now,
            )
            self._session.add(config)
            await self._session.commit()
            await self._session.refresh(config)
            log.info("column_mapping_configured", account_id=str(account_id))
            return config

    async def trigger_remapping(self, account_id: UUID, actor_id: UUID) -> None:
        """Placeholder: logs trigger, returns 202. Real queue in future bolt (ADR-007)."""
        log.info("remapping_triggered", account_id=str(account_id), triggered_by=str(actor_id))

    # ─── Excluded Identifiers ─────────────────────────────────────────────────

    async def list_excluded_identifiers(
        self, account_id: UUID
    ) -> list[AccountExcludedIdentifier]:
        result = await self._session.exec(
            select(AccountExcludedIdentifier)
            .where(AccountExcludedIdentifier.account_id == account_id)
            .order_by(AccountExcludedIdentifier.created_at)  # type: ignore[arg-type]
        )
        return list(result.all())

    async def add_excluded_identifier(
        self, account_id: UUID, mandant_id: UUID, data: ExcludedIdentifierCreate
    ) -> AccountExcludedIdentifier:
        await self.get_account(account_id, mandant_id)  # ownership check
        value = data.value.strip().upper() if data.identifier_type == "iban" else data.value.strip()
        entry = AccountExcludedIdentifier(
            account_id=account_id,
            identifier_type=data.identifier_type,
            value=value,
            label=data.label,
        )
        self._session.add(entry)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            raise HTTPException(status_code=409, detail="Identifier already excluded for this account")
        await self._session.refresh(entry)
        return entry

    async def delete_excluded_identifier(
        self, account_id: UUID, mandant_id: UUID, identifier_id: UUID
    ) -> None:
        await self.get_account(account_id, mandant_id)  # ownership check
        entry = await self._session.get(AccountExcludedIdentifier, identifier_id)
        if entry is None or entry.account_id != account_id:
            raise HTTPException(status_code=404, detail="Excluded identifier not found")
        await self._session.delete(entry)
        await self._session.commit()

    async def get_excluded_sets(
        self, account_id: UUID
    ) -> tuple[frozenset[str], frozenset[str]]:
        """Gibt (excluded_ibans, excluded_accounts) als Frozensets zurück für Matching."""
        entries = await self.list_excluded_identifiers(account_id)
        ibans = frozenset(e.value for e in entries if e.identifier_type == "iban")
        accounts = frozenset(e.value for e in entries if e.identifier_type == "account_number")
        return ibans, accounts

    async def apply_excluded_identifiers(self, account_id: UUID, mandant_id: UUID) -> int:
        """Findet Journal-Zeilen, die via ausgeschlossenem Identifier zugeordnet wurden,
        und führt das Matching erneut durch — diesmal ohne die ausgeschlossenen Werte.
        Zeilen, bei denen der aktuelle Partner den ausgeschlossenen Identifier gar nicht
        mehr besitzt, werden übersprungen (bereits korrekt zugeordnet).
        Gibt die Anzahl der geänderten Zeilen zurück.
        """
        from app.imports.matching import PartnerMatchingService, _normalize_iban, _normalize_account
        from app.imports.models import JournalLine
        from app.partners.models import PartnerAccount, PartnerIban

        excluded_ibans, excluded_accounts = await self.get_excluded_sets(account_id)
        if not excluded_ibans and not excluded_accounts:
            return 0

        result = await self._session.exec(
            select(JournalLine).where(JournalLine.account_id == account_id)
        )
        lines = result.all()

        matcher = PartnerMatchingService(self._session)
        affected = 0

        for line in lines:
            iban_excluded = bool(
                line.partner_iban_raw
                and _normalize_iban(line.partner_iban_raw) in excluded_ibans
            )
            account_excluded = bool(
                line.partner_account_raw
                and _normalize_account(line.partner_account_raw) in excluded_accounts
            )
            if not iban_excluded and not account_excluded:
                continue

            # Prüfen ob der aktuell zugeordnete Partner noch über den ausgeschlossenen
            # Identifier verfügt. Falls nein → wurde bereits korrekt neu zugeordnet → überspringen.
            if line.partner_id is not None:
                needs_rematching = False

                if iban_excluded:
                    normalized = _normalize_iban(line.partner_iban_raw)
                    iban_row = (await self._session.exec(
                        select(PartnerIban).where(
                            PartnerIban.partner_id == line.partner_id,
                            PartnerIban.iban == normalized,
                        )
                    )).first()
                    if iban_row is not None:
                        needs_rematching = True

                if account_excluded and not needs_rematching:
                    normalized_acct = _normalize_account(line.partner_account_raw)
                    acct_row = (await self._session.exec(
                        select(PartnerAccount).where(
                            PartnerAccount.partner_id == line.partner_id,
                            PartnerAccount.account_number == normalized_acct,
                        )
                    )).first()
                    if acct_row is not None:
                        needs_rematching = True

                if not needs_rematching:
                    continue

            # Ausgeschlossene Identifier NICHT an Matcher übergeben (kein Lookup + kein Auto-Enrich)
            match_result = await matcher.match(
                mandant_id=mandant_id,
                iban_raw=None if iban_excluded else line.partner_iban_raw,
                name_raw=line.partner_name_raw,
                account_raw=None if account_excluded else line.partner_account_raw,
                blz_raw=None if account_excluded else line.partner_blz_raw,
                bic_raw=None if account_excluded else line.partner_bic_raw,
                excluded_ibans=excluded_ibans,
                excluded_accounts=excluded_accounts,
            )

            if match_result.partner_id != line.partner_id:
                line.partner_id = match_result.partner_id
                self._session.add(line)
                affected += 1

        if affected > 0:
            await self._session.commit()

        return affected
