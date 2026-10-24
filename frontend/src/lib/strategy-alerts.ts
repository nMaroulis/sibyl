/** Per-run local subscriptions; these controls never change the strategy itself. */
export type StrategyAlertGroup = 'attention' | 'lifecycle';
export type StrategyAlertRun = {
  strategy: string;
  name: string;
  symbol: string;
  timeframe: string;
  mode: 'paper' | 'exchange';
  source: string;
  source_label: string;
  environment: string;
  account: string | null;
};
export type StrategyAlert = {
  id: string;
  job_id: string;
  run: StrategyAlertRun;
  label: string;
  events: StrategyAlertGroup[];
  status: 'armed' | 'paused' | 'archived';
  revision: number;
  cursor: number;
  notifications: number;
  created_at: string;
  armed_at: string;
  last_checked_at: string | null;
  last_event_at: string | null;
  last_notified_at: string | null;
};
export type StrategyAlertRules = {
  items: StrategyAlert[];
  count: number;
  total: number;
  offset: number;
  page_size: number;
  limit: number;
  groups: { id: StrategyAlertGroup; name: string; description: string }[];
};
export const strategyActionLabel = (action: string) =>
  ({
    ERROR: 'Evaluation error',
    PAUSE: 'Run paused',
    RECOVERED: 'Observations recovered',
    START: 'Run started',
    RESUME: 'Run resumed',
    STOP: 'Run stopped',
    STOP_CANCEL: 'Stop & cancel requested',
    COMPLETED: 'Run completed',
  })[action] || action;
