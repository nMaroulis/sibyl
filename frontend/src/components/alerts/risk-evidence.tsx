import { lazy, Suspense, useState } from 'react';
import { Badge, Empty, ErrorState, Loading } from '../ui';
import { useResource } from '../../lib/hooks';
import { number } from '../../lib/api';
import { date } from '../../lib/strategy-monitor';
import { riskLabel, riskValue, type RiskEvidenceData } from '../../lib/risk-alerts';

const ValueChart = lazy(() =>
  import('../charts').then((module) => ({ default: module.ValueChart })),
);

/** Retained snapshots only: opening this dialog never calls an exchange or prices a holding. */
export function RiskEvidence({
  ruleId,
  sampleId,
  example,
}: {
  ruleId: string;
  sampleId?: number;
  example?: RiskEvidenceData;
}) {
  const [selected, setSelected] = useState(sampleId);
  const resource = useResource<RiskEvidenceData>(
    `/risk-alerts/${encodeURIComponent(ruleId)}/evidence${selected ? `?sample_id=${selected}` : ''}`,
    0,
    !example,
  );
  const data = example || resource.data;
  if (resource.error) return <ErrorState message={resource.error} retry={resource.retry} />;
  if (!data) return <Loading />;
  const sample = data.sample;
  const metric = sample?.policy.metric || data.rule.metric;
  const asset = sample?.policy.asset || data.rule.asset;
  return (
    <div className="risk-evidence">
      <div className="strategy-alert-tags">
        <Badge>Saved evidence · revision {data.revision}</Badge>
        {sample?.environment === 'demo' ? (
          <Badge tone="demo">Demo</Badge>
        ) : sample?.environment === 'test' ? (
          <Badge tone="peach">Test funds</Badge>
        ) : (
          <Badge>Production funds</Badge>
        )}
      </div>
      {data.rule.error && (
        <p className="inline-alert">
          Latest attempt: {data.rule.error} Values below, if present, are retained observations.
        </p>
      )}
      {!sample ? (
        <Empty
          title={
            data.selected_sample_id
              ? 'Snapshot details have expired'
              : 'Waiting for a complete valuation'
          }
        >
          {data.selected_sample_id
            ? 'The inbox retains the original notification summary. Older sample details are subject to retention limits.'
            : 'The watch needs complete active-account reads and fresh dated conversion quotes. No partial total is used.'}
        </Empty>
      ) : (
        <>
          <div className="risk-evidence-summary">
            <div>
              <small>{riskLabel(metric, asset)}</small>
              <strong className="monetary">{riskValue(sample.metric_value, metric)}</strong>
            </div>
            <div>
              <small>Reference account value</small>
              <strong className="monetary">{number(sample.total, 2)} USDT</strong>
            </div>
            <div>
              <small>Observed at</small>
              <strong>{date(sample.as_of)}</strong>
            </div>
          </div>
          {sample.revision !== data.rule.revision && (
            <p className="inline-alert">
              This snapshot belongs to an earlier rule revision. Its accounts, source and values are
              preserved below.
            </p>
          )}
          <p className="footnote monetary">
            Rule at this check: {metric === 'value_floor' ? 'at or below' : 'at or above'}{' '}
            {riskValue(sample.policy.threshold, metric)} · recovery{' '}
            {riskValue(sample.policy.reset_threshold, metric)}.
          </p>
          <p className="footnote">
            {sample.accounts.map((a) => a.label).join(' + ')} · {sample.source_info.source_label} ·
            pricing environment {sample.source_info.environment}
          </p>
          {data.samples.length > 1 && (
            <>
              <label className="risk-evidence-picker">
                Observed check
                <select
                  aria-label="Observed check"
                  value={sample.id}
                  disabled={!!example}
                  onChange={(e) => setSelected(Number(e.target.value))}
                >
                  {[...data.samples].reverse().map((s) => (
                    <option value={s.id} key={s.id}>
                      {date(s.as_of)}
                    </option>
                  ))}
                </select>
              </label>
              <div className="monetary">
                <Suspense fallback={<Loading />}>
                  <ValueChart
                    data={data.samples.map((s) => ({ timestamp: s.as_of, value: s.total }))}
                    currency={false}
                    unit="USDT"
                    height={190}
                  />
                </Suspense>
              </div>
            </>
          )}
          {metric === 'drawdown' && (
            <p className="footnote">
              Observed peak <span className="monetary">{number(sample.peak ?? 0, 2)} USDT</span> ·{' '}
              {date(sample.peak_at)}. Cash movements affect these values.
            </p>
          )}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Value · USDT</th>
                  <th>Allocation</th>
                  <th>Conversion path</th>
                  <th>Oldest provider quote</th>
                </tr>
              </thead>
              <tbody>
                {sample.holdings.map((h) => (
                  <tr key={h.asset}>
                    <td>
                      <strong>{h.asset}</strong>
                    </td>
                    <td className="monetary">{number(h.value, 2)}</td>
                    <td className="monetary">{number(h.allocation, 2)}%</td>
                    <td>{h.path.join(' → ')}</td>
                    <td>
                      {h.observed_at ? date(h.observed_at) : 'USDT denomination · no conversion'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details>
            <summary>Balance receipt times</summary>
            <p className="footnote">
              Receipts record when each private spot read completed, not a provider-guaranteed
              balance timestamp. This is not an atomic cross-exchange snapshot.
            </p>
            {sample.balance_reads.map((read) => (
              <p className="footnote" key={read.account_id}>
                {sample.accounts.find((a) => a.id === read.account_id)?.label || read.account_id} ·{' '}
                {date(read.received_at)}
              </p>
            ))}
          </details>
        </>
      )}
      <p className="footnote">
        {data.note} Up to {data.sample_limit} recent samples per rule, within a{' '}
        {data.retention_days}-day/global storage budget. No provider reads are made here.
      </p>
    </div>
  );
}
