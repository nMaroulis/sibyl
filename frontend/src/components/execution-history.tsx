import { useState } from 'react';
import { Download } from 'lucide-react';
import { Badge, Empty, ErrorState, Loading, Panel, PanelTitle, useToast } from './ui';
import { ValueChart } from './charts';
import { useResource } from '../lib/hooks';
import { exportCSV, number, post, refresh } from '../lib/api';
import type { Point } from '../lib/types';

type ReportRow = {
  exchange_order_id?: string;
  id: string;
  created_at: string;
  mode: string;
  account: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  notional: number;
  notional_kind: string;
  quote: string;
  fee: number | null;
  status: string;
};
type Report = {
  items: ReportRow[];
  realized_paper_pnl: Record<string, number>;
  paper_pnl_curve: (Point & { quote: string })[];
  note: string;
  unmatched_sold_quantity: number;
};

/** Searchable execution records with explicitly scoped, matched-lot paper results. */
export function ExecutionHistory() {
  const report = useResource<Report>('/reports/trading');
  const [busy, setBusy] = useState('');
  const toast = useToast();
  const updateStatus = async (id: string) => {
    setBusy(id);
    try {
      await post(`/exchange-orders/${id}/refresh`);
      refresh();
      toast('Exchange status refreshed.');
    } catch (error) {
      toast((error as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState('all');
  const [side, setSide] = useState('all');
  const [status, setStatus] = useState('all');
  const [date, setDate] = useState('');
  const [quote, setQuote] = useState('USDT');
  const rows =
    report.data?.items.filter(
      (r) =>
        (mode === 'all' || r.mode === mode) &&
        (side === 'all' || r.side === side) &&
        (status === 'all' || r.status === status) &&
        (!date || r.created_at.slice(0, 10) >= date) &&
        `${r.symbol} ${r.account} ${r.id}`.toLowerCase().includes(query.toLowerCase()),
    ) ?? [];
  const statuses = [...new Set(report.data?.items.map((r) => r.status) ?? [])];
  const counts = statuses.map((s) => ({
    status: s,
    count: rows.filter((r) => r.status === s).length,
  }));
  const curve = report.data?.paper_pnl_curve.filter((p) => p.quote === quote) ?? [];
  return (
    <>
      <div className="report-summary-grid">
        <Panel>
          <PanelTitle
            title="Matched paper P&L"
            subtitle="All retained manual paper fills · FIFO, fees included"
          />
          <div className="workspace-controls">
            <label>
              Quote currency
              <select value={quote} onChange={(e) => setQuote(e.target.value)}>
                {[...new Set(['USDT', ...Object.keys(report.data?.realized_paper_pnl ?? {})])].map(
                  (q) => (
                    <option key={q}>{q}</option>
                  ),
                )}
              </select>
            </label>
            <strong className="report-total">
              {number(report.data?.realized_paper_pnl[quote] ?? 0, 6)} <small>{quote}</small>
            </strong>
          </div>
          <ValueChart data={curve} currency={false} height={160} />
          <p className="footnote padded">
            P&L uses the full retained ledger, independently of the table filters. Opening balances
            have no recorded cost basis. Unmatched sales are excluded.
          </p>
        </Panel>
        <Panel>
          <PanelTitle
            title="Record status"
            subtitle={`${rows.length} records match your filters`}
          />
          <div className="status-bars">
            {counts.length ? (
              counts.map((item) => (
                <div key={item.status}>
                  <span>{item.status}</span>
                  <i
                    style={{
                      width: `${Math.max(2, (item.count / Math.max(1, rows.length)) * 100)}%`,
                    }}
                  />
                  <strong>{item.count}</strong>
                </div>
              ))
            ) : (
              <p className="muted">Statuses appear after your first order.</p>
            )}
          </div>
          <p className="footnote padded">
            Exchange statuses are the last locally recorded observation. Refresh records reloads the
            list. Use Check exchange on submitted orders with an exchange ID to read their latest
            status.
          </p>
        </Panel>
      </div>
      <Panel className="full-panel">
        <PanelTitle
          title="Execution history"
          subtitle="Paper fills and reviewed exchange intents"
          action={
            <button
              className="button secondary tiny"
              disabled={!rows.length}
              onClick={() =>
                exportCSV('sibyl-trading-report.csv', [
                  [
                    'Time',
                    'Mode',
                    'Account',
                    'Market',
                    'Side',
                    'Quantity',
                    'Price',
                    'Notional',
                    'Notional basis',
                    'Quote',
                    'Fee',
                    'Status',
                    'ID',
                  ],
                  ...rows.map((r) => [
                    r.created_at,
                    r.mode,
                    r.account,
                    r.symbol,
                    r.side,
                    r.quantity,
                    r.price,
                    r.notional,
                    r.notional_kind,
                    r.quote,
                    r.fee ?? '',
                    r.status,
                    r.id,
                  ]),
                ])
              }
            >
              <Download size={13} /> Export filtered
            </button>
          }
        />
        <div className="workspace-controls">
          <label>
            Search
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Market, account, record ID…"
            />
          </label>
          <label>
            Mode
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="all">All modes</option>
              <option value="paper">Paper</option>
              <option value="exchange">Exchange</option>
            </select>
          </label>
          <label>
            Side
            <select value={side} onChange={(e) => setSide(e.target.value)}>
              <option value="all">All sides</option>
              <option value="buy">Buy</option>
              <option value="sell">Sell</option>
            </select>
          </label>
          <label>
            Status
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="all">All statuses</option>
              {statuses.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label>
            From date
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
        </div>
        {report.loading ? (
          <Loading />
        ) : report.error ? (
          <ErrorState message={report.error} retry={report.retry} />
        ) : rows.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Account</th>
                  <th>Market / side</th>
                  <th>Quantity</th>
                  <th>Price</th>
                  <th>Notional</th>
                  <th>Fee</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>
                      {new Date(r.created_at).toLocaleString()}
                      <small className="table-subline">{r.mode}</small>
                    </td>
                    <td>{r.account}</td>
                    <td>
                      {r.symbol}
                      <small className="table-subline">{r.side}</small>
                    </td>
                    <td>{number(r.quantity, 8)}</td>
                    <td>
                      {number(r.price, 8)} {r.quote}
                    </td>
                    <td>
                      {number(r.notional, 6)} {r.quote}
                      <small className="table-subline">{r.notional_kind}</small>
                    </td>
                    <td>{r.fee === null ? '—' : `${number(r.fee, 6)} ${r.quote}`}</td>
                    <td>
                      <Badge>{r.status}</Badge>
                      {r.mode === 'exchange' && r.exchange_order_id && (
                        <button
                          className="text-button table-subline"
                          disabled={!!busy}
                          onClick={() => updateStatus(r.id)}
                        >
                          {busy === r.id ? 'Checking…' : 'Check exchange'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No matching records">
            Your paper fills and reviewed exchange orders will appear here.
          </Empty>
        )}
        <p className="footnote padded">
          {report.data?.note} Strategy job fills are inspected separately in the Strategy studio
          console.
        </p>
      </Panel>
    </>
  );
}
