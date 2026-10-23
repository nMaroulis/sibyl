/** JSON contracts shared by the typed API client and dashboard screens. */
export type Source = {
  source: string;
  source_label?: string;
  as_of?: string;
  environment?: string;
  capabilities?: { candles: boolean; order_book: boolean };
};
export type System = {
  version: string;
  mode: 'demo' | 'live';
  execution: 'paper';
  allow_live_trading: boolean;
  allow_strategy_execution: boolean;
  llm_provider: string;
  llm_model: string;
  agents: number;
  market_exchange: string;
  market_source?: MarketSource;
  accounts: AccountSelection;
};
export type Point = { timestamp: string; value: number };
export type Asset = {
  asset: string;
  name: string;
  price: number;
  change: number | null;
  color: string;
  sparkline: number[];
};
export type ValuationQuote = {
  asset: string;
  currency: string;
  price: number | null;
  change: number | null;
  status: 'identity' | 'fresh' | 'undated' | 'stale' | 'unavailable' | 'limited';
  reason: string | null;
  path: string[];
  observed_at: string | null;
  route: {
    symbol: string;
    from_asset: string;
    to_asset: string;
    inverse: boolean;
    rate: number;
    observed_at: string | null;
    received_at: string | null;
  }[];
};
export type Holding = Asset &
  ValuationQuote & {
    quantity: number;
    value: number;
    allocation: number;
    accounts: { account_id: string; account: string; exchange: string; quantity: number }[];
  };
