import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Bell, Pause, Play, Search, X } from 'lucide-react';
import { post, refresh } from '../lib/api';
import { bitcoinSpendLabel, type BitcoinWatch, type BitcoinWatchList } from '../lib/bitcoin-types';
import { Badge, PanelTitle, useToast } from './ui';
import './bitcoin-watches.css';

export function BitcoinWatches({
  data,
  loading,
  loadError,
  inspect,
}: {
  data?: BitcoinWatchList;
  loading: boolean;
  loadError: string;
  inspect: (watch: BitcoinWatch) => void;
}) {
  const [params] = useSearchParams();
  const selected = params.get('watch');
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (selected) panel.current?.scrollIntoView({ block: 'start' });
  }, [selected]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const toast = useToast();
  const control = async (watch: BitcoinWatch, action: 'pause' | 'resume' | 'remove') => {
    setBusy(watch.id);
    setError('');
    try {
      await post(`/bitcoin/watches/${watch.id}`, { action, revision: watch.revision });
      toast({ pause: 'Watch paused', resume: 'Watch resumed', remove: 'Watch removed' }[action]);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      refresh();
      setBusy('');
    }
  };
  const items = data?.items;

  return (
    <section className="bitcoin-watches" ref={panel} aria-label="Output watches">
      <PanelTitle
        title="Output watches"
        subtitle={
          items?.length
            ? `${items.filter((item) => item.active).length} active · Local inbox`
            : 'Local inbox'
        }
        action={<Bell size={17} aria-hidden="true" />}
      />
      <div className="bitcoin-watch-content">
        {data?.recovery_required && (
          <p className="footnote">Complete workspace recovery before adding or resuming a watch.</p>
        )}
        {(error || loadError) && (
          <p className="form-error" role="alert">
            {error || loadError}
          </p>
        )}
        {loading && !loadError && <p className="footnote">Loading watches…</p>}
        {selected && items && !items.some((watch) => watch.id === selected) && (
          <p className="footnote">This watch was removed. Its notices remain in the inbox.</p>
        )}
        {items?.length === 0 && (
          <p className="footnote">
            Check a transaction’s output spends, then select <strong>Watch</strong> on an output to
            follow it.
          </p>
        )}
        {items?.map((watch) => {
          const observation = watch.observation;
          return (
            <article
              className={`bitcoin-watch-row${selected === watch.id ? ' selected' : ''}`}
              key={watch.id}
            >
              <div className="bitcoin-watch-main">
                <div className="bitcoin-watch-label">
                  <strong>Output #{watch.output_index}</strong>
                  <Badge tone={watch.demo ? 'amber' : 'neutral'}>
                    {watch.demo ? 'Demo' : 'mempool.space'}
                  </Badge>
                  <Badge tone={watch.active && !watch.error ? 'green' : 'neutral'}>
                    {watch.active ? (watch.error ? 'Retrying' : 'Active') : 'Paused'}
                  </Badge>
                </div>
                <code title={watch.transaction_id}>{watch.transaction_id}</code>
                <small>
                  {observation
                    ? bitcoinSpendLabel[observation.state]
                    : 'Awaiting first observation'}
                  {observation &&
                    ` · Observed ${new Date(observation.observed_at).toLocaleString()}`}
                </small>
                {watch.error && (
                  <small className="bitcoin-watch-error">
                    {watch.error} {observation && 'Showing the last reliable observation. '}
                    {watch.active &&
                      watch.next_check &&
                      `Next check after ${new Date(watch.next_check).toLocaleTimeString()}.`}
                  </small>
                )}
              </div>
              <div className="bitcoin-watch-actions">
                <button className="text-button" onClick={() => inspect(watch)}>
                  <Search size={13} aria-hidden="true" /> Inspect
                </button>
                <button
                  className="text-button"
                  disabled={!!busy || (!watch.active && data?.recovery_required)}
                  onClick={() => void control(watch, watch.active ? 'pause' : 'resume')}
                >
                  {watch.active ? (
                    <Pause size={13} aria-hidden="true" />
                  ) : (
                    <Play size={13} aria-hidden="true" />
                  )}
                  {watch.active ? 'Pause' : 'Resume'}
                </button>
                <button
                  className="text-button"
                  disabled={!!busy}
                  onClick={() => void control(watch, 'remove')}
                >
                  <X size={13} aria-hidden="true" /> Remove
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
