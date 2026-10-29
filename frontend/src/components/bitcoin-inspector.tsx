import { useRef, useState } from 'react';
import {
  ArrowDownLeft,
  ArrowUpRight,
  Download,
  ExternalLink,
  RefreshCw,
  Search,
} from 'lucide-react';
import { AgentButton } from './agents';
import { Badge, ErrorState, Loading, Panel, PanelTitle } from './ui';
import { number, post } from '../lib/api';
import { useResource } from '../lib/hooks';
import type {
  BitcoinAttribution,
  BitcoinCapabilities,
  BitcoinHistory,
  BitcoinReport,
  BitcoinStatus,
} from '../lib/bitcoin-types';

/** Format exact satoshis without rounding high-turnover address counters through a float. */
function btc(value: number | string | null) {
  if (value == null) return 'Unavailable';
  const satoshis = BigInt(value),
    absolute = satoshis < 0n ? -satoshis : satoshis;
  return `${satoshis < 0n ? '−' : ''}${(absolute / 100_000_000n).toLocaleString()}.${String(absolute % 100_000_000n).padStart(8, '0')} BTC`;
}

function Confirmation({ status }: { status: BitcoinStatus }) {
  return (
    <Badge tone={status.confirmed ? 'green' : 'amber'}>
      {status.confirmed
        ? status.confirmations == null
          ? 'Included · count unavailable'
          : `${number(status.confirmations, 0)} confirmations`
        : 'Pending · unconfirmed'}
    </Badge>
  );
}

function download(value: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = 'sibyl-bitcoin-observation.json';
  link.click();
  URL.revokeObjectURL(url);
}

