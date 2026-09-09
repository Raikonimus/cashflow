import { apiClient } from './client'

export type ForecastMode = 'auto' | 'manual' | 'off'

export type ForecastRuleType =
  | 'fixed_recurring'
  | 'rolling_average'
  | 'same_period_last_year'
  | 'seasonal_profile'
  | 'manual_plan'
  | 'none'

export type Scenario = 'expected' | 'low' | 'high'

export interface ForecastPreviewMonth {
  period: string
  amount: string
  is_planned: boolean
}

export interface ForecastRuleParams {
  amount?: string
  interval_months?: number
  anchor_month?: number
  window_months?: number
  special_months?: Record<string, string>
}

export interface BacktestCandidate {
  key: string
  label: string
  mae: string
  level_error: string
  score: string
  is_baseline: boolean
  is_winner: boolean
}

export interface Backtest {
  ran: boolean
  reason: string
  holdout_months: number
  holdout_from: string | null
  holdout_to: string | null
  actual_volume: string
  /** Anteil, z. B. "0.3663" für 37 % mittleren Fehler. */
  relative_error: string | null
  spread: string | null
  beats_baseline: boolean
  replaced_detected: boolean
  service_stopped: boolean
  candidates: BacktestCandidate[]
}

export interface ForecastRule {
  service_id: string
  service_name: string
  partner_name: string | null
  mode: ForecastMode
  rule_type: ForecastRuleType | null
  params: ForecastRuleParams | null
  adjustment_pct: string
  shift_months: number
  detected_cadence: string
  detected_rule_type: ForecastRuleType
  detected_reason: string
  occurrence_count: number
  median_amount: string
  effective_rule_type: ForecastRuleType
  effective_reason: string
  confidence: string | null
  preview: ForecastPreviewMonth[]
  backtest: Backtest | null
}

export interface UpdateForecastRuleRequest {
  mode: ForecastMode
  rule_type?: ForecastRuleType | null
  params?: ForecastRuleParams | null
  adjustment_pct: string
  shift_months: number
}

export interface ForecastServiceOverviewRow {
  service_id: string
  service_name: string
  partner_id: string
  partner_name: string | null
  section: string
  mode: ForecastMode
  effective_rule_type: ForecastRuleType
  effective_reason: string
  confidence: string | null
  detected_cadence: string
  occurrence_count: number
  last_booking_period: string | null
  next_12_months: string
  planned_item_count: number
  /** Modifikatoren — ohne sie saehe eine Leistung mit +100 % wie eine unberuehrte aus. */
  adjustment_pct: string
  shift_months: number
  /** Ob ueberhaupt etwas von Hand eingestellt ist. Wird im Backend entschieden, damit
   *  Zaehlung und Filter nicht auseinanderlaufen. */
  customised: boolean
  relative_error: string | null
  backtest_ran: boolean
  beats_baseline: boolean
  replaced_detected: boolean
  service_stopped: boolean
}

export interface ForecastOverview {
  services: ForecastServiceOverviewRow[]
  total: number
  without_rule: number
  customised: number
  backtested: number
  replaced_by_backtest: number
  stopped_by_backtest: number
  weak_forecasts: number
  median_relative_error: string | null
}

export interface SnapshotMonth {
  period: string
  planned_net: string
  planned_closing: string
  actual_net: string | null
  actual_closing: string | null
  net_deviation: string | null
  deviation: string | null
  is_complete: boolean
}

export interface SnapshotSummary {
  id: string
  label: string | null
  scenario: Scenario
  as_of: string
  currency: string
  start_balance: string
  created_at: string
  month_count: number
  elapsed_months: number
  latest_deviation: string | null
}

export interface SnapshotDetail extends SnapshotSummary {
  months: SnapshotMonth[]
  mean_absolute_deviation: string | null
}

/** Ein Planposten wird nie geloescht, wenn echte Buchungen eintreffen — er verliert nur
 *  seine Wirkung. Der Status sagt, was davon noch zaehlt. */
export type PlannedItemStatus = 'active' | 'partly_used' | 'used' | 'expired'

export interface PlannedItem {
  id: string
  service_id: string
  service_name: string | null
  partner_name: string | null
  period: string
  amount: string
  note: string | null
  created_at: string
  updated_at: string
  status: PlannedItemStatus
  /** Was von den Planposten dieses Monats noch erwartet wird — je Monat, nicht je Posten. */
  remaining_in_month: string
}

export async function getForecastOverview(
  mandantId: string,
  options: { onlyWithoutRule?: boolean; search?: string } = {},
): Promise<ForecastOverview> {
  const resp = await apiClient.get<ForecastOverview>(
    `/mandants/${mandantId}/forecast/services`,
    {
      params: {
        only_without_rule: options.onlyWithoutRule ? true : undefined,
        search: options.search || undefined,
      },
    },
  )
  return resp.data
}

export async function getForecastRule(
  mandantId: string,
  serviceId: string,
): Promise<ForecastRule> {
  const resp = await apiClient.get<ForecastRule>(
    `/mandants/${mandantId}/services/${serviceId}/forecast-rule`,
  )
  return resp.data
}

export async function setForecastRule(
  mandantId: string,
  serviceId: string,
  data: UpdateForecastRuleRequest,
): Promise<ForecastRule> {
  const resp = await apiClient.put<ForecastRule>(
    `/mandants/${mandantId}/services/${serviceId}/forecast-rule`,
    data,
  )
  return resp.data
}

export async function resetForecastRule(
  mandantId: string,
  serviceId: string,
): Promise<ForecastRule> {
  const resp = await apiClient.delete<ForecastRule>(
    `/mandants/${mandantId}/services/${serviceId}/forecast-rule`,
  )
  return resp.data
}

export async function listPlannedItems(
  mandantId: string,
  serviceId?: string,
): Promise<PlannedItem[]> {
  const resp = await apiClient.get<PlannedItem[]>(
    `/mandants/${mandantId}/forecast/planned-items`,
    { params: serviceId ? { service_id: serviceId } : {} },
  )
  return resp.data
}

export async function createPlannedItem(
  mandantId: string,
  data: { service_id: string; period: string; amount: string; note?: string | null },
): Promise<PlannedItem> {
  const resp = await apiClient.post<PlannedItem>(
    `/mandants/${mandantId}/forecast/planned-items`,
    data,
  )
  return resp.data
}

export async function deletePlannedItem(mandantId: string, itemId: string): Promise<void> {
  await apiClient.delete(`/mandants/${mandantId}/forecast/planned-items/${itemId}`)
}

// ─── Plan-Ist-Snapshots ───────────────────────────────────────────────────────

export async function listSnapshots(mandantId: string): Promise<SnapshotSummary[]> {
  const resp = await apiClient.get<SnapshotSummary[]>(
    `/mandants/${mandantId}/forecast/snapshots`,
  )
  return resp.data
}

export async function getSnapshot(
  mandantId: string,
  snapshotId: string,
): Promise<SnapshotDetail> {
  const resp = await apiClient.get<SnapshotDetail>(
    `/mandants/${mandantId}/forecast/snapshots/${snapshotId}`,
  )
  return resp.data
}

export async function createSnapshot(
  mandantId: string,
  data: { label?: string | null; scenario?: Scenario },
): Promise<SnapshotDetail> {
  const resp = await apiClient.post<SnapshotDetail>(
    `/mandants/${mandantId}/forecast/snapshots`,
    data,
  )
  return resp.data
}

export async function deleteSnapshot(mandantId: string, snapshotId: string): Promise<void> {
  await apiClient.delete(`/mandants/${mandantId}/forecast/snapshots/${snapshotId}`)
}
