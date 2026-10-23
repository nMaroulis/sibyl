import { useState } from 'react';
import { Download } from 'lucide-react';
import { Badge, Empty, Loading, Panel, PanelTitle, useToast } from './ui';
import { downloadFile } from '../lib/api';
import { date, formatted } from '../lib/strategy-monitor';
import { useResource } from '../lib/hooks';
import type { StrategyEventPage } from '../lib/types';

/** An event journal page stays fixed while browsing history; the latest page can poll. */
export function DecisionJournal({
  jobId,
  interval,
  quote,
}: {
  jobId: string;
  interval: number;
  quote: string;
}) {
  const [action, setAction] = useState('all');
  const [before, setBefore] = useState<number>();
  const [exporting, setExporting] = useState(false);
  const toast = useToast();
  const events = useResource<StrategyEventPage>(
    `/strategies/jobs/${encodeURIComponent(jobId)}/events?action=${action}&limit=50${before ? `&before=${before}` : ''}`,
    before ? 0 : interval,
  );
  const download = async () => {
    setExporting(true);
    try {
      await downloadFile(
        `/strategies/jobs/${encodeURIComponent(jobId)}/events.csv?action=${action}`,
        `sibyl-${jobId.slice(0, 8)}-events.csv`,
      );
    } catch (error) {
      toast((error as Error).message, true);
    } finally {
      setExporting(false);
    }
  };
  return (
    <Panel className="full-panel">
      <PanelTitle
        title="Decision journal"
        subtitle="Every recorded signal, skipped action, lifecycle change, and failure"
        action={
          <button className="button secondary tiny" disabled={exporting} onClick={download}>
            <Download size={13} /> {exporting ? 'Exporting…' : 'Export matching logs'}
          </button>
        }
      />
      <div className="workspace-controls">
        <label>
          Show events
          <select
            value={action}
            onChange={(e) => {
              setAction(e.target.value);
              setBefore(undefined);
            }}
          >
            <option value="all">All activity</option>
            <option value="fills">BUY / SELL fills</option>
            <option value="ORDER_PLANNED">Exchange order plans</option>
            <option value="ORDER_SUBMITTED">Exchange order submissions</option>
            <option value="FILL_CORRECTION">Native fill corrections</option>
            <option value="HOLD">Hold decisions</option>
            <option value="SKIP_BUY">Skipped buys</option>
            <option value="SKIP_SELL">Skipped sells</option>
            <option value="ERROR">Errors</option>
            <option value="PAUSE">Pauses</option>
            <option value="STOP">Stops</option>
          </select>
        </label>
        <span className="muted">
          {before
            ? 'Browsing older events · refresh paused for this page'
            : 'Newest first · timestamps shown in your local time'}
        </span>
      </div>
      {events.error && (
        <div className="inline-alert" role="alert">
          {events.error}
          <button className="text-button" onClick={events.retry}>
            Retry
          </button>
        </div>
      )}
      {events.loading ? (
        <Loading />
      ) : events.data?.items.length ? (
        <div className="table-scroll">
          <table className="decision-table">
            <thead>
              <tr>
                <th>Observed time / candle</th>
                <th>Action / signal</th>
                <th>Reference / fill · {quote}</th>
                <th>Slippage / fee</th>
                <th>Paper account</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {events.data.items.map((event) => (
                <tr key={event.id}>
                  <td>
                    {date(event.timestamp)}
                    <small className="table-subline">
                      {event.candle_timestamp
                        ? `Candle ${date(event.candle_timestamp)}`
                        : `Event #${event.id}`}
                    </small>
                  </td>
                  <td>
                    <Badge
                      tone={
                        event.action === 'BUY'
                          ? 'lime'
                          : event.action === 'SELL' || event.action === 'ERROR'
                            ? 'rose'
                            : 'neutral'
                      }
                    >
                      {event.action.replaceAll('_', ' ')}
                    </Badge>
                    {event.signal && <small className="table-subline">Signal {event.signal}</small>}
                  </td>
                  <td>
                    {formatted(event.reference_price, 8)}
                    <small className="table-subline">
                      Fill {formatted(event.fill_price, 8)} · {formatted(event.quantity, 8)} units
                    </small>
                  </td>
                  <td>
                    {event.slippage_bps == null ? '—' : `${formatted(event.slippage_bps, 2)} bps`}
                    <small className="table-subline">
                      Fee {formatted(event.fee, 6)} {quote}
                    </small>
                  </td>
                  <td>
                    {formatted(event.equity, 6)} {quote}
                    <small className="table-subline">
                      Cash {formatted(event.cash, 6)} · Position {formatted(event.position, 8)}
                    </small>
                  </td>
                  <td>{event.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty title="No matching events">
          New decisions are recorded once per newly closed candle. Lifecycle events appear
          immediately.
        </Empty>
      )}
      <div className="chart-footnote">
        <span>
          {events.data?.matching_count ?? 0} matching events {before ? 'before this cursor' : ''} ·
          CSV includes all matching history
        </span>
        <div className="monitor-pagination">
          {before && (
            <button className="button secondary tiny" onClick={() => setBefore(undefined)}>
              Back to latest
            </button>
          )}
          <button
            className="button secondary tiny"
            disabled={!events.data?.has_more}
            onClick={() => setBefore(events.data?.next_before ?? undefined)}
          >
            Older events →
          </button>
        </div>
      </div>
    </Panel>
  );
}