/** User-initiated public research, with independent Demo examples and no saved browser identifiers. */
export function BitcoinInspector() {
  const capabilities = useResource<BitcoinCapabilities>('/bitcoin');
  const [draft, setDraft] = useState('');
  const [report, setReport] = useState<BitcoinReport>();
  const [confirmed, setConfirmed] = useState<BitcoinHistory>();
  const [confirmedPages, setConfirmedPages] = useState<(BitcoinHistory & BitcoinAttribution)[]>([]);
  const [pending, setPending] = useState<BitcoinHistory & BitcoinAttribution>();
  const [showPending, setShowPending] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const active = useRef(false);

  const inspect = async (value: string, demo = false, inputOffset = 0, outputOffset = 0) => {
    if (active.current || !value.trim()) return;
    active.current = true;
    setBusy('inspect');
    setError('');
    setReport(undefined);
    setConfirmed(undefined);
    setConfirmedPages([]);
    setPending(undefined);
    setShowPending(false);
    try {
      const result = await post<BitcoinReport>('/bitcoin/inspect', {
        kind: /^[a-f0-9]{64}$/i.test(value.trim()) ? 'transaction' : 'address',
        value: value.trim(),
        demo,
        input_offset: inputOffset,
        output_offset: outputOffset,
      });
      setReport(result);
      if (result.kind === 'address') {
        setConfirmed(result.history);
        const { source, network, observed_at, tip_height, warnings, note } = result;
        setConfirmedPages([
          { ...result.history, source, network, observed_at, tip_height, warnings, note },
        ]);
      }
      if (!demo) setDraft(value.trim());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      active.current = false;
      setBusy('');
    }
  };

  const history = async (unconfirmed: boolean) => {
    if (active.current || report?.kind !== 'address') return;
    active.current = true;
    setBusy('history');
    setError('');
    try {
      const page = await post<BitcoinHistory & BitcoinAttribution>('/bitcoin/history', {
        address: report.address.address,
        pending: unconfirmed,
        demo: report.source === 'demo',
        ...(!unconfirmed && confirmed?.next_cursor ? { cursor: confirmed.next_cursor } : {}),
      });
      if (unconfirmed) {
        setPending(page);
        setShowPending(true);
      } else {
        const previous = confirmed?.items ?? [];
        if (page.items.some((row) => previous.some((p) => p.txid === row.txid)))
          throw new Error(
            'Address history changed between pages. Refresh the lookup before continuing.',
          );
        setConfirmed({ ...page, items: [...previous, ...page.items] });
        setConfirmedPages((previousPages) => [...previousPages, page]);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      active.current = false;
      setBusy('');
    }
  };
  const simulated = report?.source === 'demo';
  const reference =
    report?.kind === 'transaction' ? report.transaction.txid : report?.address.address;
  const context =
    report?.kind === 'transaction'
      ? { bitcoin_txid: report.transaction.txid, bitcoin_demo: simulated }
      : report?.kind === 'address'
        ? { bitcoin_address: report.address.address, bitcoin_demo: simulated }
        : {};
  const activity = showPending ? pending : confirmed;

  const addressLink = (value: string | null) =>
    value ? (
      <button
        className="bitcoin-reference text-button"
        title={value}
        disabled={!!busy || (simulated && value !== capabilities.data?.demo.address)}
        onClick={() => void inspect(value, simulated)}
      >
        {value}
      </button>
    ) : (
      <span className="muted">Non-address script</span>
    );

  return (
    <Panel className="bitcoin-inspector">
      <PanelTitle
        title="Transaction & address lookup"
        subtitle="Bitcoin mainnet · public on-chain observations"
        action={<AgentButton module="explorer" context={context} compact />}
      />
      <div className="bitcoin-content">
        <form
          className="bitcoin-search"
          onSubmit={(event) => {
            event.preventDefault();
            void inspect(draft);
          }}
        >
          <label htmlFor="bitcoin-reference">Transaction ID or Bitcoin address</label>
          <div>
            <Search size={16} />
            <input
              id="bitcoin-reference"
              autoComplete="off"
              spellCheck={false}
              maxLength={90}
              value={draft}
              placeholder="Paste a full transaction ID, 1…, 3… or bc1… address"
              onChange={(event) => setDraft(event.target.value)}
            />
            <button className="button primary" disabled={!!busy || !draft.trim()}>
              Inspect
            </button>
          </div>
        </form>
        <p className="bitcoin-source-note">
          Lookups are sent to{' '}
          <a href="https://mempool.space/" target="_blank" rel="noreferrer">
            mempool.space
          </a>
          . No API key or connected exchange is needed. Enter public references, never private keys
          or seed phrases.
        </p>
        {capabilities.data && (
          <p className="bitcoin-demo-links">
            Just exploring?{' '}
            <button
              className="text-button"
              disabled={!!busy}
              onClick={() => void inspect(capabilities.data!.demo.txid, true)}
            >
              Demo transaction
            </button>
            <span>·</span>
            <button
              className="text-button"
              disabled={!!busy}
              onClick={() => void inspect(capabilities.data!.demo.address, true)}
            >
              Demo address
            </button>
          </p>
        )}
        {capabilities.error && (
          <ErrorState message={capabilities.error} retry={capabilities.retry} />
        )}
        {busy === 'inspect' && <Loading />}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        {report && (
          <div className="bitcoin-result">
            <div className="bitcoin-result-toolbar">
              <Badge tone={simulated ? 'amber' : 'blue'}>
                {simulated ? 'Demo · synthetic observations' : 'Bitcoin mainnet'}
              </Badge>
              <span>
                Source: {report.source} · {new Date(report.observed_at).toLocaleString()}
              </span>
              <button
                className="text-button"
                disabled={!!busy}
                onClick={() => void inspect(reference!, simulated)}
              >
                <RefreshCw size={13} /> Refresh
              </button>
              <button
                className="text-button"
                onClick={() =>
                  download({
                    report,
                    confirmed_pages: confirmedPages,
                    pending_observation: pending,
                  })
                }
              >
                <Download size={13} /> Export observation
              </button>
              {report.url && (
                <a className="text-link" href={report.url} target="_blank" rel="noreferrer">
                  Public explorer <ExternalLink size={12} />
                </a>
              )}
            </div>
            <code className="bitcoin-result-id">{reference}</code>
            {report.warnings.map((warning) => (
              <p className="bitcoin-warning" key={warning}>
                {warning}
              </p>
            ))}
            {report.kind === 'transaction' ? (
              <>
                <div className="bitcoin-inclusion">
                  <Confirmation status={report.transaction.status} />
                  {report.transaction.status.block_height != null && (
                    <span>
                      Block #{number(report.transaction.status.block_height, 0)} ·{' '}
                      {new Date(report.transaction.status.block_time! * 1000).toLocaleString()}
                    </span>
                  )}
                  {report.transaction.coinbase && <Badge>Coinbase · newly issued coins</Badge>}
                </div>
                <div className="bitcoin-metrics">
                  <div>
                    <small>Transaction fee</small>
                    <strong>{number(report.transaction.fee_sats, 0)} sat</strong>
                    <span>{btc(report.transaction.fee_sats)}</span>
                  </div>
                  <div>
                    <small>Fee rate</small>
                    <strong>{number(report.transaction.fee_rate_sat_vb, 2)} sat/vB</strong>
                    <span>
                      {number(report.transaction.vsize, 0)} virtual bytes ·{' '}
                      {number(report.transaction.size, 0)} bytes
                    </span>
                  </div>
                  <div>
                    <small>Total outputs</small>
                    <strong>{btc(report.transaction.output_total_sats)}</strong>
                    <span>Includes change; not a payment or profit measure</span>
                  </div>
                </div>
                <div className="bitcoin-io-grid">
                  <section>
                    <h3>
                      <ArrowUpRight size={15} /> Inputs{' '}
                      <Badge>{report.transaction.input_count}</Badge>
                    </h3>
                    <p className="footnote">
                      Total: {btc(report.transaction.input_total_sats)}
                      {report.transaction.missing_prevouts ? ' · incomplete previous outputs' : ''}
                    </p>
                    {report.transaction.inputs.map((input) => (
                      <div className="bitcoin-io-row" key={input.index}>
                        <small>
                          #{input.index}
                          {input.coinbase ? ' · Coinbase input' : ''}
                        </small>
                        {input.previous_output ? (
                          <>
                            {addressLink(input.previous_output.address)}
                            <strong>{btc(input.previous_output.value_sats)}</strong>
                          </>
                        ) : (
                          <span className="muted">
                            {input.coinbase
                              ? 'Newly issued coins; no previous output'
                              : 'Previous output unavailable'}
                          </span>
                        )}
                        {input.txid && (
                          <button
                            className="text-button bitcoin-outpoint"
                            disabled={!!busy || simulated}
                            onClick={() => void inspect(input.txid!, simulated)}
                          >
                            Previous transaction · output #{input.vout}
                          </button>
                        )}
                      </div>
                    ))}
                    {report.transaction.next_input_offset != null && (
                      <button
                        className="text-button"
                        disabled={!!busy}
                        onClick={() =>
                          void inspect(
                            reference!,
                            simulated,
                            report.transaction.next_input_offset!,
                            report.transaction.output_offset,
                          )
                        }
                      >
                        Next inputs →
                      </button>
                    )}
                    {report.transaction.input_offset > 0 && (
                      <button
                        className="text-button"
                        disabled={!!busy}
                        onClick={() =>
                          void inspect(
                            reference!,
                            simulated,
                            Math.max(0, report.transaction.input_offset - 20),
                            report.transaction.output_offset,
                          )
                        }
                      >
                        ← Previous inputs
                      </button>
                    )}
                  </section>
                  <section>
                    <h3>
                      <ArrowDownLeft size={15} /> Outputs{' '}
                      <Badge>{report.transaction.output_count}</Badge>
                    </h3>
                    {report.transaction.outputs.map((output) => (
                      <div className="bitcoin-io-row" key={output.index}>
                        <small>
                          #{output.index} · {output.script_type}
                        </small>
                        {addressLink(output.address)}
                        <strong>{btc(output.value_sats)}</strong>
                      </div>
                    ))}
                    {report.transaction.next_output_offset != null && (
                      <button
                        className="text-button"
                        disabled={!!busy}
                        onClick={() =>
                          void inspect(
                            reference!,
                            simulated,
                            report.transaction.input_offset,
                            report.transaction.next_output_offset!,
                          )
                        }
                      >
                        Next outputs →
                      </button>
                    )}
                    {report.transaction.output_offset > 0 && (
                      <button
                        className="text-button"
                        disabled={!!busy}
                        onClick={() =>
                          void inspect(
                            reference!,
                            simulated,
                            report.transaction.input_offset,
                            Math.max(0, report.transaction.output_offset - 20),
                          )
                        }
                      >
                        ← Previous outputs
                      </button>
                    )}
                  </section>
                </div>
                <details className="bitcoin-details">
                  <summary>Technical details</summary>
                  <p>
                    Version {report.transaction.version} · locktime {report.transaction.locktime} ·
                    weight {number(report.transaction.weight, 0)} WU.
                  </p>
                  <p>
                    Input/output lists show at most twenty rows per page. Spending status of outputs
                    is not queried.
                  </p>
                </details>
              </>
            ) : (
              <>
                <div className="bitcoin-metrics">
                  <div>
                    <small>Confirmed address balance</small>
                    <strong>{btc(report.address.confirmed_balance_sats)}</strong>
                    <span>Indexed received outputs minus spent outputs</span>
                  </div>
                  <div>
                    <small>Pending change</small>
                    <strong>{btc(report.address.pending_delta_sats)}</strong>
                    <span>Projected: {btc(report.address.projected_balance_sats)}</span>
                  </div>
                  <div>
                    <small>Indexed transactions</small>
                    <strong>{number(report.address.chain_stats.tx_count, 0)}</strong>
                    <span>
                      {number(report.address.mempool_stats.tx_count, 0)} pending · not a complete
                      wallet
                    </span>
                  </div>
                </div>
                <details className="bitcoin-details">
                  <summary>Address totals</summary>
                  <p>
                    Confirmed received: {btc(report.address.chain_stats.funded_txo_sum)} · spent:{' '}
                    {btc(report.address.chain_stats.spent_txo_sum)}.
                  </p>
                  <p>
                    These are cumulative output values for one address, not income or investment
                    performance.
                  </p>
                </details>
                <div className="bitcoin-history-controls">
                  <h3>Address activity</h3>
                  <button
                    className={`button ${!showPending ? 'primary' : 'secondary'}`}
                    disabled={!!busy}
                    onClick={() => setShowPending(false)}
                  >
                    Confirmed
                  </button>
                  <button
                    className={`button ${showPending ? 'primary' : 'secondary'}`}
                    disabled={!!busy}
                    onClick={() => void history(true)}
                  >
                    Pending <RefreshCw size={12} />
                  </button>
                  <span>
                    {activity?.items.length ?? 0} shown ·{' '}
                    {showPending ? 'at most 50 pending' : '25 per source page'}
                  </span>
                </div>
                {busy === 'history' && (
                  <p role="status" className="footnote">
                    Reading address activity…
                  </p>
                )}
                {pending && showPending && (
                  <p className="footnote">
                    Pending observation: {new Date(pending.observed_at).toLocaleString()}.{' '}
                    {pending.warnings.join(' ')}
                    {pending.truncation_possible
                      ? ' The source limit was reached; more pending transactions may exist.'
                      : ''}
                  </p>
                )}
                <div className="table-scroll bitcoin-activity">
                  <table>
                    <thead>
                      <tr>
                        <th>Transaction</th>
                        <th>Confirmation</th>
                        <th>Net change · this address</th>
                        <th>Fee</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activity?.items.map((row) => (
                        <tr key={row.txid}>
                          <td>
                            <button
                              className="text-button bitcoin-tx-link"
                              title={row.txid}
                              disabled={!!busy}
                              onClick={() => void inspect(row.txid, simulated)}
                            >
                              {row.txid.slice(0, 12)}…{row.txid.slice(-6)}
                            </button>
                          </td>
                          <td>
                            <Confirmation status={row.status} />
                          </td>
                          <td
                            className={
                              row.net_sats == null ? '' : row.net_sats < 0 ? 'negative' : 'positive'
                            }
                          >
                            {btc(row.net_sats)}
                          </td>
                          <td>{number(row.fee_sats, 0)} sat</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!activity?.items.length && !busy && (
                  <p className="footnote">
                    No {showPending ? 'pending' : 'confirmed'} transactions were returned by this
                    source.
                  </p>
                )}
                {!showPending && confirmed?.next_cursor && confirmed.items.length < 200 && (
                  <button
                    className="button secondary"
                    disabled={!!busy}
                    onClick={() => void history(false)}
                  >
                    Load older confirmed transactions
                  </button>
                )}
                <p className="footnote">
                  {confirmed && confirmed.items.length >= 200
                    ? 'The in-page view is limited to 200 confirmed transactions. Use the public explorer for more. '
                    : ''}
                  History pages are separate observations; reorganizations can change their
                  contents. Export includes only the observations loaded here.
                </p>
              </>
            )}
            <p className="bitcoin-method-note">{report.note}</p>
          </div>
        )}
      </div>
    </Panel>
  );
}
