import type { Backtest, StrategyParams } from './types';
import type { Dataset } from './market-history';

export type ValidationOptions = {
  strategies: Record<string, { key: string; values: number[] }[]>;
  max_candidates: number;
  max_axes: number;
  max_values: number;
  max_folds: number;
  min_test_bars: number;
  max_work_bars: number;
};
export type ValidationMetrics = {
  return_pct: number;
  sharpe: number;
  max_drawdown: number;
  trades: number;
  fees: number;
};
export type ValidationSummary = {
  id: string;
  created_at: string;
  source: string;
  environment: string;
  dataset: Dataset;
  candidate_count: number;
  method: string;
  engine_revision: string;
  request: {
    dataset_id: string;
    parameters: StrategyParams;
    grid: Record<string, number[]>;
    folds: number;
    initial_train_pct: number;
    objective: 'return_pct' | 'sharpe' | 'max_drawdown';
    min_train_trades: number;
  };
  summary: {
    mean_return_pct: number;
    median_return_pct: number;
    worst_return_pct: number;
    mean_fixed_return_pct: number;
    mean_benchmark_pct: number;
    profitable_windows: number;
    test_bars: number;
    trades: number;
  };
};
export type ValidationReport = ValidationSummary & {
  rerun_of?: string;
  assumptions: string[];
  common_warmup: number;
  processed_bars: number;
  folds: {
    index: number;
    train: { start: string; end: string; bars: number; scored_bars: number };
    test: { start: string; end: string; bars: number };
    selected: {
      candidate_id: number;
      overrides: Record<string, number>;
      parameters: StrategyParams;
    };
    training_ranking: (ValidationMetrics & {
      candidate_id: number;
      overrides: Record<string, number>;
      eligible: boolean;
    })[];
    out_of_sample: Omit<Backtest, 'id' | 'source'>;
    fixed_parameters: ValidationMetrics;
  }[];
};
