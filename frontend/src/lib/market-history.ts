import type { ChartCandle } from '../components/candlesticks';
import type { Timeframe } from './types';

export const frameSeconds: Record<Timeframe, number> = {
  '1m': 60,
  '5m': 300,
  '15m': 900,
  '30m': 1800,
  '1h': 3600,
  '4h': 14400,
  '12h': 43200,
  '1d': 86400,
  '1w': 604800,
};
export type Dataset = {
  id: string;
  digest: string;
  label: string;
  source: string;
  source_label: string;
  environment: string;
  symbol: string;
  timeframe: Timeframe;
  count: number;
  start: string;
  end: string;
  created_at: string;
  immutable: boolean;
};
export type DatasetList = { items: Dataset[]; total: number; offset: number; limit: number };
export type Series = {
  id: string;
  source: string;
  source_label: string;
  environment: string;
  symbol: string;
  timeframe: Timeframe;
  retained: number;
  oldest: string | null;
  newest: string | null;
};
export type Coverage = {
  expected: number;
  stored: number;
  missing: number;
  complete: boolean;
  gaps: { start: string; end: string; candles: number }[];
  gap_ranges: number;
  gaps_truncated: boolean;
};
export type CandleHistory = {
  source: string;
  source_label: string;
  environment: string;
  available: boolean;
  series: Series | null;
  revision: number;
  retained: number;
  oldest: string | null;
  newest: string | null;
  start: string | null;
  end: string | null;
  coverage: Coverage | null;
  candles: ChartCandle[];
  preview_truncated: boolean;
  range_truncated: boolean;
  latest_closed_end: string;
  backfill: { supported: boolean; page_intervals: number; note: string };
  job: null | {
    id: string;
    status: string;
    pages: number;
    observations: number;
    cursor: number;
    start_ms: number;
    end_ms: number;
    start: string;
    end: string;
    error: string | null;
    next_attempt: number;
    checked_at: string | null;
  };
};
