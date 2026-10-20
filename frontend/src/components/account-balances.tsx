import { ExchangeMark } from './exchange-mark';
import { useState } from 'react';
import { Download } from 'lucide-react';
import { Badge, DataNote, Empty, ErrorState, Loading, Panel, PanelTitle } from './ui';
import { useResource } from '../lib/hooks';
import { exportCSV, number } from '../lib/api';
import type { Source } from '../lib/types';

type Balance = {
  asset: string;
  total: number;
  free: number | null;
  used: number | null;
  price: number | null;
  value: number | null;
};
type Account = {
  id: string;
  name: string;
  exchange: string;
  sandbox: boolean;
  status: string;
  total: number;
  unpriced: number;
  holdings: Balance[];
};
type Accounts = Source & { accounts: Account[]; quote_rates: Record<string, number>; note: string };
export function AccountBalances() {
  const result = useResource<Accounts>('/portfolio/accounts', 60000);
  const [account, setAccount] = useState('all');
  const [quote, setQuote] = useState('USDT');
  const [query, setQuery] = useState('');
  const accounts =
    result.data?.accounts.filter((item) => account === 'all' || item.id === account) ?? [];
  const rate = result.data?.quote_rates[quote];
  const rows = accounts.flatMap((a) =>
    a.holdings
      .filter((h) => h.asset.includes(query.toUpperCase()))
      .map((h) => ({ ...h, account: a.name, accountId: a.id })),
  );
  const value = (v: number | null) =>
    v === null || !rate ? '—' : number(v / rate, quote === 'BTC' || quote === 'ETH' ? 6 : 2);
  return (
    <Panel className="full-panel">
      <PanelTitle
        title="Account balances"
        subtitle="Available, reserved, and total spot quantities"
        action={
          <button
            className="button secondary tiny"
            disabled={!rows.length}
            onClick={() =>
              exportCSV('sibyl-account-balances.csv', [
                ['Account', 'Asset', 'Free', 'Reserved', 'Total', `Value (${quote})`],
                ...rows.map((r) => [
                  r.account,
                  r.asset,
                  r.free ?? '',
                  r.used ?? '',
                  r.total,
                  r.value !== null && rate ? r.value / rate : '',
                ]),
              ])
            }
          >
            <Download size={13} /> Export
          </button>
        }
      />
      <div className="workspace-controls">
        <label>
          Account
          <select value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="all">All accounts</option>
            {result.data?.accounts.map((a) => (
              <option value={a.id} key={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Value in
          <select value={quote} onChange={(e) => setQuote(e.target.value)}>
            {Object.keys(result.data?.quote_rates ?? { USDT: 1 }).map((q) => (
              <option key={q}>{q}</option>
            ))}
          </select>
        </label>
        <label>
          Filter assets
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="BTC…" />
        </label>
      </div>
      {result.loading ? (
        <Loading />
      ) : result.error ? (
        <ErrorState message={result.error} retry={result.retry} />
      ) : (
        <>
          <div className="account-summary">
            {accounts.map((a) => (
              <div key={a.id}>
                <strong className="account-brand">
                  <ExchangeMark exchange={a.exchange} size={20} />
                  {a.name}
                </strong>
                <span>
                  {value(a.total)} {quote}
                </span>
                <Badge
                  tone={
                    a.exchange === 'demo'
                      ? 'demo'
                      : a.status === 'error'
                        ? 'rose'
                        : a.sandbox
                          ? 'purple'
                          : 'neutral'
                  }
                >
                  {a.exchange === 'demo' ? 'Demo' : a.status}
                  {a.sandbox ? ' · Sandbox · test funds' : ''}
                </Badge>
                {a.unpriced > 0 && <small>{a.unpriced} unpriced assets</small>}
              </div>
            ))}
          </div>
          {rows.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Account</th>
                    <th>Asset</th>
                    <th>Available</th>
                    <th>Reserved</th>
                    <th>Total</th>
                    <th>Value · {quote}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={`${r.accountId}:${r.asset}`}>
                      <td>{r.account}</td>
                      <td>
                        <strong>{r.asset}</strong>
                      </td>
                      <td>{r.free === null ? '—' : number(r.free, 8)}</td>
                      <td>{r.used === null ? '—' : number(r.used, 8)}</td>
                      <td>{number(r.total, 8)}</td>
                      <td>{value(r.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="No balances to display">
              Connect an account or choose another asset filter.
            </Empty>
          )}
          <p className="footnote padded">{result.data?.note}</p>
          <div className="chart-footnote">
            <DataNote source={result.data?.source} />
            <span>{result.data?.as_of && new Date(result.data.as_of).toLocaleString()}</span>
          </div>
        </>
      )}
    </Panel>
  );
}
