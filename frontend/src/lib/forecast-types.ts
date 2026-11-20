export type ForecastDataset = {
  id: string;
  digest: string;
  label: string;
  source: string;
  source_label: string;
  environment: string;
  symbol: string;
  timeframe: string;
  count: number;
  start: string;
  end: string;
  created_at: string;
};
export type ForecastModel = {
  id: string;
  series_id: string;
  version: number;
  label: string;
  created_at: string;
  symbol: string;
  source: string;
  environment: string;
  dataset: ForecastDataset;
  fingerprint: string;
  engine: string;
  app_version: string;
  parent_id: string | null;
  archived?: boolean;
  archive_revision?: number;
  imported_from?: {
    verified: false;
    claimed_source: string;
    method: string;
    recorded_fit_matches_local: boolean;
  };
  parameters: {
    family?: 'ridge' | 'mlp' | 'huber' | 'arima';
    arima_p?: number;
    arima_q?: number;
    arima_season?: 7;
    difference?: number;
    context_candles?: number;
    huber_delta?: number;
    lags?: number;
    alpha?: number;
    max_horizon: number;
    feature_set?: 'returns' | 'returns_context';
  };
};
export type ForecastMetrics = { mae: number; rmse: number; mape_pct: number };
export type ForecastEvaluation = {
  horizon: number;
  samples: number;
  model: ForecastMetrics;
  naive: ForecastMetrics;
  drift: ForecastMetrics;
  mae_skill_vs_naive_pct: number | null;
  coverage_pct: number;
  mean_interval_width_pct: number;
  overlapping_targets: boolean;
};
export type ForecastChartPoint = {
  timestamp: string;
  actual?: number;
  predicted?: number;
  value?: number;
  lower?: number;
  upper?: number;
  naive?: number;
  drift?: number;
};
export type ForecastDetail = {
  model: ForecastModel;
  nominal_coverage: number;
  notes: string[];
  partitions: Record<string, { start: string; end: string; candles: number }>;
  training?: (NeuralTraining | HuberTraining)[];
  arima_training?: ARIMATraining;
  evaluation: ForecastEvaluation[];
  test_trace: ForecastChartPoint[];
  trace_horizon: number;
  outputs: Omit<ForecastOutput, 'points' | 'observations'>[];
};
export type ForecastOutput = {
  id: string;
  created_at: string;
  model_id: string;
  model_version: number;
  symbol: string;
  source: string;
  environment: string;
  origin: string;
  input_kind: string;
  last_price: number;
  input_fingerprint: string;
  stale: boolean;
  age_days: number;
  shift: { outside_training_range: number; features: number; note: string };
  note: string;
  nominal_coverage: number;
  horizon: number;
  points: ForecastChartPoint[];
  observations: { candles: { timestamp: string; close: number }[] };
};

export type RollingRequest = {
  horizon: number;
  folds: number;
  test_days: number;
  calibration_days: number;
  window: 'expanding' | 'rolling';
  training_days?: number | null;
};
export type RollingAggregate = {
  samples: number;
  model: ForecastMetrics;
  naive: ForecastMetrics;
  drift: ForecastMetrics;
  mae_skill_vs_naive_pct: number | null;
  coverage_pct: number;
  mean_interval_width_pct: number;
  positive_skill_folds: number;
};
export type RollingHeader = {
  id: string;
  model_id: string;
  model_version: number;
  model_fingerprint: string;
  label: string;
  symbol: string;
  source: string;
  environment: string;
  dataset: ForecastDataset;
  created_at: string;
  request: RollingRequest;
  result_fingerprint: string;
  fingerprint: string;
  aggregate: RollingAggregate;
};
export type RollingReport = Omit<RollingHeader, 'aggregate'> & {
  result: {
    engine: string;
    nominal_coverage: number;
    aggregate: RollingAggregate;
    folds: {
      index: number;
      partitions: Record<
        string,
        { start: string; end: string; candles: number; start_index: number; end_index: number }
      >;
      evaluation: ForecastEvaluation & { trace: ForecastChartPoint[] };
    }[];
    notes: string[];
  };
};

export type NeuralTraining = {
  family?: 'mlp';
  horizon: number;
  epochs: number;
  hidden_units: number;
  optimizer: string;
  initial_loss: number;
  final_loss: number;
};
export type HuberTraining = {
  family: 'huber';
  horizon: number;
  delta: number;
  steps: number;
  max_steps: number;
  converged: boolean;
  initial_loss: number;
  final_loss: number;
  target_center: number;
  target_scale: number;
  residual_threshold: number;
  downweighted_samples: number;
  training_samples: number;
  effective_weight_sum: number;
  minimum_weight: number;
};

export type ARIMATraining = {
  library: string;
  library_version: string;
  estimator: string;
  converged: boolean;
  iterations: number;
  max_iterations: number;
  training_returns: number;
  aic: number;
  bic: number;
  log_likelihood: number;
  warning_categories: string[];
  parameter_values: Record<string, number>;
  scale_units: string;
};
