import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ArrowDownUp, History, ListOrdered, RefreshCw, ShieldCheck } from 'lucide-react';
import {
  Badge,
  Change,
  DataNote,
  ErrorState,
  Loading,
  PageTitle,
  Panel,
  PanelTitle,
  useToast,
} from '../components/ui';
import { ValueChart } from '../components/charts';
import { money, number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { AccountSelection, Analysis, Order, OrderInput, Preview } from '../lib/types';
import { AccountContext, AccountSetup, useAccounts } from '../components/account-selection';
import { AgentButton } from '../components/agents';
import { OrderBook } from '../components/orderbook';
import { ComingSoon } from '../components/coming-soon';
import { ExchangeExecution } from '../components/ExchangeExecution';
import { AccountHistory } from '../components/account-history';
import { ExecutionHistory } from '../components/execution-history';
import { SectionPanel, SectionTabs } from '../components/section-tabs';

const sections = [
  { id: 'trade', label: 'Trade', icon: ArrowDownUp },
  { id: 'executions', label: 'Executions', icon: ListOrdered },
  { id: 'history', label: 'Account history', icon: History },
];

/** One trading workspace; tabs retain forms and filters while hidden polling pauses. */
export function Trading() {
  const accounts = useAccounts();
  if (accounts.loading) return <Loading />;
  if (accounts.error || !accounts.data)
    return (
      <ErrorState
        message={accounts.error || 'Account selection unavailable.'}
        retry={accounts.retry}
      />
    );
  if (!accounts.data.active_ids.length)
    return (
      <>
        <PageTitle title="Trade" description="Choose your exchange accounts to get started." />
        <AccountSetup selection={accounts.data} page="trading workspace" />
      </>
    );
  return <TradingActive key={accounts.data.signature} selection={accounts.data} />;
}

function TradingActive({ selection }: { selection: AccountSelection }) {
  const [params, setParams] = useSearchParams();
  const requested = params.get('tab') ?? 'trade';
  const tab = sections.some((item) => item.id === requested) ? requested : 'trade';
  const asset = params.get('asset') || 'BTC';
  const [opened, setOpened] = useState([tab]);
  useEffect(() => {
    setOpened((old) => (old.includes(tab) ? old : [...old, tab]));
  }, [tab]);
  const select = (key: string, value: string) =>
    setParams((old) => {
      const next = new URLSearchParams(old);
      next.set(key, value);
      return next;
    });
  return (
    <>
      <PageTitle
        title="Trade"
        description="Place spot orders, review executions, and explore account history."
        action={
          tab === 'trade' ? (
            <AgentButton module="broker" context={{ symbol: `${asset}/USDT` }} />
          ) : (
            <button className="button secondary" onClick={refresh}>
              <RefreshCw size={14} /> Refresh records
            </button>
          )
        }
      />
      <AccountContext selection={selection} />
      <SectionTabs
        id="trade"
        label="Trade sections"
        items={sections}
        value={tab}
        onChange={(value) => select('tab', value)}
      />
      <SectionPanel id="trade" value={tab}>
        <div hidden={tab !== 'trade'}>
          {selection.mode !== 'demo' ? (
            <>
              <ExchangeExecution />
              <OrderBook symbol={`${asset}/USDT`} active={tab === 'trade'} />
              <ComingSoon module="trade" />
            </>
          ) : (
            (tab === 'trade' || opened.includes('trade')) && (
              <TradeWorkspace
                asset={asset}
                setAsset={(value) => select('asset', value)}
                active={tab === 'trade'}
              />
            )
          )}
        </div>
        <div hidden={tab !== 'executions'}>
          {(tab === 'executions' || opened.includes('executions')) && <ExecutionHistory />}
        </div>
        <div hidden={tab !== 'history'}>
          {(tab === 'history' || opened.includes('history')) && (
            <AccountHistory active={tab === 'history'} />
          )}
        </div>
      </SectionPanel>
    </>
  );
}

/** Order entry stays mounted after its first visit so tab changes preserve drafts. */
function TradeWorkspace({
  asset,
  setAsset,
  active,
}: {
  asset: string;
  setAsset: (asset: string) => void;
  active: boolean;
}) {
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [quantity, setQuantity] = useState('0.01');
  const [preview, setPreview] = useState<Preview>();
  const [input, setInput] = useState<OrderInput>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const ledger = useResource<{ balances: Record<string, number> }>('/paper/balances');
  const analysis = useResource<Analysis>(
    `/markets/analysis?symbol=${encodeURIComponent(`${asset}/USDT`)}&limit=90`,
  );
  const toast = useToast();
  const reset = () => {
    setPreview(undefined);
    setInput(undefined);
    setError('');
  };
  useEffect(() => {
    setPreview(undefined);
    setInput(undefined);
    setError('');
  }, [asset]);
  const review = async () => {
    setBusy(true);
    setError('');
    const body: OrderInput = {
      symbol: `${asset}/USDT`,
      side,
      quantity: Number(quantity),
      idempotency_key: crypto.randomUUID(),
    };
    try {
      const result = await post<Preview>('/orders/preview', body);
      setPreview(result);
      setInput(body);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const execute = async () => {
    if (!input) return;
    setBusy(true);
    setError('');
    try {
      await post<Order>('/orders', input);
      reset();
      refresh();
      toast('Paper order filled. Your virtual balances have been updated.');
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <div className="trading-grid">
        <Panel>
          <PanelTitle
            title={`${asset} / USDT`}
            subtitle="Daily closing prices"
            action={
              <select
                aria-label="Chart market"
                value={asset}
                onChange={(event) => {
                  setAsset(event.target.value);
                  reset();
                }}
              >
                {['BTC', 'ETH', 'SOL', 'LINK', 'AVAX', 'DOT'].map((symbol) => (
                  <option key={symbol}>{symbol}</option>
                ))}
              </select>
            }
          />
          {analysis.data ? (
            <>
              <div className="market-chart-heading">
                <strong>{money(analysis.data.price)}</strong>
                <Change value={analysis.data.period_return} />
              </div>
              <ValueChart
                data={analysis.data.candles.map((candle) => ({
                  timestamp: candle.timestamp,
                  value: candle.close,
                }))}
                height={330}
              />
              <div className="chart-footnote">
                <DataNote source={analysis.data.source} />
                <span>Sample return shown above</span>
              </div>
            </>
          ) : analysis.error ? (
            <ErrorState message={analysis.error} retry={analysis.retry} />
          ) : (
            <div className="chart-empty">Loading market history…</div>
          )}
        </Panel>
        <Panel>
          <PanelTitle title="Your next move" subtitle="Virtual funds. Real workflow." />
          <form
            className="form trade-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (preview) execute();
              else review();
            }}
          >
            <div className="segmented trade-side">
              <button
                type="button"
                className={side === 'buy' ? 'selected' : ''}
                onClick={() => {
                  setSide('buy');
                  reset();
                }}
              >
                Buy
              </button>
              <button
                type="button"
                className={side === 'sell' ? 'selected sell' : ''}
                onClick={() => {
                  setSide('sell');
                  reset();
                }}
              >
                Sell
              </button>
            </div>
            <label>
              Market
              <select
                value={asset}
                disabled={busy}
                onChange={(event) => {
                  setAsset(event.target.value);
                  reset();
                }}
              >
                {['BTC', 'ETH', 'SOL', 'LINK', 'AVAX', 'DOT'].map((symbol) => (
                  <option key={symbol} value={symbol}>
                    {symbol} / USDT
                  </option>
                ))}
              </select>
            </label>
            <div className="order-type">
              <span>Order type</span>
              <Badge>Market · paper</Badge>
            </div>
            <label>
              Quantity · {asset}
              <input
                required
                type="number"
                step="any"
                min="0.00000001"
                max="1000000"
                value={quantity}
                disabled={busy}
                onChange={(event) => {
                  setQuantity(event.target.value);
                  reset();
                }}
              />
            </label>
            <div className="available-balance">
              Paper balance{' '}
              <strong>
                {number(ledger.data?.balances[side === 'buy' ? 'USDT' : asset] ?? 0, 6)}{' '}
                {side === 'buy' ? 'USDT' : asset}
              </strong>
            </div>
            {preview && (
              <div className="order-preview">
                <div>
                  <span>Reference price</span>
                  <strong>{money(preview.price)}</strong>
                </div>
                <div>
                  <span>Notional</span>
                  <strong>{money(preview.notional)}</strong>
                </div>
                <div>
                  <span>Paper fee · 0.1%</span>
                  <strong>{money(preview.fee)}</strong>
                </div>
                <div className="preview-total">
                  <span>{side === 'buy' ? 'Estimated debit' : 'Estimated credit'}</span>
                  <strong>{money(preview.total)}</strong>
                </div>
                <small>Reviewed at a reference price. Execution uses a fresh quote.</small>
              </div>
            )}
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <button
              disabled={busy}
              className={`button full-width ${side === 'sell' ? 'rose-button' : 'primary'}`}
              type="submit"
            >
              <ArrowDownUp size={15} />
              {busy ? 'Working…' : preview ? `Confirm paper ${side}` : 'Review paper order'}
            </button>
            {preview && (
              <button type="button" className="text-button" onClick={reset}>
                Edit order
              </button>
            )}
            <p className="footnote">
              <ShieldCheck size={12} />
              This order updates your virtual ledger. Connected exchange balances are separate.
            </p>
          </form>
        </Panel>
      </div>
      <OrderBook symbol={`${asset}/USDT`} active={active} />
      <ComingSoon module="trade" />
    </>
  );
}