export type MarketAsset = Omit<Asset, 'price'> & {
  price: number | null;
  symbol: string;
  quote: string;
  volume: number | null;
  status: 'fresh' | 'stale' | 'undated' | 'unavailable' | 'loading';
  error?: string;
  observed_at: string | null;
};
export type Portfolio = Source & {
  mode: AccountSelection['mode'];
  total: number;
  active: boolean;
  scope: string;
  complete: boolean;
  coverage: { priced: number; total: number };
  cash: number;
  currency: string;
  change: number | null;
  change_value: number | null;
  holdings: Holding[];
  history: Point[];
  history_note: string;
  history_kind: 'illustrative' | 'observed';
  valuation_note: string;
  warnings: string[];
  unpriced: (ValuationQuote & { name: string; quantity: number })[];
  venues: {
    id: string;
    name: string;
    status: string;
    assets: number;
    exchange: string;
    total: number | null;
    unpriced: number;
    sandbox: boolean;
  }[];
};
export type Candle = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  sma: number | null;
  upper: number | null;
  lower: number | null;
  ema_fast: number;
  ema_slow: number;
  rsi: number | null;
};
export type Timeframe = '1m' | '5m' | '15m' | '30m' | '1h' | '4h' | '12h' | '1d' | '1w';
export type MarketStatistics = {
  price: number;
  sample: {
    loaded: number;
    observations: number;
    return_observations: number;
    start: string;
    end: string;
    interval_seconds: number;
    gap_count: number;
    missing_intervals: number;
    stale: boolean;
    age_seconds: number;
    warnings: string[];
  };
  assessment: {
    version: string;
    score: number | null;
    label: string;
    available_weight: number;
    reason: string | null;
    note: string;
    components: { id: string; label: string; weight: number; value: number | null; rule: string }[];
  };
  returns: Record<string, number | null>;
  trend: Record<string, number | null>;
  momentum: Record<string, number | null>;
  volatility: Record<string, number | null>;
  risk: Record<string, number | null>;
  volume: Record<string, number | null>;
  levels: Record<string, number | null>;
};
export type Analysis = Source & {
  timeframe: Timeframe;
  symbol: string;
  candles: Candle[];
  price: number;
  statistics: MarketStatistics;
  rsi: number | null;
  trend: string;
  volatility: number | null;
  high: number;
  low: number;
  period_return: number;
};
export type Connection = {
  id: string;
  exchange: string;
  label: string;
  sandbox: boolean;
  created_at: string;
  active: boolean;
};
export type AccountSelection = {
  mode: 'none' | 'demo' | 'live' | 'test';
  active_ids: string[];
  accounts: Connection[];
  signature: string;
  demo_available: boolean;
  scopes: {
    id: string;
    label: string;
    kind: 'combined' | 'exchange' | 'account';
    count: number;
    exchange?: string;
    sandbox?: boolean;
  }[];
};
export type Strategy = {
  id: string;
  name: string;
  tag: string;
  description: string;
  risk: string;
};
export type StrategyParams = {
  strategy: string;
  symbol: string;
  capital: number;
  candles: number;
  fee_bps: number;
  slippage_bps: number;
  window: number;
  timeframe?: Timeframe;
  fast_period?: number;
  slow_period?: number;
  rsi_period?: number;
  rsi_lower?: number | null;
  rsi_upper?: number | null;
  band_std?: number;
  volume_multiplier?: number;
  macd_fast_period?: number;
  macd_slow_period?: number;
  macd_signal_period?: number;
  adx_period?: number;
  atr_period?: number;
  cmf_period?: number | null;
  tsi_short_period?: number;
  tsi_long_period?: number;
  stop_loss_pct?: number | null;
  take_profit_pct?: number | null;
  max_trades?: number | null;
};
export type Performance = {
  sharpe: number;
  max_drawdown: number;
  observations: number;
  sortino: number | null;
  calmar: number | null;
  profit_factor: number | null;
  average_win: number | null;
  average_loss: number | null;
  best_trade: number | null;
  worst_trade: number | null;
  drawdown_curve: number[];
};
export type Fill = {
  reason?: string;
  side: string;
  timestamp: string;
  price: number;
  quantity: number;
  fee?: number;
};
export type Backtest = Source & {
  price_series?: {
    timestamp: string;
    close: number;
    open: number;
    high: number;
    low: number;
    volume: number;
  }[];
  benchmark_curve?: Point[];
  engine_revision?: string;
  round_trips?: {
    id: number;
    entry_time: string;
    exit_time: string;
    entry_price: number;
    exit_price: number;
    quantity: number;
    pnl: number;
    return_pct: number;
    holding_seconds: number;
    reason: string;
  }[];
  summary?: {
    net_profit: number;
    profit_factor: number | null;
    expectancy: number | null;
    exposure_pct: number;
    turnover: number;
    annualized_return_pct: number | null;
    average_holding_seconds: number | null;
    evaluated_bars: number;
    warmup_bars: number;
    start: string;
    end: string;
  };
  dataset?: import('./market-history').Dataset;
  engine_version?: string;
  id: string;
  strategy: string;
  symbol: string;
  metrics?: Performance;
  timeframe?: Timeframe;
  initial_capital: number;
  final_equity: number;
  return_pct: number;
  benchmark_pct: number;
  sharpe: number;
  max_drawdown: number;
  trades: number;
  win_rate: number;
  fees: number;
  curve: Point[];
  fills: Fill[];
  execution: string;
  parameters: StrategyParams;
};
export type Job = Source & {
  mode?: 'paper' | 'exchange';
  account?: string;
  exchange?: string;
  connection_id?: string;
  environment?: string;
  execution_state?: string;
  accounting_incomplete?: boolean;
  dust_position?: boolean;
  risk_locked?: boolean;
  fee_assets?: Record<string, number>;
  unvalued_fees?: Record<string, number>;
  native_fill_count?: number;
  risk?: Record<string, number | null>;
  stop_cancellation?: { review_id: string; requested_at: string };
  close_position?: {
    review_id: string;
    intent_id: string;
    state: string;
    message: string;
    checked_at: string;
    native_status?: string;
    filled?: number;
    requested?: number;
    remaining_position?: number;
  };
  orders?: {
    id: string;
    status: string;
    strategy_abandoned?: boolean;
    strategy_action?: string;
    strategy_close_review_id?: string;
    strategy_expires_at?: string;
    cancel_state?: string;
    cancel_message?: string;
    strategy_cancellation?: {
      state: string;
      message: string;
      reason: string;
      checked_at: string;
      outcome?: string;
      terminal_checks?: number;
      next_check?: number;
    };
    exchange_order_id?: string;
    client_order_id?: string;
    filled?: number;
    remaining?: number;
    message?: string;
    request: { side: string; quantity: number; symbol: string };
  }[];
  created_at: string;
  monitoring_since?: string;
  updated_at?: string;
  observed_at?: string;
  reference_price?: number;
  statistics_complete?: boolean;
  entry_cost?: number;
  realized_pnl?: number;
  fees_paid?: number;
  completed_returns?: number[];
  round_trips?: number;
  metrics?: Performance;
  curve?: Point[];
  id: string;
  parameters: StrategyParams;
  status: string;
  cash: number;
  quantity: number;
  equity: number;
  last_candle: string | null;
  fills: Fill[];
  error: string | null;
  checked_at?: string;
};
export type OrderInput = {
  symbol: string;
  side: 'buy' | 'sell';
  quantity: number;
  idempotency_key: string;
};
export type Order = {
  id: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  notional: number;
  fee: number;
  status: string;
  mode: string;
  created_at: string;
};
export type Preview = Omit<Order, 'id' | 'status' | 'created_at'> & Source & { total: number };
export type Agent = {
  id: string;
  name: string;
  tagline: string;
  description: string;
  engine: string;
  tool: string;
  tools: string[];
  url: string;
  mode: string;
  provider: string;
};
export type AgentReply = {
  context?: AgentContext;
  id: string;
  module: string;
  session_id: string;
  question: string;
  answer: string;
  engine: string;
  mode: string;
  provider: string;
  tool: string;
  evidence: unknown;
  observations?: { tool: string; arguments: Record<string, unknown>; evidence: unknown }[];
  created_at: string;
};
export type Forecast = Source & {
  symbol: string;
  model: string;
  trained: boolean;
  horizon: number;
  points: (Point & { lower: number; upper: number })[];
  last_price: number;
  daily_volatility: number;
  note: string;
};
export type Article = {
  body?: string;
  sentiment: { label: string; compound: number; pos: number; neg: number; neu: number };
  id: string;
  title: string;
  category: string;
  summary: string;
  publisher: string;
  published_at: string | null;
  url: string | null;
  source_id: string;
  assets: string[];
  collected_at: string;
  first_seen_at: string;
};
export type NewsDistribution = {
  count: number;
  compound: number | null;
  positive: number;
  neutral: number;
  negative: number;
};
export type NewsFeed = {
  source: string;
  mode: 'demo' | 'live';
  default_mode: 'demo' | 'live';
  items: Article[];
  total: number;
  archive_count: number;
  has_more: boolean;
  limit: number;
  offset: number;
  note: string;
  sentiment: NewsDistribution & {
    model: string;
    note: string;
    undated: number;
    timeline: (NewsDistribution & { date: string })[];
    assets: (NewsDistribution & { asset: string })[];
  };
  facets: { assets: string[]; publishers: { id: string; name: string }[] };
  sources: {
    method: 'rss' | 'web' | 'api';
    id: string;
    name: string;
    website: string;
    status: string;
    last_attempt: string | null;
    last_success: string | null;
    error: string | null;
    articles: number;
  }[];
  collection: {
    refresh_seconds: number;
    retention_days: number;
    max_articles: number;
    in_progress: boolean;
  };
};
export type FearGreedPoint = { value: number; classification: string; timestamp: string };
export type FearGreedIndex = {
  source: string;
  source_url: string;
  mode: 'demo' | 'live';
  status: string;
  current: FearGreedPoint | null;
  history: FearGreedPoint[];
  comparisons: {
    yesterday?: FearGreedPoint | null;
    last_week?: FearGreedPoint | null;
    last_month?: FearGreedPoint | null;
  };
  fetched_at: string | null;
  error: string | null;
  note: string;
};
export type NewsSettings = {
  mode: 'auto' | 'demo' | 'live';
  resolved_mode: 'demo' | 'live';
  sources: string[];
  cryptoslate_method: 'rss' | 'web';
  has_api_key: boolean;
  query: string;
  catalog: {
    id: string;
    name: string;
    kind: string;
    website: string | null;
    description: string;
    methods?: string[];
  }[];
};
export type MarketSource = {
  id: string;
  name: string;
  kind: 'demo' | 'exchange' | 'connection' | 'api';
  provider: string;
  environment: string;
  requires_key: boolean;
  has_api_key: boolean;
  available: boolean;
  candles: boolean;
  order_book: boolean;
  description?: string;
  website?: string | null;
  note?: string;
};
export type MarketSettings = {
  active: MarketSource;
  catalog: MarketSource[];
  account_mode: 'demo' | 'live';
  restart_required: boolean;
};
export type Knowledge = {
  term: string;
  category: string;
  text: string;
  url: string;
};
export type Block = {
  height: number;
  id: string;
  timestamp: number;
  tx_count: number;
  size: number;
};
export type Stock = Source & {
  profile?: {
    sector?: string;
    industry?: string;
    country?: string;
    description?: string;
    website?: string;
    market_cap?: number;
    trailing_pe?: number;
    dividend_yield?: number;
  };
  profile_warning?: string;
  statistics: {
    period_return: number;
    high: number;
    low: number;
    volatility: number;
    max_drawdown: number;
    observations: number;
  };
  symbol: string;
  name: string;
  price: number;
  currency: string;
  history: Point[];
};
export type Run = {
  id: string;
  kind: string;
  created_at: string;
  payload: AgentReply | Backtest;
};

