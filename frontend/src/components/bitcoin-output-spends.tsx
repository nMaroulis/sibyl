import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, BellPlus, Download, RefreshCw } from 'lucide-react';
import { api, number, post, refresh } from '../lib/api';
import {
  bitcoinSpendLabel,
  type BitcoinOutputSpends as Observation,
  type BitcoinWatch,
} from '../lib/bitcoin-types';
import { Badge, useToast } from './ui';
import './bitcoin-output-spends.css';

/** Explicit, dated spend checks remain separate from the transaction's earlier observation. */
export function BitcoinOutputSpends({
  transactionId,
  offset,
  demo,
  disabled,
  examples,
  watched,
  watchUnavailable,
  inspect,
}: {
  transactionId: string;
  offset: number;
  demo: boolean;
  disabled: boolean;
  examples?: { confirmed_spend_txid: string; pending_spend_txid: string };
  watched?: BitcoinWatch[];
  watchUnavailable: boolean;
  inspect: (identity: string) => void;
}) {
  const [observation, setObservation] = useState<Observation>();
  const [busy, setBusy] = useState(false);
  const [watching, setWatching] = useState<number | null>(null);
  const toast = useToast();

  const addWatch = async (index: number) => {
    setWatching(index);
    try {
      const watch = await post<BitcoinWatch>('/bitcoin/watches', {
        transaction_id: transactionId,
        output_index: index,
        demo,
      });
      toast(
        watch.active ? `Watching output #${index}` : `Output #${index} already has a paused watch`,
      );
      refresh();
    } catch (reason) {
      toast((reason as Error).message, true);
    } finally {
      setWatching(null);
    }
  };
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      controller.current?.abort();
      controller.current = null;
    },
    [],
  );
  const check = async () => {
    if (controller.current || disabled) return;
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setError('');
    try {
      setObservation(
        await api<Observation>('/bitcoin/output-spends', {
          method: 'POST',
          signal: request.signal,
          body: JSON.stringify({ transaction_id: transactionId, output_offset: offset, demo }),
        }),
      );
    } catch (reason) {
      if (!request.signal.aborted) setError((reason as Error).message);
    } finally {
      if (controller.current === request) {
        controller.current = null;
        setBusy(false);
      }
    }
  };
  const exportObservation = () => {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(observation, null, 2)], { type: 'application/json' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = 'sibyl-bitcoin-output-spends.json';
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <section className="bitcoin-spends" aria-label="Output spending status">
      <div className="bitcoin-spends-heading">
        <strong>Output spending status</strong>
        <button className="text-button" disabled={disabled || busy} onClick={() => void check()}>
          <RefreshCw size={12} className={busy ? 'spin' : ''} aria-hidden="true" />
          {busy ? 'Checking…' : observation ? 'Refresh checks' : 'Check output spends'}
        </button>
      </div>
      <p className="footnote">
        An explicit check of this output page. Unspent does not guarantee spendability.
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
          {observation ? ' The previous observation below has not been refreshed.' : ''}
        </p>
      )}
      {observation && (
        <>
          <div className="bitcoin-spends-attribution">
            <span>
              {observation.source} · {new Date(observation.observed_at).toLocaleString()}
            </span>
            <button className="text-button" onClick={exportObservation}>
              <Download size={11} /> Export spends
            </button>
          </div>
          {observation.warnings.map((warning) => (
            <p className="footnote" key={warning}>
              {warning}
            </p>
          ))}
          <div className="bitcoin-spends-list">
            {observation.items.map((output) => {
              const watch = watched?.find((item) => item.output_index === output.index);
              return (
                <div className="bitcoin-spend-row" key={output.index}>
                  <div>
                    <span>
                      Output #{output.index} · {number(output.value_sats, 0)} sat
                    </span>
                    <Badge
                      tone={
                        output.state === 'confirmed'
                          ? 'lime'
                          : output.state === 'pending' || output.state === 'unknown'
                            ? 'amber'
                            : 'neutral'
                      }
                    >
                      {bitcoinSpendLabel[output.state]}
                    </Badge>
                    {watch ? (
                      <small>{watch.active ? 'Watching' : 'Watch paused'}</small>
                    ) : (
                      <button
                        className="text-button bitcoin-watch-action"
                        aria-label={`Watch output #${output.index}`}
                        disabled={disabled || watchUnavailable || watching !== null}
                        onClick={() => void addWatch(output.index)}
                      >
                        <BellPlus size={12} aria-hidden="true" />
                        {watching === output.index ? 'Saving…' : 'Watch'}
                      </button>
                    )}
                  </div>
                  {output.spending_txid && (
                    <button
                      className="text-button bitcoin-spending-link"
                      disabled={disabled || busy}
                      onClick={() => inspect(output.spending_txid!)}
                    >
                      <code>{output.spending_txid}</code>
                      <ArrowUpRight size={12} aria-hidden="true" />
                    </button>
                  )}
                  {output.spending_input_index != null && (
                    <small>
                      Spending input #{output.spending_input_index}
                      {output.status?.confirmed
                        ? output.status.confirmations == null
                          ? ' · depth unavailable'
                          : ` · ${output.status.confirmations} confirmations`
                        : ''}
                    </small>
                  )}
                  {output.reason && <small>{output.reason}</small>}
                </div>
              );
            })}
          </div>
          <p className="footnote">
            {demo
              ? 'Demo watches use synthetic data.'
              : 'Watching sends this transaction ID to mempool.space for periodic checks.'}
          </p>
          <p className="footnote">{observation.spend_note}</p>
        </>
      )}
      {demo && examples?.confirmed_spend_txid && examples.pending_spend_txid && (
        <div className="bitcoin-spends-examples">
          <span>Demo spend examples:</span>
          <button
            className="text-button"
            disabled={disabled || busy}
            onClick={() => inspect(examples.confirmed_spend_txid)}
          >
            Confirmed
          </button>
          <button
            className="text-button"
            disabled={disabled || busy}
            onClick={() => inspect(examples.pending_spend_txid)}
          >
            Pending
          </button>
        </div>
      )}
    </section>
  );
}
