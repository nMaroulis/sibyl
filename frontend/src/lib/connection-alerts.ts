import type { HistoryRecording, ProviderHealth } from './provider-health';
import type { Inbox } from '../components/notifications';

/** A passive watch on transport evidence, independent of price/strategy rules. */
export type ConnectionSource = Pick<
  ProviderHealth,
  'id' | 'name' | 'kind' | 'provider' | 'environment' | 'available'
>;
export type ConnectionAlert = {
  id: string;
  source: string;
  source_info: ConnectionSource;
  label: string;
  failures_required: number;
  successes_required: number;
  notify_recovery: boolean;
  status: 'armed' | 'paused' | 'archived';
  revision: number;
  notifications: number;
  armed_at: string;
  last_checked_at: string | null;
  last_event_at: string | null;
  tracking_note: string | null;
  operations: Record<
    string,
    {
      failures: number;
      successes: number;
      incident: boolean;
      at: string | null;
      error_kind: string | null;
    }
  >;
};
export type ConnectionRulesData = {
  items: ConnectionAlert[];
  sources: ConnectionSource[];
  total: number;
  count: number;
  limit: number;
  recording: HistoryRecording;
};
export type ConnectionAlertExample = { rules: ConnectionRulesData; inbox: Inbox };
export const operationLabel = (operation: string) =>
  ({
    fetch_ticker: 'Price quotes',
    fetch_ohlcv: 'Candles',
    fetch_candle_page: 'Candle imports',
    fetch_order_book: 'Order book',
    fetch_balance: 'Account balances',
    fetch_open_orders: 'Open orders',
    fetch_my_trades: 'Recent fills',
    fetch_trade_page: 'Fill imports',
    fetch_funding_page: 'Funding imports',
    fetch_order: 'Order details',
    fetch_order_lookup_page: 'Order lookup',
    fetch_order_fill_page: 'Order fills',
    fetch_account_order_page: 'Account order history',
    load_markets: 'Market catalog',
    read: 'Provider reads',
  })[operation] || operation;
export const connectionSettingsURL = (source: string) =>
  `/settings?tab=${source.startsWith('connection:') ? 'exchanges' : 'market'}`;
