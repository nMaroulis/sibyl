import type { Inbox } from '../components/notifications';
import type { Connection, MarketSource } from './types';
import { number } from './api';

export type RiskMetric = 'value_floor' | 'concentration' | 'drawdown';
export type RiskAccount = Omit<Connection, 'active'>;
export type RiskSource = {
  source: string;
  source_label: string;
  source_kind: MarketSource['kind'];
  provider: string;
  environment: string;
};
export type RiskObservation = {
  total: number;
  currency: string;
  metric_value: number | null;
  peak: number | null;
  peak_at: string | null;
  as_of: string;
};
export type RiskRule = {
  id: string;
  account_ids: string[];
  accounts: RiskAccount[];
  environment: string;
  source: string;
  source_info: RiskSource;
  metric: RiskMetric;
  asset: string;
  threshold: number;
  reset_threshold: number;
  cooldown_seconds: number;
  notify_recovery: boolean;
  label: string;
  status: 'armed' | 'paused' | 'archived';
  revision: number;
  cycle: number;
  notifications: number;
  armed_at: string;
  last_checked_at: string | null;
  last_sample_id: number | null;
  last_observation: RiskObservation | null;
  error: string | null;
  evaluation_note: string | null;
  in_breach: boolean;
  incident_notified: boolean;
  cooldown_until: number;
  next_check: number;
};
export type RiskRulesData = {
  items: RiskRule[];
  count: number;
  total: number;
  limit: number;
  check_interval_seconds: number;
};
export type RiskEvidenceData = {
  rule: RiskRule;
  sample:
    | (RiskObservation & {
        id: number;
        revision: number;
        policy: {
          metric: RiskMetric;
          asset: string;
          threshold: number;
          reset_threshold: number;
          label: string;
        };
        complete: boolean;
        accounts: RiskAccount[];
        environment: string;
        source_info: RiskSource;
        started_at: string;
        balance_reads: { account_id: string; received_at: string }[];
        holdings: {
          asset: string;
          value: number;
          allocation: number;
          path: string[];
          observed_at: string | null;
        }[];
      })
    | null;
  samples: (Pick<RiskObservation, 'as_of' | 'total' | 'metric_value' | 'peak'> & { id: number })[];
  revision: number;
  selected_sample_id: number | null;
  retention_days: number;
  sample_limit: number;
  note: string;
};
export type RiskExample = { rules: RiskRulesData; inbox: Inbox; evidence: RiskEvidenceData };
export const riskLabel = (metric: RiskMetric, asset = '') =>
  ({
    value_floor: 'Account value floor',
    concentration: `${asset || 'Asset'} concentration`,
    drawdown: 'Observed-value drawdown',
  })[metric];
export const riskValue = (value: number | null | undefined, metric: RiskMetric) =>
  value == null ? '—' : `${number(value, 2)}${metric === 'value_floor' ? ' USDT' : '%'}`;
export const riskURL = (id: string, sampleId?: number) =>
  `/alerts?tab=risk&rule_id=${encodeURIComponent(id)}${sampleId ? `&sample_id=${sampleId}` : ''}`;
export const fundsEnvironment = (account: Pick<Connection, 'exchange' | 'sandbox'>) =>
  account.exchange === 'demo' ? 'demo' : account.sandbox ? 'test' : 'production';