/** Page selections accepted by the corresponding read-only agent tool. */
export type AgentContext = {
  backtest_id?: string;
  validation_id?: string;
  portfolio_scope?: string;
  performance_view?: boolean;
  performance_account_id?: string;
  performance_environment?: '' | 'demo' | 'test' | 'production';
  performance_example?: boolean;
  performance_transfer_example?: boolean;
  performance_fee_example?: boolean;
  funding_view?: boolean;
  funding_account_id?: string;
  funding_asset?: string;
  funding_kind?: '' | 'deposit' | 'withdrawal' | 'transfer';
  funding_status?: '' | 'pending' | 'completed' | 'failed' | 'cancelled' | 'restricted' | 'unknown';
  funding_environment?: '' | 'demo' | 'test' | 'production';
  funding_example?: boolean;
  transfer_view?: boolean;
  transfer_example?: boolean;
  market_source?: string;
  crypto_id?: string;
  job_id?: string;
  timeframe?: Timeframe;
  limit?: number;
  symbol?: string;
  equity_symbol?: string;
  horizon?: number;
  parameters?: StrategyParams;
  article_id?: string;
  news_mode?: 'demo' | 'live';
  news_publisher?: string;
  news_asset?: string;
  news_sentiment?: '' | 'positive' | 'neutral' | 'negative';
  news_days?: number;
  query?: string;
};
export type ModuleId =
  | 'oracle'
  | 'accountant'
  | 'analyst'
  | 'broker'
  | 'chronos'
  | 'reporter'
  | 'technician'
  | 'wiki'
  | 'explorer'
  | 'stocks';

