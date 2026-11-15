import { useState } from 'react';
import { Archive, ArchiveRestore, RefreshCw } from 'lucide-react';
import { number, post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { Badge, ErrorState, Loading, Panel, PanelTitle, useToast } from '../ui';
import type { Job } from '../../lib/types';

type Performance = {
  method: string;
  quote: string;
  opening_at: string;
  archived_at: string | null;
  archive_blocker: string | null;
  flow_count: number;
  mark: { as_of: string; price: number | null; kind: string } | null;
  reason: string | null;
  fee_valuation: {
    quote_total: number | null;
    missing_count: number;
    recent: {
      fill_id: string;
      asset: string;
      native_fee: number;
      quote_fee: number;
      legs: { symbol: string }[];
    }[];
  } | null;
  flows: { action: string; timestamp_ms: number; value: number }[];
  metrics: {
    opening: number;
    closing: number;
    weighted_capital: number;
    net_external_flow: number;
    gain: number;
    return_pct: number | null;
  } | null;
};

export function RunPerformance({ job, interval }: { job: Job; interval: number }) {
  const path = `/strategies/exchange/jobs/${encodeURIComponent(job.id)}`;
  const resource = useResource<Performance>(`${path}/performance`, interval);
  const [busy, setBusy] = useState('');
  const toast = useToast();
  const report = resource.data;
  const archived = !!report?.archived_at;
  const flatTerminal = ['completed', 'stopped'].includes(job.status) && job.quantity === 0;
  const action = async (kind: 'mark' | 'archive') => {
    setBusy(kind);
    try {
      if (kind === 'mark') await post(`${path}/performance/mark`);
      else await post(`${path}/archive`, { archived: !archived });
      refresh();
      toast(
        kind === 'mark'
          ? 'Valuation mark refreshed'
          : archived
            ? 'Run restored to the list'
            : 'Run archived',
      );
    } catch (error) {
      toast((error as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  const metrics = report?.metrics;
  return (
    <Panel className="full-panel">
      <PanelTitle
        title="Lifetime performance"
        subtitle="Exchange run · Modified Dietz estimate"
        action={archived ? <Badge>Archived</Badge> : undefined}
      />
      {resource.error && <ErrorState message={resource.error} retry={resource.retry} />}
      {resource.loading && !report && <Loading />}
      {report && (
        <>
          {metrics && (
            <div className="extended-metrics">
              <div>
                <small>Flow-adjusted return</small>
                <strong>
                  {metrics.return_pct == null ? '—' : `${number(metrics.return_pct, 2)}%`}
                </strong>
              </div>
              <div>
                <small>Gain · {report.quote}</small>
                <strong>{number(metrics.gain, 6)}</strong>
              </div>
              <div>
                <small>Net attributed flows · {report.quote}</small>
                <strong>{number(metrics.net_external_flow, 6)}</strong>
              </div>
              <div>
                <small>Weighted capital · {report.quote}</small>
                <strong>{number(metrics.weighted_capital, 6)}</strong>
              </div>
            </div>
          )}
          {report.fee_valuation && (
            <details className="padded">
              <summary>Third-currency fee valuation</summary>
              <p className="footnote">
                Historical closes from this run’s exact exchange feed.{' '}
                {report.fee_valuation.quote_total == null
                  ? `${report.fee_valuation.missing_count} fees lack a usable value.`
                  : `Net estimated fees ${number(report.fee_valuation.quote_total, 8)} ${report.quote}.`}{' '}
                Reported separately from execution accounting.
              </p>
              <ul>
                {report.fee_valuation.recent.map((fee, index) => (
                  <li key={`${fee.fill_id}:${index}`}>
                    {number(fee.native_fee, 8)} {fee.asset} · {number(fee.quote_fee, 8)}{' '}
                    {report.quote}
                    {' · '}
                    {fee.legs.map((leg) => leg.symbol).join(' → ')}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {report.reason && <p className="footnote padded">{report.reason}</p>}
          <p className="footnote padded">
            {report.mark && (
              <>
                {report.mark.kind === 'flat_cash'
                  ? 'Terminal quote cash'
                  : 'Observed exchange midpoint'}{' '}
                · {new Date(report.mark.as_of).toLocaleString()}.{' '}
              </>
            )}
            Adoption, release and handoff are valued at their recorded reference prices.
          </p>
          {!!report.flows.length && (
            <details className="padded">
              <summary>Attributed flows ({report.flow_count})</summary>
              {report.flow_count > report.flows.length && (
                <p className="footnote">Latest 100 flows. Export the journal for all receipts.</p>
              )}
              <ul>
                {report.flows.map((flow, index) => (
                  <li key={index}>
                    {flow.action.replaceAll('_', ' ')} · {number(flow.value, 8)} {report.quote} ·{' '}
                    {new Date(flow.timestamp_ms).toLocaleString()}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <div className="workspace-controls">
            {report.mark?.kind !== 'flat_cash' && (
              <button
                className="button secondary tiny"
                disabled={!!busy}
                onClick={() => void action('mark')}
              >
                <RefreshCw size={13} />{' '}
                {busy === 'mark' ? 'Reading mark…' : 'Refresh valuation mark'}
              </button>
            )}
            {(archived || (flatTerminal && !report.archive_blocker)) && (
              <button
                className="button secondary tiny"
                disabled={!!busy}
                onClick={() => void action('archive')}
              >
                {archived ? <ArchiveRestore size={13} /> : <Archive size={13} />}
                {archived ? 'Restore to run list' : 'Archive run'}
              </button>
            )}
          </div>
          {!archived && flatTerminal && report.archive_blocker && (
            <p className="footnote padded">{report.archive_blocker}</p>
          )}
        </>
      )}
    </Panel>
  );
}
