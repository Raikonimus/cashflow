import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.imports.models import JournalLine
from app.partners.models import AuditLog, Partner
from app.services.models import Service
from app.services.models import ServiceGroupAssignment, ServiceGroupSection, ServiceType
from app.services.service import ServiceManagementService
from app.tenants.models import Account
from app.journal.schemas import (
    BulkAssignResponse,
    IncomeExpenseGroupRow,
    IncomeExpenseMatrixResponse,
    IncomeExpenseSection,
    IncomeExpenseServiceRow,
    JournalYearsResponse,
    JournalLineResponse,
    MatrixCell,
    MatrixCells,
    PaginatedJournalResponse,
)

log = structlog.get_logger()

INTERNAL_UNMAPPED_DATA_KEYS = {"_cashflow_source_values"}
MONTH_KEYS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

_ZERO = Decimal("0.00")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_unmapped_data(unmapped_data: Any) -> Any:
    if not isinstance(unmapped_data, dict):
        return unmapped_data

    sanitized = {
        key: value
        for key, value in unmapped_data.items()
        if key not in INTERNAL_UNMAPPED_DATA_KEYS
    }
    return sanitized or None


def _as_money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _empty_cells() -> dict[str, dict[str, Decimal]]:
    cells: dict[str, dict[str, Decimal]] = {
        "year_total": {"gross": Decimal("0"), "net": Decimal("0")},
    }
    for month_key in MONTH_KEYS:
        cells[month_key] = {"gross": Decimal("0"), "net": Decimal("0")}
    return cells


def _to_cells_payload(cells: dict[str, dict[str, Decimal]]) -> MatrixCells:
    return MatrixCells(
        year_total=MatrixCell(gross=_as_money(cells["year_total"]["gross"]), net=_as_money(cells["year_total"]["net"])),
        jan=MatrixCell(gross=_as_money(cells["jan"]["gross"]), net=_as_money(cells["jan"]["net"])),
        feb=MatrixCell(gross=_as_money(cells["feb"]["gross"]), net=_as_money(cells["feb"]["net"])),
        mar=MatrixCell(gross=_as_money(cells["mar"]["gross"]), net=_as_money(cells["mar"]["net"])),
        apr=MatrixCell(gross=_as_money(cells["apr"]["gross"]), net=_as_money(cells["apr"]["net"])),
        may=MatrixCell(gross=_as_money(cells["may"]["gross"]), net=_as_money(cells["may"]["net"])),
        jun=MatrixCell(gross=_as_money(cells["jun"]["gross"]), net=_as_money(cells["jun"]["net"])),
        jul=MatrixCell(gross=_as_money(cells["jul"]["gross"]), net=_as_money(cells["jul"]["net"])),
        aug=MatrixCell(gross=_as_money(cells["aug"]["gross"]), net=_as_money(cells["aug"]["net"])),
        sep=MatrixCell(gross=_as_money(cells["sep"]["gross"]), net=_as_money(cells["sep"]["net"])),
        oct=MatrixCell(gross=_as_money(cells["oct"]["gross"]), net=_as_money(cells["oct"]["net"])),
        nov=MatrixCell(gross=_as_money(cells["nov"]["gross"]), net=_as_money(cells["nov"]["net"])),
        dec=MatrixCell(gross=_as_money(cells["dec"]["gross"]), net=_as_money(cells["dec"]["net"])),
    )


def _section_for_service(service: Service) -> ServiceGroupSection | None:
    if service.erfolgsneutral:
        return ServiceGroupSection.neutral
    if service.service_type == ServiceType.customer.value:
        return ServiceGroupSection.income
    if service.service_type in {
        ServiceType.supplier.value,
        ServiceType.authority.value,
        ServiceType.shareholder.value,
        ServiceType.employee.value,
    }:
        return ServiceGroupSection.expense
    return None


def _month_key_from_valuta_date(valuta_date: str) -> str | None:
    try:
        month = int(valuta_date[5:7])
    except (TypeError, ValueError):
        return None
    if month < 1 or month > 12:
        return None
    return MONTH_KEYS[month - 1]


class JournalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ─── List lines ──────────────────────────────────────────────────────────

    async def list_lines(
        self,
        mandant_id: UUID,
        *,
        account_id: UUID | None = None,
        partner_id: UUID | None = None,
        year: int | None = None,
        month: int | None = None,
        has_partner: bool | None = None,
        search: str = "",
        sort_by: str = "valuta_date",
        sort_dir: str = "desc",
        page: int = 1,
        size: int = 50,
    ) -> PaginatedJournalResponse:
        size = min(size, 200)
        offset = (page - 1) * size

        # All account IDs belonging to this mandant (security boundary)
        account_ids_res = await self._session.exec(
            select(Account.id).where(Account.mandant_id == mandant_id)  # type: ignore[arg-type]
        )
        mandant_account_ids = set(account_ids_res.all())

        if account_id is not None:
            if account_id not in mandant_account_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account does not belong to this mandant",
                )
            account_ids_filter = {account_id}
        else:
            account_ids_filter = mandant_account_ids

        query = select(JournalLine).where(
            col(JournalLine.account_id).in_(account_ids_filter)
        )

        if partner_id is not None:
            query = query.where(JournalLine.partner_id == partner_id)

        if has_partner is True:
            query = query.where(JournalLine.partner_id.is_not(None))
        elif has_partner is False:
            query = query.where(JournalLine.partner_id.is_(None))

        if year is not None and month is not None:
            prefix = f"{year:04d}-{month:02d}-"
            query = query.where(text("journal_lines.valuta_date LIKE :valuta_prefix").bindparams(valuta_prefix=f"{prefix}%"))
        elif year is not None:
            query = query.where(text("journal_lines.valuta_date LIKE :valuta_year").bindparams(valuta_year=f"{year:04d}-%"))

        if search:
            # Always JOIN partners for search (avoid duplicate join if also sorting by partner_name)
            term = f"%{search.lower()}%"
            query = (
                query
                .outerjoin(Partner, Partner.id == JournalLine.partner_id)  # type: ignore[arg-type]
                .where(
                    or_(
                        func.lower(func.coalesce(JournalLine.text, "")).like(term),
                        func.lower(func.coalesce(JournalLine.partner_name_raw, "")).like(term),
                        func.lower(func.coalesce(Partner.display_name, Partner.name, "")).like(term),
                    )
                )
            )

        # Sorting: partner_name / service_name require JOINs; others are plain SQL columns
        SQL_SORT_COLS = {"valuta_date", "booking_date", "amount", "text"}
        order_dir = "DESC" if sort_dir == "desc" else "ASC"
        if sort_by in SQL_SORT_COLS:
            order_expr = text(f"{sort_by} {order_dir}")
        elif sort_by == "partner_name":
            # JOIN partners so we can ORDER BY coalesce(display_name, name) globally
            # Only join if not already joined via search
            if not search:  # search already added the join
                query = query.outerjoin(Partner, Partner.id == JournalLine.partner_id)  # type: ignore[arg-type]
            order_expr = text(
                f"lower(coalesce(partners.display_name, partners.name, journal_lines.partner_name_raw, '')) {order_dir}"
            )
        elif sort_by == "service_name":
            query = query.outerjoin(Service, Service.id == JournalLine.service_id)  # type: ignore[arg-type]
            order_expr = text(f"lower(coalesce(services.name, '')) {order_dir}")
        else:
            order_expr = text("valuta_date DESC")  # fallback

        count_res = await self._session.exec(query)
        total = len(count_res.all())

        data_res = await self._session.exec(
            query.order_by(order_expr).offset(offset).limit(size)
        )
        lines = data_res.all()

        # Batch-load partner names (prefer display_name)
        partner_ids = {ln.partner_id for ln in lines if ln.partner_id}
        partner_names: dict = {}
        if partner_ids:
            p_res = await self._session.exec(
                select(Partner)
            )
            partner_names = {
                partner.id: partner.display_name or partner.name
                for partner in p_res.all()
                if partner.id in partner_ids
            }

        service_ids = {ln.service_id for ln in lines if ln.service_id}
        service_names: dict = {}
        if service_ids:
            s_res = await self._session.exec(
                select(Service.id, Service.name).where(col(Service.id).in_(service_ids))
            )
            service_names = {
                service_id: service_name
                for service_id, service_name in s_res.all()
            }

        items = [
            JournalLineResponse(
                **{
                    **{k: v for k, v in ln.model_dump().items() if k != "unmapped_data"},
                    "unmapped_data": _sanitize_unmapped_data(ln.unmapped_data),
                },
                service_name=service_names.get(ln.service_id) if ln.service_id else None,
                partner_name=partner_names.get(ln.partner_id) if ln.partner_id else None,
            )
            for ln in lines
        ]

        return PaginatedJournalResponse(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=math.ceil(total / size) if total > 0 else 1,
        )

    async def list_years(
        self,
        mandant_id: UUID,
        *,
        account_id: UUID | None = None,
    ) -> JournalYearsResponse:
        account_ids_res = await self._session.exec(
            select(Account.id).where(Account.mandant_id == mandant_id)  # type: ignore[arg-type]
        )
        mandant_account_ids = set(account_ids_res.all())

        if account_id is not None:
            if account_id not in mandant_account_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account does not belong to this mandant",
                )
            account_ids_filter = {account_id}
        else:
            account_ids_filter = mandant_account_ids

        if not account_ids_filter:
            return JournalYearsResponse(years=[])

        years_query = (
            select(func.substr(JournalLine.valuta_date, 1, 4).label("year"))
            .where(col(JournalLine.account_id).in_(account_ids_filter))
            .group_by(text("year"))
            .order_by(text("year DESC"))
        )
        rows = (await self._session.exec(years_query)).all()

        years: list[int] = []
        for row in rows:
            try:
                years.append(int(str(row)))
            except (TypeError, ValueError):
                continue
        return JournalYearsResponse(years=years)

    async def get_income_expense_matrix(
        self,
        mandant_id: UUID,
        year: int,
    ) -> IncomeExpenseMatrixResponse:
        base_currency = "EUR"

        service_svc = ServiceManagementService(self._session)
        await service_svc.ensure_default_groups(mandant_id)

        service_rows = (
            await self._session.exec(
                select(Service, Partner)
                .join(Partner, Partner.id == Service.partner_id)
                .where(Partner.mandant_id == mandant_id)
                .order_by(Service.name)
            )
        ).all()
        grouped_services: dict[UUID, Service] = {}
        service_section: dict[UUID, ServiceGroupSection] = {}
        service_partner_name: dict[UUID, str | None] = {}
        for service, partner in service_rows:
            section = _section_for_service(service)
            if section is None:
                continue
            grouped_services[service.id] = service
            service_section[service.id] = section
            service_partner_name[service.id] = partner.display_name or partner.name

        groups_by_section = await service_svc.list_groups_by_section(mandant_id)

        assignments = (
            await self._session.exec(
                select(ServiceGroupAssignment).where(ServiceGroupAssignment.mandant_id == mandant_id)
            )
        ).all()
        assignment_by_service: dict[UUID, ServiceGroupAssignment] = {assignment.service_id: assignment for assignment in assignments}

        # Ensure one assignment for every included service and repair wrong-section defaults.
        changed_assignments = False
        for service_id, section in service_section.items():
            service = grouped_services[service_id]
            existing_assignment = assignment_by_service.get(service_id)
            assignment = await service_svc.ensure_service_group_assignment(
                mandant_id,
                service,
                groups_by_section=groups_by_section,
                assignment=existing_assignment,
            )
            if assignment is not None and assignment is not existing_assignment:
                assignment_by_service[service_id] = assignment
                changed_assignments = True
            elif existing_assignment is not None and assignment is not None and existing_assignment.service_group_id != assignment.service_group_id:
                assignment_by_service[service_id] = assignment
                changed_assignments = True
        if changed_assignments:
            await self._session.commit()
            assignments = (
                await self._session.exec(
                    select(ServiceGroupAssignment).where(ServiceGroupAssignment.mandant_id == mandant_id)
                )
            ).all()
            assignment_by_service = {assignment.service_id: assignment for assignment in assignments}

        # Aggregation: gross per service and month in base currency.
        account_ids_res = await self._session.exec(select(Account.id).where(Account.mandant_id == mandant_id))
        account_ids = set(account_ids_res.all())
        if account_ids:
            line_rows = (
                await self._session.exec(
                    select(JournalLine.service_id, JournalLine.valuta_date, JournalLine.amount)
                    .where(
                        col(JournalLine.account_id).in_(account_ids),
                        JournalLine.service_id.is_not(None),
                        text("journal_lines.valuta_date LIKE :valuta_year").bindparams(valuta_year=f"{year:04d}-%"),
                        JournalLine.currency == base_currency,
                    )
                )
            ).all()
            service_year_rows = (
                await self._session.exec(
                    select(JournalLine.service_id, func.substr(JournalLine.valuta_date, 1, 4).label("year"))
                    .where(
                        col(JournalLine.account_id).in_(account_ids),
                        JournalLine.service_id.is_not(None),
                    )
                )
            ).all()
            excluded_rows = (
                await self._session.exec(
                    select(JournalLine.currency, JournalLine.amount)
                    .where(
                        col(JournalLine.account_id).in_(account_ids),
                        JournalLine.service_id.is_not(None),
                        text("journal_lines.valuta_date LIKE :valuta_year").bindparams(valuta_year=f"{year:04d}-%"),
                        JournalLine.currency != base_currency,
                    )
                )
            ).all()
        else:
            line_rows = []
            service_year_rows = []
            excluded_rows = []

        gross_by_service_month: dict[UUID, dict[str, Decimal]] = {}
        for service_id, valuta_date, amount in line_rows:
            if service_id not in grouped_services:
                continue
            month_key = _month_key_from_valuta_date(valuta_date)
            if month_key is None:
                continue
            gross_by_service_month.setdefault(service_id, {}).setdefault(month_key, Decimal("0"))
            gross_by_service_month[service_id][month_key] += Decimal(str(amount))

        active_years_by_service: dict[UUID, set[int]] = {}
        for service_id, raw_year in service_year_rows:
            if service_id not in grouped_services:
                continue
            try:
                active_year = int(str(raw_year))
            except (TypeError, ValueError):
                continue
            active_years_by_service.setdefault(service_id, set()).add(active_year)

        excluded_count_by_section = {
            ServiceGroupSection.income: 0,
            ServiceGroupSection.expense: 0,
            ServiceGroupSection.neutral: 0,
        }
        excluded_amount_by_section = {
            ServiceGroupSection.income: Decimal("0"),
            ServiceGroupSection.expense: Decimal("0"),
            ServiceGroupSection.neutral: Decimal("0"),
        }
        if excluded_rows:
            line_rows_excluded_with_service = (
                await self._session.exec(
                    select(JournalLine.service_id, JournalLine.amount)
                    .where(
                        col(JournalLine.account_id).in_(account_ids),
                        JournalLine.service_id.is_not(None),
                        text("journal_lines.valuta_date LIKE :valuta_year").bindparams(valuta_year=f"{year:04d}-%"),
                        JournalLine.currency != base_currency,
                    )
                )
            ).all()
            for service_id, amount in line_rows_excluded_with_service:
                if service_id not in service_section:
                    continue
                section = service_section[service_id]
                excluded_count_by_section[section] += 1
                excluded_amount_by_section[section] += Decimal(str(amount))

        section_payload: dict[str, IncomeExpenseSection] = {}

        for section in (ServiceGroupSection.income, ServiceGroupSection.expense, ServiceGroupSection.neutral):
            section_groups = groups_by_section[section]
            group_rows: list[IncomeExpenseGroupRow] = []
            section_totals = _empty_cells()
            for group in section_groups:
                subtotal = _empty_cells()
                services_in_group: list[IncomeExpenseServiceRow] = []

                assigned_service_ids = [
                    assignment.service_id
                    for assignment in assignment_by_service.values()
                    if assignment.service_group_id == group.id and assignment.service_id in grouped_services
                ]
                active_years_in_group = sorted(
                    {
                        active_year
                        for service_id in assigned_service_ids
                        for active_year in active_years_by_service.get(service_id, set())
                    }
                )
                for service_id in sorted(assigned_service_ids, key=lambda item: grouped_services[item].name.lower()):
                    service = grouped_services[service_id]
                    if service_section[service_id] != section:
                        continue

                    service_cells = _empty_cells()
                    monthly_gross = gross_by_service_month.get(service_id, {})
                    for month_key in MONTH_KEYS:
                        gross_value = monthly_gross.get(month_key, Decimal("0"))
                        service_cells[month_key]["gross"] = gross_value
                        service_cells["year_total"]["gross"] += gross_value

                    tax_rate = Decimal(str(service.tax_rate))
                    divisor = Decimal("1") + (tax_rate / Decimal("100"))
                    for cell_key in ["year_total", *MONTH_KEYS]:
                        gross_value = service_cells[cell_key]["gross"]
                        service_cells[cell_key]["net"] = (gross_value / divisor) if divisor != Decimal("0") else gross_value

                        subtotal[cell_key]["gross"] += service_cells[cell_key]["gross"]
                        subtotal[cell_key]["net"] += service_cells[cell_key]["net"]

                        section_totals[cell_key]["gross"] += service_cells[cell_key]["gross"]
                        section_totals[cell_key]["net"] += service_cells[cell_key]["net"]

                    services_in_group.append(
                        IncomeExpenseServiceRow(
                            service_id=service.id,
                            service_name=service.name,
                            partner_name=service_partner_name.get(service.id),
                            service_type=service.service_type,
                            erfolgsneutral=service.erfolgsneutral,
                            cells=_to_cells_payload(service_cells),
                        )
                    )

                group_rows.append(
                    IncomeExpenseGroupRow(
                        group_id=group.id,
                        group_name=group.name,
                        sort_order=group.sort_order,
                        collapsed=False,
                        assigned_service_count=len(assigned_service_ids),
                        active_years=active_years_in_group,
                        subtotal_cells=_to_cells_payload(subtotal),
                        services=services_in_group,
                    )
                )

            section_payload[section.value] = IncomeExpenseSection(
                currency=base_currency,
                excluded_currency_count=excluded_count_by_section[section],
                excluded_currency_amount_gross=_as_money(excluded_amount_by_section[section]),
                groups=group_rows,
                totals=_to_cells_payload(section_totals),
            )

        return IncomeExpenseMatrixResponse(
            year=year,
            base_currency=base_currency,
            sections=section_payload,
        )

    # ─── Bulk-assign ─────────────────────────────────────────────────────────

    async def bulk_assign(
        self,
        mandant_id: UUID,
        actor_id: UUID,
        line_ids: list[UUID],
        partner_id: UUID,
    ) -> BulkAssignResponse:
        if not line_ids:
            return BulkAssignResponse(assigned=0, skipped=0)

        # Security: resolve all mandant accounts once
        account_ids_res = await self._session.exec(
            select(Account.id).where(Account.mandant_id == mandant_id)  # type: ignore[arg-type]
        )
        mandant_account_ids = set(account_ids_res.all())

        lines_res = await self._session.exec(
            select(JournalLine).where(col(JournalLine.id).in_(line_ids))
        )
        lines = lines_res.all()

        # Reject request if any requested line belongs to a different mandant
        foreign = [ln for ln in lines if ln.account_id not in mandant_account_ids]
        if foreign:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="One or more journal lines do not belong to this mandant",
            )

        assigned = 0
        skipped = 0
        changed_lines: list[JournalLine] = []
        for ln in lines:
            if ln.partner_id == partner_id:
                skipped += 1
                continue
            changed_lines.append(ln)
            assigned += 1

        service_svc = ServiceManagementService(self._session)
        await service_svc.prepare_lines_for_partner_change(mandant_id, changed_lines, partner_id)

        # Single audit log entry for the whole operation
        entry = AuditLog(
            mandant_id=mandant_id,
            event_type="journal.bulk_assign",
            actor_id=actor_id,
            payload={
                "partner_id": str(partner_id),
                "line_ids": [str(lid) for lid in line_ids],
                "assigned": assigned,
                "skipped": skipped,
            },
        )
        self._session.add(entry)

        if assigned > 0:
            await service_svc.revalidate_partner_lines(partner_id)
        else:
            await self._session.commit()

        log.info(
            "journal_bulk_assigned",
            mandant_id=str(mandant_id),
            partner_id=str(partner_id),
            assigned=assigned,
        )
        return BulkAssignResponse(assigned=assigned, skipped=skipped)

    async def assign_service(
        self,
        mandant_id: UUID,
        actor_id: UUID,
        line_id: UUID,
        service_id: UUID,
    ) -> JournalLineResponse:
        line = await self._session.get(JournalLine, line_id)
        if line is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal line not found")

        account = await self._session.get(Account, line.account_id)
        if account is None or account.mandant_id != mandant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Journal line does not belong to this mandant")

        service_svc = ServiceManagementService(self._session)
        await service_svc.manually_assign_journal_line(mandant_id, line, service_id)

        self._session.add(
            AuditLog(
                mandant_id=mandant_id,
                event_type="journal.service_assigned",
                actor_id=actor_id,
                payload={
                    "journal_line_id": str(line.id),
                    "service_id": str(service_id),
                },
            )
        )
        await self._session.commit()
        await self._session.refresh(line)

        partner_name = None
        if line.partner_id is not None:
            partner = await self._session.get(Partner, line.partner_id)
            if partner is not None:
                partner_name = partner.display_name or partner.name

        service_name = None
        if line.service_id is not None:
            service = await self._session.get(Service, line.service_id)
            if service is not None:
                service_name = service.name

        return JournalLineResponse(
            **{
                **{key: value for key, value in line.model_dump().items() if key != "unmapped_data"},
                "unmapped_data": _sanitize_unmapped_data(line.unmapped_data),
            },
            service_name=service_name,
            partner_name=partner_name,
        )