export type StrategyEvent = {
  id: number;
  timestamp: string;
  kind: string;
  action: string;
  signal?: string;
  reason: string;
  candle_timestamp?: string;
  candle_close?: number;
  reference_price?: number;
  fill_price?: number | null;
  slippage?: number | null;
  slippage_bps?: number | null;
  quantity?: number;
  fee?: number;
  cash: number;
  position: number;
  equity: number;
};
export type StrategyObservation = {
  timestamp: string;
  price: number;
  equity: number;
  cash: number;
  position: number;
};
export type StrategyMonitorData = {
  job: Job;
  observations: StrategyObservation[];
  markers: StrategyEvent[];
  legacy_fills: Fill[];
  event_count: number;
  worker_interval: number;
  as_of: string;
  retention: { observations: number; events: string };
};
export type StrategyEventPage = {
  items: StrategyEvent[];
  has_more: boolean;
  next_before: number | null;
  matching_count: number;
};

export type ModelProvider = {
  id: string;
  name: string;
  kind: 'api' | 'local' | 'tools';
  description: string;
  models: string[];
  base_url: string;
  requires_key: boolean;
  installed: boolean;
  extra: string;
  docs_url: string;
};
export type ModelProfile = {
  model: string;
  base_url: string;
  has_api_key: boolean;
  key_source: 'saved' | 'environment' | 'none';
  saved: boolean;
};
export type ModelWorkspace = {
  active_provider: string;
  active_model: string;
  source: 'workspace' | 'environment';
  profiles: Record<string, ModelProfile>;
  providers: ModelProvider[];
};

