import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowDownUp, Download, ShieldCheck } from 'lucide-react';
import {
  Badge,
  Change,
  DataNote,
  Empty,
  ErrorState,
  PageTitle,
  Panel,
  PanelTitle,
  useToast,
} from '../components/ui';
import { ValueChart } from '../components/charts';
import { exportCSV, money, number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Analysis, Order, OrderInput, Preview } from '../lib/types';
import { AgentButton } from '../components/agents';
import { OrderBook } from '../components/orderbook';
import { ComingSoon } from '../components/coming-soon';
import { ExchangeExecution } from '../components/ExchangeExecution';

export function Trading() {
  const [params] = useSearchParams();
  const [asset, setAsset] = useState(params.get('asset') || 'BTC');
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [quantity, setQuantity] = useState('0.01');
  const [preview, setPreview] = useState<Preview>();
  const [input, setInput] = useState<OrderInput>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const orders = useResource<Order[]>('/orders');
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
      <PageTitle
        eyebrow="ROOM TO EXPERIMENT"
        title="Spot trading"
        description="Practice your next move with a separate paper wallet."
        action={
          <>
            <Badge tone="lime">
              <ShieldCheck size={12} />
              Paper execution only
            </Badge>
            <AgentButton module="broker" context={{ symbol: `${asset}/USDT` }} />
          </>
        }
      />
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
      <Panel className="full-panel">
        <PanelTitle
          title="Order history"
          subtitle="Every paper fill, saved locally"
          action={
            <button
              className="button secondary tiny"
              disabled={!orders.data?.length}
              onClick={() =>
                exportCSV('sibyl-paper-orders.csv', [
                  ['Time', 'Symbol', 'Side', 'Quantity', 'Price', 'Fee'],
                  ...(orders.data ?? []).map((order) => [
                    order.created_at,
                    order.symbol,
                    order.side,
                    order.quantity,
                    order.price,
                    order.fee,
                  ]),
                ])
              }
            >
              <Download size={13} />
              Export
            </button>
          }
        />
        {orders.error ? (
          <ErrorState message={orders.error} retry={orders.retry} />
        ) : orders.data?.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Market</th>
                  <th>Side</th>
                  <th>Quantity</th>
                  <th>Fill price</th>
                  <th>Fee</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {orders.data.map((order) => (
                  <tr key={order.id}>
                    <td>{new Date(order.created_at).toLocaleString()}</td>
                    <td>{order.symbol}</td>
                    <td>
                      <Badge tone={order.side === 'buy' ? 'lime' : 'rose'}>{order.side}</Badge>
                    </td>
                    <td>{number(order.quantity, 6)}</td>
                    <td>{money(order.price)}</td>
                    <td>{money(order.fee)}</td>
                    <td>
                      <Badge>Filled · paper</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="Your first move is still ahead">
            Review a paper order to begin. Fills and fees will be recorded here.
          </Empty>
        )}
      </Panel>
      <OrderBook symbol={`${asset}/USDT`} />
      <ExchangeExecution />
      <div className="quiet-callout horizontal-callout">
        <div>
          <h3>Your activity, in one place.</h3>
          <p>
            Filter paper fills and exchange intents, export records, and inspect matched paper P&L.
          </p>
        </div>
        <Link className="button secondary" to="/reports">
          Open trading report →
        </Link>
      </div>
      <ComingSoon module="trade" />
    </>
  );
}
