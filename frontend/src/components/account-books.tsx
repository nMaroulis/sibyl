import { useState } from 'react';
import type { FormEvent } from 'react';
import { Download, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { api, exportCSV, number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Connection } from '../lib/types';
import { ExpandableRows } from './expandable-rows';
import { AgentButton } from './agents';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from './ui';

type AssetRow = {
  account_id: string;
  environment: string;
  asset: string;
  quantity: number | null;
  known_open_cost: number | null;
  unknown_open_quantity: number | null;
  unknown_sold_quantity: number | null;
  matched_realized: number | null;
  net_modeled_realized: number | null;
  funding_fee_value: number | null;
  issues: string[];
};
type Opening = {
  id: string;
  account_id: string;
  asset: string;
  currency: string;
  quantity: string;
  total_cost: string | null;
  as_of: string;
  revision: number;
  note: string;
};
type Report = {
  currency: string;
  source: string;
  as_of: string;
  fill_count: number;
  funding_count: number;
  note: string;
  input_fingerprint: string;
  reports: {
    environment: string;
    items: AssetRow[];
    disposal_count: number;
    conversion_count: number;
    transfer_count: number;
    conversions: {
      event_id: string;
      asset: string;
      quantity: string;
      timestamp_ms: number;
      rate: string | null;
      status: string;
      path: unknown[];
    }[];
  }[];
  unapplied_openings: { id: string; asset: string; reason: string }[];
  unapplied_transfers: { id: string; reason: string }[];
};
const value = (input: number | null) => (input == null ? 'Unavailable' : number(input, 6));

/** Cross-pair books read retained evidence only; opening assertions never change exchange balances. */
export function AccountBooks({
  accountId,
  environment,
  accounts,
  active,
}: {
  accountId: string;
  environment: string;
  accounts: Connection[];
  active: boolean;
}) {
  const [currency, setCurrency] = useState('USDT');
  const [source, setSource] = useState('binance');
  const [editing, setEditing] = useState<Opening | boolean>(false);
  const initial = typeof editing === 'object' ? editing : undefined;
  const [saving, setSaving] = useState(false);
  const toast = useToast();
  const query = new URLSearchParams({ account_id: accountId, environment, currency, source });
  const state = useResource<Report>(`/account-books?${query}`, 0, active);
  const openings = useResource<{ items: Opening[] }>(
    `/account-books/openings?${new URLSearchParams({ account_id: accountId, currency })}`,
    0,
    active,
  );
  const catalog = useResource<{
    items: { source: string; source_label: string; environment: string }[];
  }>('/market-history/series', 0, active);
  const rows = state.data?.reports.flatMap((group) => group.items) ?? [];
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    try {
      const identity = initial?.account_id ?? String(form.get('account_id'));
      await post(`/account-books/openings/${identity}`, {
        asset: String(form.get('asset')).trim().toUpperCase(),
        currency,
        quantity: String(form.get('quantity')),
        total_cost: form.get('total_cost') ? String(form.get('total_cost')) : null,
        as_of: new Date(String(form.get('as_of'))).toISOString(),
        revision: initial?.revision ?? 0,
        note: String(form.get('note')),
      });
      toast('Opening asset saved. Exchange balances were not changed.');
      setEditing(false);
      refresh();
    } catch (error) {
      toast((error as Error).message, true);
    } finally {
      setSaving(false);
    }
  };
  const remove = async (opening: Opening) => {
    try {
      await api(`/account-books/openings/${opening.id}?revision=${opening.revision}`, {
        method: 'DELETE',
      });
      toast('Opening assertion removed; its audit is retained.');
      refresh();
    } catch (error) {
      toast((error as Error).message, true);
    }
  };
  const download = () =>
    exportCSV('sibyl-cross-pair-accounting.csv', [
      [
        'Account',
        'Environment',
        'Asset',
        'Reporting currency',
        'Retained units',
        'Known open cost',
        'Unknown open units',
        'Unknown disposed units',
        'Matched realized component',
        'Qualified modeled net',
        'Funding fee mark',
        'Issues',
      ],
      ...rows.map((row) => [
        row.account_id,
        row.environment,
        row.asset,
        currency,
        row.quantity ?? '',
        row.known_open_cost ?? '',
        row.unknown_open_quantity ?? '',
        row.unknown_sold_quantity ?? '',
        row.matched_realized ?? '',
        row.net_modeled_realized ?? '',
        row.funding_fee_value ?? '',
        row.issues.join(' '),
      ]),
    ]);
  const sources = [
    ...new Set(['binance', 'demo', ...(catalog.data?.items.map((row) => row.source) ?? [])]),
  ];
  return (
    <Panel className="full-panel performance-panel account-books-panel">
      <PanelTitle
        title="Across-pair accounting"
        subtitle="Account and asset FIFO · retained history"
        action={
          <div className="performance-actions">
            <AgentButton
              module="accountant"
              compact
              context={{
                account_books_view: true,
                account_books_currency: currency,
                performance_account_id: accountId,
                performance_environment: environment as '' | 'demo' | 'test' | 'production',
                market_source: source,
              }}
            >
              Explain these books
            </AgentButton>
            <button className="button secondary tiny" onClick={() => setEditing(true)}>
              <Plus size={13} />
              Opening asset
            </button>
            <button className="button secondary tiny" onClick={state.retry}>
              <RefreshCw size={13} />
              Recalculate
            </button>
            <button className="button secondary tiny" disabled={!rows.length} onClick={download}>
              <Download size={13} />
              CSV
            </button>
          </div>
        }
      />
      <div className="form-grid">
        <label>
          Reporting unit
          <select value={currency} onChange={(event) => setCurrency(event.target.value)}>
            {['USDT', 'USD', 'EUR', 'GBP', 'BTC', 'ETH'].map((unit) => (
              <option key={unit}>{unit}</option>
            ))}
          </select>
        </label>
        <label>
          Retained price feed
          <select value={source} onChange={(event) => setSource(event.target.value)}>
            {sources.map((id) => (
              <option key={id}>{id}</option>
            ))}
          </select>
          <small>
            Uses already retained closed candles. Import missing pairs in Market history.
          </small>
        </label>
      </div>
      {state.loading && <Loading />}
      {state.error && <ErrorState message={state.error} retry={state.retry} />}
      {state.data && (
        <>
          <details className="accounting-method">
            <summary>Method and coverage</summary>
            <p className="muted">{state.data.note}</p>
          </details>
          <div className="inline-badges">
            <Badge>{state.data.fill_count} dependency fills</Badge>
            <Badge>{state.data.funding_count} funding observations</Badge>
            <Badge>{currency} reporting unit</Badge>
          </div>
          {rows.length ? (
            <ExpandableRows total={rows.length} label="asset books">
              {(visible) => (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Asset / account</th>
                        <th>Retained units</th>
                        <th>Known open cost</th>
                        <th>Unknown basis units</th>
                        <th>Matched realized</th>
                        <th>Coverage</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.slice(0, visible).map((row) => (
                        <tr key={`${row.account_id}:${row.environment}:${row.asset}`}>
                          <td>
                            <strong>{row.asset}</strong>
                            <small className="muted">
                              {accounts.find((account) => account.id === row.account_id)?.label ??
                                row.account_id}{' '}
                              · {row.environment}
                            </small>
                          </td>
                          <td>{value(row.quantity)}</td>
                          <td>
                            {value(row.known_open_cost)} {currency}
                          </td>
                          <td>{value(row.unknown_open_quantity)}</td>
                          <td>
                            {value(row.matched_realized)} {currency}
                          </td>
                          <td>
                            {row.issues.length ? (
                              <details>
                                <summary>
                                  {row.issues.length} qualification
                                  {row.issues.length === 1 ? '' : 's'}
                                </summary>
                                {row.issues.map((issue) => (
                                  <p key={issue} className="muted">
                                    {issue}
                                  </p>
                                ))}
                              </details>
                            ) : (
                              <Badge>Retained components priced</Badge>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </ExpandableRows>
          ) : (
            <Empty title="No retained accounting inputs">
              Import account fills or funding, or add a reviewed opening asset. You can connect
              multiple exchange accounts; their books remain separate.
            </Empty>
          )}
          {state.data.unapplied_openings.length > 0 && (
            <details open>
              <summary>Opening assertions need review</summary>
              {state.data.unapplied_openings.map((row) => (
                <p key={row.id}>
                  {row.asset}: {row.reason}
                </p>
              ))}
            </details>
          )}
          {state.data.unapplied_transfers.length > 0 && (
            <details>
              <summary>{state.data.unapplied_transfers.length} transfer links/groups need review</summary>
              {state.data.unapplied_transfers.map((row) => (
                <p key={row.id}>{row.reason}</p>
              ))}
            </details>
          )}
          <details>
            <summary>Historical conversion evidence</summary>
            {state.data.reports.map((group) => (
              <div key={group.environment}>
                <h4>
                  {group.environment} · {group.conversion_count} conversions
                </h4>
                <p className="muted">
                  Newest 500 retained evidence rows per environment are displayed; all inputs
                  contribute to the calculation.
                </p>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Event date</th>
                        <th>Asset</th>
                        <th>Native quantity</th>
                        <th>Rate in {currency}</th>
                        <th>Evidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.conversions.map((row, index) => (
                        <tr key={`${row.event_id}:${row.asset}:${index}`}>
                          <td>{new Date(row.timestamp_ms).toLocaleString()}</td>
                          <td>{row.asset}</td>
                          <td>{row.quantity}</td>
                          <td>{row.rate ?? 'Unavailable'}</td>
                          <td>
                            <details>
                              <summary>{row.status}</summary>
                              <pre>{JSON.stringify(row.path, null, 2)}</pre>
                            </details>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </details>
        </>
      )}
      {openings.data?.items.length ? (
        <details>
          <summary>Opening asset assertions · {openings.data.items.length}</summary>
          {openings.data.items.map((row) => (
            <div className="performance-actions" key={row.id}>
              <span>
                {row.asset} · {row.quantity} units · {row.total_cost ?? 'unknown'} {row.currency}{' '}
                basis · {new Date(row.as_of).toLocaleString()}
              </span>
              <button
                className="button secondary tiny"
                onClick={() => setEditing(row)}
                aria-label={`Edit ${row.asset} opening`}
              >
                <Pencil size={13} />
              </button>
              <button
                className="button secondary tiny"
                onClick={() => remove(row)}
                aria-label={`Remove ${row.asset} opening`}
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </details>
      ) : null}
      {editing && (
        <Modal title="Opening asset inventory" onClose={() => setEditing(false)}>
          <form className="form-grid" onSubmit={save}>
            <p className="muted">
              Enter inventory acquired before retained trading history. Costs are explicit
              assertions in {currency}; this does not deposit funds or edit exchange records.
            </p>
            <label>
              Account
              <select
                name="account_id"
                defaultValue={initial?.account_id ?? accountId}
                disabled={!!initial}
                required
              >
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Asset
              <input
                name="asset"
                placeholder="BTC"
                pattern="[A-Z0-9][A-Z0-9.]{0,19}"
                defaultValue={initial?.asset}
                readOnly={!!initial}
                required
              />
            </label>
            <label>
              Quantity
              <input
                name="quantity"
                type="number"
                min="0"
                step="any"
                defaultValue={initial?.quantity}
                required
              />
            </label>
            <label>
              Total acquisition cost in {currency}
              <input
                name="total_cost"
                defaultValue={initial?.total_cost ?? ''}
                type="number"
                min="0"
                step="any"
                placeholder="Leave empty if unknown"
              />
            </label>
            <label>
              Held as of
              <input
                name="as_of"
                type="datetime-local"
                defaultValue={
                  initial
                    ? new Date(
                        new Date(initial.as_of).getTime() -
                          new Date(initial.as_of).getTimezoneOffset() * 60000,
                      )
                        .toISOString()
                        .slice(0, 16)
                    : undefined
                }
                required
              />
            </label>
            <label>
              Evidence note
              <input
                name="note"
                minLength={3}
                maxLength={1000}
                defaultValue={initial?.note}
                required
              />
            </label>
            <button className="button" type="submit" disabled={saving}>
              {saving ? 'Saving…' : 'Save opening assertion'}
            </button>
          </form>
        </Modal>
      )}
    </Panel>
  );
}
