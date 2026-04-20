import { Fragment, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { faPenToSquare, faTrashCan } from '@fortawesome/free-regular-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { getIncomeExpenseMatrix, listJournalYears } from '@/api/journal'
import type { IncomeExpenseGroupRow, IncomeExpenseSection, MatrixCells } from '@/api/journal'
import { assignServiceGroup, createServiceGroup, deleteServiceGroup, updateServiceGroup } from '@/api/services'
import type { ServiceGroupSection } from '@/api/services'
import { useAuthStore } from '@/store/auth-store'

const BASE_SERVICE_NAME = 'Basisleistung'
const MONTH_KEYS: Array<keyof MatrixCells> = ['year_total', 'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
const HEADERS = ['Jahr', 'Jan', 'Feb', 'Mar', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
const LABEL_COLUMN_WIDTH_CLASS = 'w-[26rem]'
const VALUE_COLUMN_WIDTH_CLASS = 'w-[6.5rem]'
const SECTION_LABELS: Record<ServiceGroupSection, string> = {
  income: 'Einnahmen',
  expense: 'Ausgaben',
  neutral: 'Erfolgsneutrale Zahlungen',
}
const EDIT_ROLES = new Set(['accountant', 'mandant_admin', 'admin'])
const YEAR_COLUMN_INDEX = 0

interface GroupRef {
  id: string
  name: string
  section: ServiceGroupSection
  assignedServiceCount: number
  currentYearServiceCount: number
  activeYears: number[]
}

interface CreateGroupDialogState {
  open: boolean
  section: ServiceGroupSection
}

interface RenameGroupDialogState {
  open: boolean
  group: GroupRef | null
}

interface DeleteGroupDialogState {
  open: boolean
  group: GroupRef | null
}

type CollapsedGroupsBySection = Record<ServiceGroupSection, Set<string>>
type ViewMode = 'year' | 'multi-year'

interface PeriodColumn {
  key: string
  label: string
}

interface DisplayServiceRow extends Omit<IncomeExpenseGroupRow['services'][number], 'cells'> {
  periodValues: string[]
}

interface DisplayGroupRow extends Omit<IncomeExpenseGroupRow, 'subtotal_cells' | 'services'> {
  periodValues: string[]
  services: DisplayServiceRow[]
}

interface DisplaySection extends Omit<IncomeExpenseSection, 'groups' | 'totals'> {
  groups: DisplayGroupRow[]
  totals: string[]
}

interface DisplaySections {
  income: DisplaySection
  expense: DisplaySection
  neutral: DisplaySection
}

function formatMoney(value: string, currency: string): string {
  const numeric = Number.parseFloat(value)
  if (Number.isNaN(numeric)) {
    return currency === 'EUR' ? '0' : `0 ${currency}`
  }
  const formatted = numeric.toLocaleString('de-AT', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
  return currency === 'EUR' ? formatted : `${formatted} ${currency}`
}

function cellsToArray(cells: MatrixCells): string[] {
  return MONTH_KEYS.map((key) => cells[key].net)
}

function parseAmount(value: string): number {
  const numeric = Number.parseFloat(value)
  return Number.isNaN(numeric) ? 0 : numeric
}

function formatAmount(value: number): string {
  return value.toFixed(2)
}

function sumAmounts(values: string[]): string {
  return formatAmount(values.reduce((sum, value) => sum + parseAmount(value), 0))
}

function buildPeriodValues(values: string[]): string[] {
  return [sumAmounts(values), ...values]
}

function hasNonZeroAmount(value: string): boolean {
  return Math.abs(parseAmount(value)) > 0.0000001
}

function hasNonZeroPeriodValues(values: string[]): boolean {
  return values.some((value) => hasNonZeroAmount(value))
}

function hasNonZeroYearTotal(cells: MatrixCells): boolean {
  const numeric = Number.parseFloat(cells.year_total.net)
  return !Number.isNaN(numeric) && Math.abs(numeric) > 0.0000001
}

function getPeriodTotal(periodValues: string[]): number {
  return parseAmount(periodValues[0] ?? '0.00')
}

function compareServicesByPeriodTotal(
  sectionKey: ServiceGroupSection,
  left: DisplayServiceRow,
  right: DisplayServiceRow,
): number {
  const leftTotal = getPeriodTotal(left.periodValues)
  const rightTotal = getPeriodTotal(right.periodValues)

  if (sectionKey === 'expense') {
    return leftTotal - rightTotal
  }

  return rightTotal - leftTotal
}

function getServiceDisplayName(service: IncomeExpenseGroupRow['services'][number]): string {
  if (service.partner_name) {
    if (service.service_name === BASE_SERVICE_NAME) {
      return service.partner_name
    }
    if (service.partner_name === service.service_name) {
      return service.partner_name
    }
    return `${service.partner_name} / ${service.service_name}`
  }
  return service.service_name
}

function toDisplaySection(section: IncomeExpenseSection): DisplaySection {
  return {
    ...section,
    groups: section.groups.map((group) => ({
      ...group,
      periodValues: cellsToArray(group.subtotal_cells),
      services: group.services.map((service) => ({
        ...service,
        periodValues: cellsToArray(service.cells),
      })),
    })),
    totals: cellsToArray(section.totals),
  }
}

function buildYearDisplaySections(sections: IncomeExpenseMatrixResponse['sections']): DisplaySections {
  return {
    income: toDisplaySection(sections.income),
    expense: toDisplaySection(sections.expense),
    neutral: toDisplaySection(sections.neutral),
  }
}

function buildMultiYearDisplaySections(
  matrices: IncomeExpenseMatrixResponse[],
  years: number[],
): DisplaySections {
  function buildSection(sectionKey: ServiceGroupSection): DisplaySection {
    const groups = new Map<string, {
      group_id: string
      group_name: string
      sort_order: number
      collapsed: boolean
      assigned_service_count: number
      active_years: Set<number>
      periodValuesByYear: Map<number, string>
      services: Map<string, DisplayServiceRow & { periodValuesByYear: Map<number, string> }>
    }>()
    const totalsByYear = new Map<number, string>()
    let currency = 'EUR'
    let excludedCurrencyCount = 0
    let excludedCurrencyAmount = 0

    function upsertService(
      targetGroup: {
        services: Map<string, DisplayServiceRow & { periodValuesByYear: Map<number, string> }>
      },
      service: IncomeExpenseGroupRow['services'][number],
      year: number,
    ) {
      const existingService = targetGroup.services.get(service.service_id)
      if (existingService) {
        existingService.service_name = service.service_name
        existingService.partner_name = service.partner_name
        existingService.service_type = service.service_type
        existingService.erfolgsneutral = service.erfolgsneutral
        existingService.periodValuesByYear.set(year, service.cells.year_total.net)
        return
      }

      targetGroup.services.set(service.service_id, {
        ...service,
        periodValues: [],
        periodValuesByYear: new Map([[year, service.cells.year_total.net]]),
      })
    }

    function upsertGroup(section: IncomeExpenseSection, group: IncomeExpenseGroupRow, year: number) {
      currency = section.currency
      const existingGroup = groups.get(group.group_id)
      if (existingGroup) {
        existingGroup.group_name = group.group_name
        existingGroup.sort_order = group.sort_order
        existingGroup.assigned_service_count = Math.max(existingGroup.assigned_service_count, group.assigned_service_count)
        for (const activeYear of group.active_years) {
          existingGroup.active_years.add(activeYear)
        }
        existingGroup.periodValuesByYear.set(year, group.subtotal_cells.year_total.net)
        return existingGroup
      }

      const nextGroup = {
        group_id: group.group_id,
        group_name: group.group_name,
        sort_order: group.sort_order,
        collapsed: group.collapsed,
        assigned_service_count: group.assigned_service_count,
        active_years: new Set(group.active_years),
        periodValuesByYear: new Map([[year, group.subtotal_cells.year_total.net]]),
        services: new Map<string, DisplayServiceRow & { periodValuesByYear: Map<number, string> }>(),
      }
      groups.set(group.group_id, nextGroup)
      return nextGroup
    }

    function toDisplayService(service: DisplayServiceRow & { periodValuesByYear: Map<number, string> }): DisplayServiceRow {
      const serviceYearlyValues = years.map((entryYear) => service.periodValuesByYear.get(entryYear) ?? '0.00')
      return {
        service_id: service.service_id,
        service_name: service.service_name,
        partner_name: service.partner_name,
        service_type: service.service_type,
        erfolgsneutral: service.erfolgsneutral,
        periodValues: buildPeriodValues(serviceYearlyValues),
      }
    }

    for (const [index, matrix] of matrices.entries()) {
      const year = years[index]
      if (year === undefined) {
        continue
      }

      const section = matrix.sections[sectionKey]
      currency = section.currency
      excludedCurrencyCount += section.excluded_currency_count
      excludedCurrencyAmount += parseAmount(section.excluded_currency_amount_gross)
      totalsByYear.set(year, section.totals.year_total.net)

      for (const group of section.groups) {
        const targetGroup = upsertGroup(section, group, year)
        for (const service of group.services) {
          upsertService(targetGroup, service, year)
        }
      }
    }

    return {
      currency,
      excluded_currency_count: excludedCurrencyCount,
      excluded_currency_amount_gross: formatAmount(excludedCurrencyAmount),
      groups: [...groups.values()]
        .sort((left, right) => left.sort_order - right.sort_order || left.group_name.localeCompare(right.group_name, 'de'))
        .map((group) => {
          const yearlyValues = years.map((year) => group.periodValuesByYear.get(year) ?? '0.00')
          return {
            group_id: group.group_id,
            group_name: group.group_name,
            sort_order: group.sort_order,
            collapsed: group.collapsed,
            assigned_service_count: group.assigned_service_count,
            active_years: [...group.active_years].sort((left, right) => left - right),
            periodValues: buildPeriodValues(yearlyValues),
            services: [...group.services.values()].map(toDisplayService),
          }
        }),
      totals: buildPeriodValues(years.map((year) => totalsByYear.get(year) ?? '0.00')),
    }
  }

  return {
    income: buildSection('income'),
    expense: buildSection('expense'),
    neutral: buildSection('neutral'),
  }
}

function parseDragPayload(raw: string): { serviceId: string; section: ServiceGroupSection } | null {
  try {
    const parsed = JSON.parse(raw) as { serviceId?: string; section?: string }
    if (!parsed.serviceId || !parsed.section) {
      return null
    }
    if (parsed.section !== 'income' && parsed.section !== 'expense' && parsed.section !== 'neutral') {
      return null
    }
    return { serviceId: parsed.serviceId, section: parsed.section }
  } catch {
    return null
  }
}

function parseGroupDragPayload(raw: string): { groupId: string; section: ServiceGroupSection } | null {
  try {
    const parsed = JSON.parse(raw) as { groupId?: string; section?: string }
    if (!parsed.groupId || !parsed.section) {
      return null
    }
    if (parsed.section !== 'income' && parsed.section !== 'expense' && parsed.section !== 'neutral') {
      return null
    }
    return { groupId: parsed.groupId, section: parsed.section }
  } catch {
    return null
  }
}

function getDragPayload(dataTransfer: DataTransfer, type: 'group' | 'service'): string {
  const customType = type === 'group' ? 'application/x-cashflow-group' : 'application/x-cashflow-service'
  const customPayload = dataTransfer.getData(customType)
  if (customPayload) {
    return customPayload
  }
  return dataTransfer.getData('text/plain')
}

function reorderItems(itemIds: string[], activeId: string, targetId: string): string[] {
  const activeIndex = itemIds.indexOf(activeId)
  const targetIndex = itemIds.indexOf(targetId)
  if (activeIndex === -1 || targetIndex === -1 || activeIndex === targetIndex) {
    return itemIds
  }
  const next = [...itemIds]
  const [movedItem] = next.splice(activeIndex, 1)
  next.splice(targetIndex, 0, movedItem)
  return next
}

function OverlayDialog({
  open,
  title,
  children,
  onClose,
}: Readonly<{
  open: boolean
  title: string
  children: ReactNode
  onClose: () => void
}>) {
  if (!open) {
    return null
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-900/50 px-4">
      <div className="w-full max-w-lg rounded-xl border border-gray-200 bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
          <button type="button" onClick={onClose} className="rounded px-2 py-1 text-xs text-gray-500 hover:bg-gray-100">
            Schließen
          </button>
        </div>
        <div className="px-4 py-4">{children}</div>
      </div>
    </div>
  )
}

function EditIcon() {
  return <FontAwesomeIcon icon={faPenToSquare} aria-hidden="true" className="h-3 w-3" />
}

function TrashIcon() {
  return <FontAwesomeIcon icon={faTrashCan} aria-hidden="true" className="h-3 w-3" />
}

function SectionTable({
  title,
  columns,
  sectionKey,
  section,
  canEdit,
  onRequestCreateGroup,
  onRequestRenameGroup,
  onRequestDeleteGroup,
  onAssignService,
  onReorderGroups,
  collapsedGroups,
  onToggleGroup,
  onSetCollapsedGroups,
  pendingServiceId,
  pendingGroupIds,
}: Readonly<{
  title: string
  columns: PeriodColumn[]
  sectionKey: ServiceGroupSection
  section: DisplaySection
  canEdit: boolean
  onRequestCreateGroup: (section: ServiceGroupSection) => void
  onRequestRenameGroup: (group: GroupRef) => void
  onRequestDeleteGroup: (group: GroupRef) => void
  onAssignService: (serviceId: string, groupId: string) => void
  onReorderGroups: (orderedGroupIds: string[]) => void
  collapsedGroups: Set<string>
  onToggleGroup: (groupId: string) => void
  onSetCollapsedGroups: (updater: (prev: Set<string>) => Set<string>) => void
  pendingServiceId: string | null
  pendingGroupIds: string[]
}>) {
  const [dragOverGroupId, setDragOverGroupId] = useState<string | null>(null)
  const visibleGroups = useMemo(
    () => section.groups
      .map((group) => ({
        ...group,
        services: group.services
          .filter((service) => hasNonZeroPeriodValues(service.periodValues))
          .sort((left, right) => compareServicesByPeriodTotal(sectionKey, left, right)),
      }))
      .filter((group) => group.services.length > 0 || canEdit),
    [canEdit, section.groups, sectionKey],
  )
  const showTotals = hasNonZeroPeriodValues(section.totals)
  const excludedCurrencyAmount = Number.parseFloat(section.excluded_currency_amount_gross)
  const showExcludedCurrencyInfo = section.excluded_currency_count > 0
    || (!Number.isNaN(excludedCurrencyAmount) && Math.abs(excludedCurrencyAmount) > 0.0000001)
  const visibleGroupIds = visibleGroups.map((group) => group.group_id)
  const hasVisibleGroups = visibleGroupIds.length > 0
  const areAllVisibleGroupsCollapsed = hasVisibleGroups && visibleGroupIds.every((groupId) => collapsedGroups.has(groupId))

  function toggleAllGroups() {
    onSetCollapsedGroups((prev) => {
      if (!hasVisibleGroups) {
        return prev
      }

      const next = new Set(prev)
      if (areAllVisibleGroupsCollapsed) {
        visibleGroupIds.forEach((groupId) => next.delete(groupId))
      } else {
        visibleGroupIds.forEach((groupId) => next.add(groupId))
      }
      return next
    })
  }

  function handleGroupDrop(groupId: string, rawPayload: string) {
    const payload = parseDragPayload(rawPayload)
    if (!payload) {
      return
    }
    if (payload.section !== sectionKey) {
      globalThis.alert('Verschieben nur innerhalb derselben Sektion erlaubt.')
      return
    }
    onAssignService(payload.serviceId, groupId)
  }

  function handleGroupReorderDrop(targetGroupId: string, rawPayload: string) {
    const payload = parseGroupDragPayload(rawPayload)
    setDragOverGroupId(null)
    if (!payload) {
      return
    }
    if (payload.section !== sectionKey || payload.groupId === targetGroupId) {
      return
    }
    const orderedGroupIds = reorderItems(
      visibleGroups.map((group) => group.group_id),
      payload.groupId,
      targetGroupId,
    )
    onReorderGroups(orderedGroupIds)
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
      <header className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
        <h2 className="text-base font-semibold text-gray-900">{title}</h2>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={toggleAllGroups}
            disabled={!hasVisibleGroups}
            className="rounded border border-gray-300 px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:border-gray-200 disabled:text-gray-400 disabled:hover:bg-white"
          >
            {areAllVisibleGroupsCollapsed ? 'Alle aufklappen' : 'Alle zuklappen'}
          </button>
          {canEdit && (
            <button
              type="button"
              onClick={() => onRequestCreateGroup(sectionKey)}
              className="rounded bg-gray-900 px-2 py-1 text-xs font-medium text-white hover:bg-gray-700"
            >
              Gruppe anlegen
            </button>
          )}
          {showExcludedCurrencyInfo && (
            <div className="text-xs text-gray-500">
              Ausgeschlossene Fremdwährungen: {section.excluded_currency_count} ({formatMoney(section.excluded_currency_amount_gross, section.currency)})
            </div>
          )}
        </div>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1200px] table-fixed text-sm">
          <colgroup>
            <col className={LABEL_COLUMN_WIDTH_CLASS} />
            {columns.map((column) => (
              <col key={`${sectionKey}-col-${column.key}`} className={VALUE_COLUMN_WIDTH_CLASS} />
            ))}
          </colgroup>
          <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="sticky left-0 z-10 bg-gray-50 px-4 py-2 text-left">Leistung / Gruppe</th>
              {columns.map((column, index) => (
                <th
                  key={column.key}
                  className={`px-3 py-2 text-right ${index === YEAR_COLUMN_INDEX ? 'bg-amber-100 font-semibold text-amber-900' : ''}`}
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {visibleGroups.map((group: IncomeExpenseGroupRow) => {
              const isCollapsed = collapsedGroups.has(group.group_id)
              const isPendingGroup = pendingGroupIds.includes(group.group_id)
              const isDropTarget = dragOverGroupId === group.group_id
              return (
                <Fragment key={group.group_id}>
                  <tr
                    key={`${group.group_id}-subtotal`}
                    draggable={canEdit}
                    className={`font-semibold text-gray-800 ${isDropTarget ? 'bg-amber-100' : 'bg-gray-50'} ${isPendingGroup ? 'opacity-60' : ''} ${canEdit ? 'cursor-grab' : ''}`}
                    onDragStart={(event) => {
                      if (!canEdit) {
                        return
                      }
                      const payload = JSON.stringify({ groupId: group.group_id, section: sectionKey })
                      event.dataTransfer.setData(
                        'application/x-cashflow-group',
                        payload,
                      )
                      event.dataTransfer.setData('text/plain', payload)
                      event.dataTransfer.effectAllowed = 'move'
                    }}
                    onDragEnd={() => setDragOverGroupId(null)}
                    onDragOver={(event) => {
                      if (canEdit) {
                        event.preventDefault()
                        setDragOverGroupId(group.group_id)
                      }
                    }}
                    onDragLeave={() => {
                      if (dragOverGroupId === group.group_id) {
                        setDragOverGroupId(null)
                      }
                    }}
                    onDrop={(event) => {
                      if (!canEdit) {
                        return
                      }
                      event.preventDefault()
                      const groupPayload = getDragPayload(event.dataTransfer, 'group')
                      if (parseGroupDragPayload(groupPayload)) {
                        handleGroupReorderDrop(group.group_id, groupPayload)
                        return
                      }
                      handleGroupDrop(group.group_id, getDragPayload(event.dataTransfer, 'service'))
                    }}
                  >
                    <td className={`sticky left-0 z-10 px-4 py-2 text-left ${isDropTarget ? 'bg-amber-100' : 'bg-gray-50'}`}>
                      <button
                        type="button"
                        onClick={() => onToggleGroup(group.group_id)}
                        className="mr-2 text-xs text-gray-600"
                      >
                        {isCollapsed ? '▶' : '▼'}
                      </button>
                      {group.group_name}
                      {canEdit && (
                        <span className="ml-2 inline-flex items-center gap-px align-middle">
                          <button
                            type="button"
                            onClick={() => onRequestRenameGroup({
                              id: group.group_id,
                              name: group.group_name,
                              section: sectionKey,
                              assignedServiceCount: group.assigned_service_count,
                              currentYearServiceCount: group.services.length,
                              activeYears: group.active_years,
                            })}
                            aria-label={`Gruppe ${group.group_name} umbenennen`}
                            title="Gruppe umbenennen"
                            className="inline-flex h-5 w-5 items-center justify-center rounded text-gray-500 hover:bg-gray-200/70 hover:text-gray-700"
                          >
                            <EditIcon />
                          </button>
                          <button
                            type="button"
                            onClick={() => onRequestDeleteGroup({
                              id: group.group_id,
                              name: group.group_name,
                              section: sectionKey,
                              assignedServiceCount: group.assigned_service_count,
                              currentYearServiceCount: group.services.length,
                              activeYears: group.active_years,
                            })}
                            aria-label={`Gruppe ${group.group_name} löschen`}
                            title="Gruppe löschen"
                            className="inline-flex h-5 w-5 items-center justify-center rounded text-gray-500 hover:bg-red-100/70 hover:text-red-600"
                          >
                            <TrashIcon />
                          </button>
                        </span>
                      )}
                    </td>
                    {group.periodValues.map((value, index) => (
                      <td
                        key={`${group.group_id}-sub-${index}`}
                        className={`px-3 py-2 text-right ${index === YEAR_COLUMN_INDEX ? 'bg-amber-50 text-amber-950' : ''}`}
                      >
                        {formatMoney(value, section.currency)}
                      </td>
                    ))}
                  </tr>
                  {!isCollapsed && group.services.map((service) => {
                    const serviceDisplayName = getServiceDisplayName(service)
                    return (
                      <tr
                        key={service.service_id}
                        className={`text-gray-700 ${pendingServiceId === service.service_id ? 'bg-amber-50' : ''}`}
                        draggable={canEdit}
                        onDragStart={(event) => {
                          if (!canEdit) {
                            return
                          }
                          const payload = JSON.stringify({ serviceId: service.service_id, section: sectionKey })
                          event.dataTransfer.setData(
                            'application/x-cashflow-service',
                            payload,
                          )
                          event.dataTransfer.setData('text/plain', payload)
                          event.dataTransfer.effectAllowed = 'move'
                        }}
                      >
                        <td className="sticky left-0 z-10 bg-white px-4 py-2 text-left">
                          <span className="ml-6 block truncate" title={serviceDisplayName}>{serviceDisplayName}</span>
                        </td>
                      {service.periodValues.map((value, index) => (
                        <td
                          key={`${service.service_id}-${index}`}
                          className={`px-3 py-2 text-right ${index === YEAR_COLUMN_INDEX ? 'bg-amber-50/60 font-medium text-amber-950' : ''}`}
                        >
                          {formatMoney(value, section.currency)}
                        </td>
                      ))}
                      </tr>
                    )
                  })}
                </Fragment>
              )
            })}
            {showTotals && (
              <tr className="bg-gray-100 font-semibold text-gray-900">
                <td className="sticky left-0 z-10 bg-gray-100 px-4 py-2 text-left">Gesamtsumme</td>
                {section.totals.map((value, index) => (
                  <td
                    key={`total-${sectionKey}-${index}`}
                    className={`px-3 py-2 text-right ${index === YEAR_COLUMN_INDEX ? 'bg-amber-100 text-amber-950' : ''}`}
                  >
                    {formatMoney(value, section.currency)}
                  </td>
                ))}
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function IncomeExpensePage() {
  const mandantId = useAuthStore((s) => s.user?.mandant_id ?? '')
  const role = useAuthStore((s) => s.user?.role ?? '')
  const [year, setYear] = useState<number>(new Date().getFullYear())
  const [viewMode, setViewMode] = useState<ViewMode>('year')
  const [pendingServiceId, setPendingServiceId] = useState<string | null>(null)
  const [createDialog, setCreateDialog] = useState<CreateGroupDialogState>({ open: false, section: 'income' })
  const [renameDialog, setRenameDialog] = useState<RenameGroupDialogState>({ open: false, group: null })
  const [deleteDialog, setDeleteDialog] = useState<DeleteGroupDialogState>({ open: false, group: null })
  const [newGroupName, setNewGroupName] = useState('')
  const [renameGroupName, setRenameGroupName] = useState('')
  const [pendingGroupIds, setPendingGroupIds] = useState<string[]>([])
  const [collapsedGroupsBySection, setCollapsedGroupsBySection] = useState<CollapsedGroupsBySection>({
    income: new Set(),
    expense: new Set(),
    neutral: new Set(),
  })
  const queryClient = useQueryClient()
  const canEdit = EDIT_ROLES.has(role)

  const yearMatrixQuery = useQuery({
    queryKey: ['income-expense-matrix', mandantId, year],
    queryFn: () => getIncomeExpenseMatrix(mandantId, year),
    enabled: !!mandantId && viewMode === 'year',
  })

  const { data: yearsData } = useQuery({
    queryKey: ['journal-years', mandantId],
    queryFn: () => listJournalYears(mandantId),
    enabled: !!mandantId,
  })

  const availableYears = useMemo(
    () => [...(yearsData?.years ?? [])].sort((left, right) => left - right),
    [yearsData?.years],
  )

  const multiYearMatrixQuery = useQuery({
    queryKey: ['income-expense-multi-matrix', mandantId, availableYears.join(',')],
    queryFn: () => Promise.all(availableYears.map((entryYear) => getIncomeExpenseMatrix(mandantId, entryYear))),
    enabled: !!mandantId && viewMode === 'multi-year' && availableYears.length > 0,
  })

  const canGoToPreviousYear = availableYears.includes(year - 1)
  const canGoToNextYear = availableYears.includes(year + 1)

  const sections = useMemo<DisplaySections | null>(() => {
    if (viewMode === 'multi-year') {
      if (!multiYearMatrixQuery.data || availableYears.length === 0) {
        return null
      }
      return buildMultiYearDisplaySections(multiYearMatrixQuery.data, availableYears)
    }

    if (!yearMatrixQuery.data) {
      return null
    }
    return buildYearDisplaySections(yearMatrixQuery.data.sections)
  }, [availableYears, multiYearMatrixQuery.data, viewMode, yearMatrixQuery.data])

  const periodColumns = useMemo<PeriodColumn[]>(() => {
    if (viewMode === 'multi-year') {
      return [
        { key: 'total', label: 'Gesamt' },
        ...availableYears.map((entryYear) => ({ key: String(entryYear), label: String(entryYear) })),
      ]
    }
    return [
      { key: 'year_total', label: 'Jahr' },
      ...MONTH_KEYS.slice(1).map((key, index) => ({ key, label: HEADERS[index + 1] })),
    ]
  }, [availableYears, viewMode])

  const isLoading = viewMode === 'multi-year' ? multiYearMatrixQuery.isLoading : yearMatrixQuery.isLoading
  const isError = viewMode === 'multi-year' ? multiYearMatrixQuery.isError : yearMatrixQuery.isError
  const error = viewMode === 'multi-year' ? multiYearMatrixQuery.error : yearMatrixQuery.error

  const groupsBySection = useMemo(() => {
    if (!sections) {
      return {
        income: [],
        expense: [],
        neutral: [],
      }
    }
    return {
      income: sections.income.groups,
      expense: sections.expense.groups,
      neutral: sections.neutral.groups,
    }
  }, [sections])

  function invalidateMatrixQueries() {
    queryClient.invalidateQueries({ queryKey: ['income-expense-matrix', mandantId] })
    queryClient.invalidateQueries({ queryKey: ['income-expense-multi-matrix', mandantId] })
  }

  const createGroupMutation = useMutation({
    mutationFn: ({ section, name, sortOrder }: { section: ServiceGroupSection; name: string; sortOrder: number }) =>
      createServiceGroup(mandantId, { section, name, sort_order: sortOrder }),
    onSuccess: () => {
      invalidateMatrixQueries()
    },
  })

  const renameGroupMutation = useMutation({
    mutationFn: ({ groupId, name }: { groupId: string; name: string }) =>
      updateServiceGroup(mandantId, groupId, { name }),
    onSuccess: () => {
      invalidateMatrixQueries()
    },
  })

  const deleteGroupMutation = useMutation({
    mutationFn: ({ groupId, reassignToGroupId }: { groupId: string; reassignToGroupId?: string }) =>
      deleteServiceGroup(mandantId, groupId, reassignToGroupId ? { reassign_to_group_id: reassignToGroupId } : {}),
    onSuccess: () => {
      invalidateMatrixQueries()
    },
  })

  const assignServiceMutation = useMutation({
    mutationFn: ({ serviceId, groupId }: { serviceId: string; groupId: string }) =>
      assignServiceGroup(mandantId, serviceId, groupId),
    onMutate: ({ serviceId }) => {
      setPendingServiceId(serviceId)
    },
    onSettled: () => {
      setPendingServiceId(null)
      invalidateMatrixQueries()
    },
  })

  const reorderGroupsMutation = useMutation({
    mutationFn: async ({ section, orderedGroupIds }: { section: ServiceGroupSection; orderedGroupIds: string[] }) => {
      const currentGroups = groupsBySection[section]
      const currentSortOrders = new Map(currentGroups.map((group) => [group.group_id, group.sort_order]))
      const orderedSortValues = [...currentGroups]
        .map((group) => group.sort_order)
        .sort((left, right) => left - right)

      const updates = orderedGroupIds
        .map((groupId, index) => ({
          groupId,
          sortOrder: orderedSortValues[index] ?? index,
        }))
        .filter((entry) => currentSortOrders.get(entry.groupId) !== entry.sortOrder)

      await Promise.all(
        updates.map((entry) => updateServiceGroup(mandantId, entry.groupId, { sort_order: entry.sortOrder })),
      )
    },
    onMutate: ({ orderedGroupIds }) => {
      setPendingGroupIds(orderedGroupIds)
    },
    onSettled: () => {
      setPendingGroupIds([])
      invalidateMatrixQueries()
    },
  })

  function openCreateDialog(section: ServiceGroupSection) {
    setCreateDialog({ open: true, section })
    setNewGroupName('')
  }

  function openRenameDialog(group: GroupRef) {
    setRenameDialog({ open: true, group })
    setRenameGroupName(group.name)
  }

  function openDeleteDialog(group: GroupRef) {
    setDeleteDialog({ open: true, group })
  }

  function closeCreateDialog() {
    setCreateDialog((prev) => ({ ...prev, open: false }))
    setNewGroupName('')
  }

  function closeRenameDialog() {
    setRenameDialog({ open: false, group: null })
    setRenameGroupName('')
  }

  function closeDeleteDialog() {
    setDeleteDialog({ open: false, group: null })
  }

  function submitCreateGroup() {
    const name = newGroupName.trim()
    if (!name || !createDialog.open) {
      return
    }
    createGroupMutation.mutate(
      {
        section: createDialog.section,
        name,
        sortOrder: groupsBySection[createDialog.section].length + 1,
      },
      {
        onSuccess: () => closeCreateDialog(),
      },
    )
  }

  function submitRenameGroup() {
    const target = renameDialog.group
    const nextName = renameGroupName.trim()
    if (!target || !nextName || nextName === target.name) {
      return
    }
    renameGroupMutation.mutate(
      { groupId: target.id, name: nextName },
      {
        onSuccess: () => closeRenameDialog(),
      },
    )
  }

  function submitDeleteGroup() {
    const target = deleteDialog.group
    if (!target || target.assignedServiceCount > 0) {
      return
    }
    deleteGroupMutation.mutate({ groupId: target.id }, {
      onSuccess: () => closeDeleteDialog(),
    })
  }

  const deleteDialogHasAssignedServices = (deleteDialog.group?.assignedServiceCount ?? 0) > 0
  const deleteDialogOtherYears = (deleteDialog.group?.activeYears ?? []).filter((activeYear) => activeYear !== year)

  function toggleGroup(section: ServiceGroupSection, groupId: string) {
    setCollapsedGroupsBySection((prev) => {
      const nextSectionGroups = new Set(prev[section])
      if (nextSectionGroups.has(groupId)) {
        nextSectionGroups.delete(groupId)
      } else {
        nextSectionGroups.add(groupId)
      }
      return {
        ...prev,
        [section]: nextSectionGroups,
      }
    })
  }

  function setCollapsedGroupsForSection(section: ServiceGroupSection, updater: (prev: Set<string>) => Set<string>) {
    setCollapsedGroupsBySection((prev) => ({
      ...prev,
      [section]: updater(prev[section]),
    }))
  }

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-8 space-y-4">
      <header className="rounded-xl bg-gradient-to-r from-teal-700 to-emerald-700 px-5 py-4 text-white shadow">
        <h1 className="text-2xl font-semibold">Einnahmen & Ausgaben nach Zahlungsprinzip</h1>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-teal-100">
            {viewMode === 'multi-year'
              ? 'Jahressummen je Leistung und Gruppe über alle verfügbaren Jahre'
              : 'Monatsmatrix je Leistung mit Jahres- und Gruppensummen'}
          </p>
          <p className="text-xs uppercase tracking-wide text-teal-200">Alle Angaben in €</p>
        </div>
        {!canEdit && <p className="mt-2 text-xs text-teal-200">Read-only Modus: Gruppen und Zuordnungen sind nicht bearbeitbar.</p>}
      </header>

      <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3">
        {viewMode === 'year' ? (
          <>
            <button
              type="button"
              onClick={() => setYear((prev) => prev - 1)}
              disabled={!canGoToPreviousYear}
              className="rounded border px-3 py-1.5 text-sm hover:bg-gray-50 disabled:cursor-not-allowed disabled:border-gray-200 disabled:text-gray-400 disabled:hover:bg-white"
            >
              ◀ Vorjahr
            </button>
            <div className="rounded bg-gray-100 px-3 py-1.5 font-semibold text-gray-800">{year}</div>
            <button
              type="button"
              onClick={() => setYear((prev) => prev + 1)}
              disabled={!canGoToNextYear}
              className="rounded border px-3 py-1.5 text-sm hover:bg-gray-50 disabled:cursor-not-allowed disabled:border-gray-200 disabled:text-gray-400 disabled:hover:bg-white"
            >
              Folgejahr ▶
            </button>
            <button
              type="button"
              onClick={() => setViewMode('multi-year')}
              disabled={availableYears.length === 0}
              className="rounded border px-3 py-1.5 text-sm hover:bg-gray-50 disabled:cursor-not-allowed disabled:border-gray-200 disabled:text-gray-400 disabled:hover:bg-white"
            >
              Mehrjahresübersicht
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => setViewMode('year')}
              className="rounded border px-3 py-1.5 text-sm hover:bg-gray-50"
            >
              Zur Jahresansicht
            </button>
            <div className="rounded bg-gray-100 px-3 py-1.5 font-semibold text-gray-800">Mehrjahresübersicht</div>
            {availableYears.length > 0 && (
              <div className="text-sm text-gray-500">{availableYears[0]} bis {availableYears.at(-1)}</div>
            )}
          </>
        )}
      </div>

      {isLoading && (
        <div className="rounded-xl border border-gray-200 bg-white px-6 py-8 text-center text-gray-500">Daten werden geladen...</div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-6 py-4 text-sm text-red-700">
          Fehler beim Laden der Matrix: {error instanceof Error ? error.message : 'Unbekannter Fehler'}
        </div>
      )}

      {(createGroupMutation.isError || renameGroupMutation.isError || deleteGroupMutation.isError || assignServiceMutation.isError) && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-6 py-4 text-sm text-red-700">
          Bearbeitung fehlgeschlagen. Bitte Eingaben prüfen und erneut versuchen.
        </div>
      )}

      {sections && !isLoading && !isError && (
        <>
          <SectionTable
            title={SECTION_LABELS.income}
            columns={periodColumns}
            sectionKey="income"
            section={sections.income}
            canEdit={canEdit}
            onRequestCreateGroup={openCreateDialog}
            onRequestRenameGroup={openRenameDialog}
            onRequestDeleteGroup={openDeleteDialog}
            onAssignService={(serviceId, groupId) => assignServiceMutation.mutate({ serviceId, groupId })}
            onReorderGroups={(orderedGroupIds) => reorderGroupsMutation.mutate({ section: 'income', orderedGroupIds })}
            collapsedGroups={collapsedGroupsBySection.income}
            onToggleGroup={(groupId) => toggleGroup('income', groupId)}
            onSetCollapsedGroups={(updater) => setCollapsedGroupsForSection('income', updater)}
            pendingServiceId={pendingServiceId}
            pendingGroupIds={pendingGroupIds}
          />
          <SectionTable
            title={SECTION_LABELS.expense}
            columns={periodColumns}
            sectionKey="expense"
            section={sections.expense}
            canEdit={canEdit}
            onRequestCreateGroup={openCreateDialog}
            onRequestRenameGroup={openRenameDialog}
            onRequestDeleteGroup={openDeleteDialog}
            onAssignService={(serviceId, groupId) => assignServiceMutation.mutate({ serviceId, groupId })}
            onReorderGroups={(orderedGroupIds) => reorderGroupsMutation.mutate({ section: 'expense', orderedGroupIds })}
            collapsedGroups={collapsedGroupsBySection.expense}
            onToggleGroup={(groupId) => toggleGroup('expense', groupId)}
            onSetCollapsedGroups={(updater) => setCollapsedGroupsForSection('expense', updater)}
            pendingServiceId={pendingServiceId}
            pendingGroupIds={pendingGroupIds}
          />
          <SectionTable
            title={SECTION_LABELS.neutral}
            columns={periodColumns}
            sectionKey="neutral"
            section={sections.neutral}
            canEdit={canEdit}
            onRequestCreateGroup={openCreateDialog}
            onRequestRenameGroup={openRenameDialog}
            onRequestDeleteGroup={openDeleteDialog}
            onAssignService={(serviceId, groupId) => assignServiceMutation.mutate({ serviceId, groupId })}
            onReorderGroups={(orderedGroupIds) => reorderGroupsMutation.mutate({ section: 'neutral', orderedGroupIds })}
            collapsedGroups={collapsedGroupsBySection.neutral}
            onToggleGroup={(groupId) => toggleGroup('neutral', groupId)}
            onSetCollapsedGroups={(updater) => setCollapsedGroupsForSection('neutral', updater)}
            pendingServiceId={pendingServiceId}
            pendingGroupIds={pendingGroupIds}
          />
        </>
      )}

      <OverlayDialog
        open={createDialog.open}
        title={`Gruppe anlegen (${SECTION_LABELS[createDialog.section]})`}
        onClose={closeCreateDialog}
      >
        <div className="space-y-3">
          <input
            value={newGroupName}
            onChange={(event) => setNewGroupName(event.target.value)}
            placeholder="Gruppenname"
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
          />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={closeCreateDialog} className="rounded border border-gray-300 px-3 py-1.5 text-sm">Abbrechen</button>
            <button type="button" onClick={submitCreateGroup} className="rounded bg-gray-900 px-3 py-1.5 text-sm text-white">Anlegen</button>
          </div>
        </div>
      </OverlayDialog>

      <OverlayDialog
        open={renameDialog.open}
        title="Gruppe umbenennen"
        onClose={closeRenameDialog}
      >
        <div className="space-y-3">
          <input
            value={renameGroupName}
            onChange={(event) => setRenameGroupName(event.target.value)}
            placeholder="Neuer Gruppenname"
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
          />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={closeRenameDialog} className="rounded border border-gray-300 px-3 py-1.5 text-sm">Abbrechen</button>
            <button type="button" onClick={submitRenameGroup} className="rounded bg-gray-900 px-3 py-1.5 text-sm text-white">Speichern</button>
          </div>
        </div>
      </OverlayDialog>

      <OverlayDialog
        open={deleteDialog.open}
        title="Gruppe löschen"
        onClose={closeDeleteDialog}
      >
        <div className="space-y-3">
          <p className="text-sm text-gray-700">
            Gruppe <strong>{deleteDialog.group?.name}</strong> wirklich löschen?
          </p>

          {deleteDialogHasAssignedServices && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              <p>
                Diese Gruppe enthält noch {deleteDialog.group?.assignedServiceCount} Service{deleteDialog.group?.assignedServiceCount === 1 ? '' : 's'} und kann deshalb nicht gelöscht werden.
              </p>
              {deleteDialog.group?.currentYearServiceCount === 0 && deleteDialogOtherYears.length > 0 && (
                <p className="mt-1">
                  In der aktuellen Jahresansicht sind keine Services sichtbar. Zugeordnete Buchungen gibt es jedoch in den Jahren {deleteDialogOtherYears.join(', ')}.
                </p>
              )}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button type="button" onClick={closeDeleteDialog} className="rounded border border-gray-300 px-3 py-1.5 text-sm">Abbrechen</button>
            <button type="button" onClick={submitDeleteGroup} disabled={deleteDialogHasAssignedServices} className="rounded bg-red-600 px-3 py-1.5 text-sm text-white disabled:cursor-not-allowed disabled:bg-red-300">Löschen</button>
          </div>
        </div>
      </OverlayDialog>
    </div>
  )
}

export default IncomeExpensePage
