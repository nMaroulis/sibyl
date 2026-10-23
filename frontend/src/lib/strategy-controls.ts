/** Persisted admission state, not an assertion that venue orders are canceled. */
export type StrategyControl = {
  halted: boolean;
  revision: number;
  changed_at: string | null;
  reason: string;
  server_enabled: boolean;
  exchange_runs: Record<string, number>;
  release_confirmation: string;
  history_limit: number;
  history_retention: number;
  history: {
    revision: number;
    action: 'halt' | 'release';
    changed_at: string;
    reason: string;
    paused_job_ids: string[];
    paused_count: number;
  }[];
};
