/** Shared strategy policy and dated evidence; unrelated account wealth is outside its scope. */
export type LimitPolicy = {
  enabled: boolean;
  source: string;
  max_allocated: number | null;
  max_exposure: number | null;
  max_daily_loss: number | null;
};

export type PortfolioLimitState = {
  environment: 'production' | 'test';
  revision: number;
  policy: LimitPolicy;
  locked: boolean;
  tripped_day: string | null;
  fresh: boolean;
  error: string | null;
  sample: null | {
    as_of: string;
    day: string;
    period_started_at: string;
    allocated: number;
    position: number;
    pending_buys: number;
    exposure: number;
    daily_pnl: number;
    daily_loss: number;
    source: { source_label: string };
    rates: Record<string, { price: number; path: string[]; observed_at: string | null }>;
    runs: {
      id: string;
      account: string;
      symbol: string;
      status: string;
      allocated: number;
      position: number;
      pending_buys: number;
      pnl: number;
    }[];
  };
  history: {
    id: number;
    action: string;
    timestamp: string;
    reason: string;
    paused_job_ids: string[];
  }[];
};

export type PortfolioLimits = {
  currency: string;
  policies: PortfolioLimitState[];
  save_confirmation: string;
  release_confirmation: string;
  scope: string;
};