export type CryptoAsset = {
  id: string;
  symbol: string;
  name: string;
  category: string;
  wikipedia: string;
  color: string;
};
export type CryptoCatalog = {
  items: CryptoAsset[];
  selection_note: string;
  data_note: string;
};
export type CryptoProfile = Source & {
  asset: CryptoAsset;
  status: 'ready' | 'partial' | 'unavailable';
  profile: {
    description: string;
    launch_date: string | null;
    proof_type: string;
    organization: string;
    development_status: string;
    open_source: boolean | null;
    tags: string[];
    team: { name: string; position: string }[];
    links: { label: string; url: string }[];
  } | null;
  history: {
    title: string;
    introduction: string;
    sections: { title: string; text: string }[];
    url: string;
    revision: number | null;
    license_url: string;
    article_note: string | null;
  } | null;
  market: {
    price: number | null;
    market_cap: number | null;
    volume_24h: number | null;
    rank: number | null;
    circulating_supply: number | null;
    total_supply: number | null;
    max_supply: number | null;
    percent_change_24h: number | null;
    percent_change_7d: number | null;
    percent_change_30d: number | null;
    percent_change_1y: number | null;
    ath_price: number | null;
    ath_date: string | null;
    percent_from_price_ath: number | null;
    updated_at: string | null;
    first_data_at: string | null;
    currency: string;
  } | null;
  sources: {
    part: 'profile' | 'history' | 'market';
    source: string;
    url: string;
    cached: boolean;
    stale: boolean;
    error: string | null;
    as_of: string | null;
  }[];
};

/** Backend-owned exchange configuration; capabilities describe the installed SDK. */
export type ExchangeSupportGroup = {
  id: string;
  label: string;
  summary: {
    status: 'supported' | 'partial' | 'unsupported' | 'simulated';
    implemented: number;
    total: number;
  };
  features: {
    id: string;
    label: string;
    status: 'available' | 'simulated' | 'pending' | 'unavailable';
    detail: string;
  }[];
};
export type ExchangeProvider = {
  id: string;
  name: string;
  note: string;
  account: string;
  credentials_required: boolean;
  simulated: boolean;
  test_environment: boolean;
  ccxt_id: string;
  setup_url: string;
  passphrase: boolean;
  uid: boolean;
  sandbox: boolean;
  market_orders: boolean;
  limit_orders: boolean;
  cancel_orders: boolean;
  verification: string;
  support: ExchangeSupportGroup[];
  capabilities: Record<string, 'native' | 'emulated' | 'unavailable' | 'simulated'>;
  timeframes: string[];
};
export type ExchangeCatalog = {
  key_storage: string;
  items: ExchangeProvider[];
  ccxt_version: string;
  not_configured: string[];
  demo: ExchangeProvider;
};
