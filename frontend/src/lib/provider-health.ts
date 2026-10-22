import type { MarketSource } from './types';

export type ProviderHealth = Pick<
  MarketSource,
  'id' | 'name' | 'kind' | 'provider' | 'environment'
> & {
  available: boolean;
  default: boolean;
  status: 'demo' | 'unavailable' | 'retrying' | 'degraded' | 'stale' | 'healthy' | 'not_checked';
  data_status: 'synthetic' | 'not_observed' | 'fresh' | 'stale' | 'undated' | 'invalid';
  requests: number;
  successful_requests: number;
  failed_requests: number;
  read_retries: number;
  deferred: number;
  cache_hits: number;
  history_available: boolean;
  last_success_at: string | null;
  last_request_at: string | null;
  latency_ms: number | null;
  last_error: HealthError | null;
  errors: HealthError[];
  quote: { symbol: string; observed_at: string | null; received_at: string; valid: boolean } | null;
  retry_after: number;
  retry_at: string | null;
  queued: number;
  shared_queued: number;
  shared_busy: boolean;
};
export type HistoryRecording = {
  status: 'ready' | 'partial';
  dropped_observations: number;
  last_failure_at: string | null;
};
export type ProviderReadHistory = {
  source_id: string;
  as_of: string;
  start: string;
  hours: number;
  retention_days: number;
  totals: {
    requests: number;
    successes: number;
    failures: number;
    success_rate: number | null;
    mean_latency_ms: number | null;
    max_latency_ms: number | null;
    first_at: string | null;
    last_at: string | null;
  };
  series: {
    at: string;
    requests: number;
    successes: number;
    failures: number;
    mean_latency_ms: number | null;
  }[];
  recent_errors: HealthError[];
  recording: HistoryRecording;
};
export type HealthError = { at: string; kind: string; message: string };
export type ProviderHealthReport = {
  items: ProviderHealth[];
  as_of: string;
  started_at: string;
  in_flight: number;
  queued: number;
  history_recording: HistoryRecording;
  jobs: { candle_imports: number; fill_imports: number; funding_imports: number };
  policy: {
    min_interval_ms: number;
    max_inflight: number;
    max_queue_per_provider: number;
    interactive_first: boolean;
    max_read_attempts: number;
    scope: string;
    telemetry: string;
  };
};
export const healthLabels: Record<ProviderHealth['status'], string> = {
  demo: 'Offline demo',
  unavailable: 'Unavailable',
  retrying: 'Cooling down',
  degraded: 'Needs attention',
  stale: 'No recent read',
  healthy: 'Healthy',
  not_checked: 'Not checked',
};
