// API types mirroring the backend's pydantic schemas.

export type RunStatus = 'RUNNING' | 'COMPLETED' | 'DIVERGED' | 'KILLED' | 'LOST'
export type Health = 'HEALTHY' | 'AT_RISK' | 'DOOMED'
export type Directive = 'NONE' | 'KILL'

export interface Forecast {
  id: number
  run_id: number
  as_of_progress: number
  p_hit_target: number
  p_diverge: number
  p_plateau: number
  eta_quantiles: Record<string, number>
  components: Record<string, unknown>
  calibrated: boolean
  created_at: string
}

export interface Run {
  id: number
  name: string
  tags: string[]
  framework: string | null
  status: RunStatus
  health: Health | null
  target_metric: string
  target_value: number
  direction: 'min' | 'max'
  budget_steps: number
  budget_wallclock_s: number
  gpu_type: string
  gpu_count: number
  gpu_hourly_usd: number
  burn_usd_per_hour: number
  started_at: string
  ended_at: string | null
  last_heartbeat_at: string | null
  last_checkpoint_at: string | null
  current_step: number
  progress: number
  directive: Directive
  directive_issued_at: string | null
  directive_grace_s: number | null
  kill_acked_at: string | null
  final_value: number | null
  created_at: string
  latest_forecast: Forecast | null
}

export interface Page<T> {
  items: T[]
  next_cursor: string | null
}

export interface MetricPoint {
  step: number
  ts: string
  value: number
}

export interface MetricSeries {
  run_id: number
  name: string
  total_points: number
  points: MetricPoint[]
}

export interface Policy {
  id: number
  name: string
  enabled: boolean
  definition: PolicyDefinition
  version: number
  created_at: string
  updated_at: string
}

export interface PolicyDefinition {
  name: string
  scope: { tags: string[] }
  when: {
    signal: string
    op: '<' | '<=' | '>' | '>='
    value: number
    after_progress: number
    sustained_evals: number
  }
  action: {
    type: 'warn' | 'kill'
    grace_seconds: number
    min_checkpoint_age_seconds: number
    notify: boolean
  }
}

export interface DryRunFire {
  run_id: number
  run_name: string
  at_progress: number
  signal_value: number
  est_gross_usd: number
  est_expected_usd: number
}

export interface DryRunResult {
  would_have_fired: DryRunFire[]
  est_gross_usd: number
  est_expected_usd: number
  runs_scanned: number
  assumptions: string[]
}

export type EventKind = 'WARN' | 'KILL_ISSUED' | 'KILL_ACKED' | 'OVERRIDDEN'

export interface PolicyEvent {
  id: number
  policy_id: number | null
  policy_name: string | null
  run_id: number
  run_name: string
  kind: EventKind
  snapshot: Record<string, unknown>
  gross_recovered_usd: number | null
  expected_recovered_usd: number | null
  created_at: string
}

export interface LedgerRow {
  run_id: number
  run_name: string
  killed_at: string
  gpu_type: string
  gpu_count: number
  gpu_hourly_usd: number
  gross_recovered_usd: number
  expected_recovered_usd: number | null
}

export interface Ledger {
  window_days: number
  gross_recovered_usd: number
  expected_recovered_usd: number
  kills: number
  rows: LedgerRow[]
}

export interface ReliabilityBin {
  bin_low: number
  bin_high: number
  count: number
  mean_forecast: number
  observed_rate: number
}

export interface CalibrationFitPoint {
  fitted_at: string
  brier_after: number | null
  n_samples: number
}

export interface OutcomeCalibration {
  outcome: 'hit_target' | 'diverge'
  n_samples: number
  calibrated: boolean
  brier_raw: number | null
  brier_calibrated: number | null
  fitted_at: string | null
  bins: ReliabilityBin[]
  history: CalibrationFitPoint[]
}

export interface Calibration {
  min_samples: number
  outcomes: OutcomeCalibration[]
}

export interface ApiKeyInfo {
  id: number
  name: string
  key_prefix: string
  scopes: string[]
  revoked_at: string | null
  created_at: string
}

export interface ApiKeyCreated extends ApiKeyInfo {
  key: string
}

export interface StreamEvent {
  type: 'run.updated' | 'forecast.updated' | 'policy.fired' | 'ledger.updated'
  data: Record<string, unknown>
}

export interface CopilotStatus {
  enabled: boolean
  model: string | null
}
