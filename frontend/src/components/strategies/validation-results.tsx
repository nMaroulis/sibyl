import { useState } from 'react';
import { RotateCcw } from 'lucide-react';
import { AgentButton } from '../agents';
import { Badge, Change } from '../ui';
import { BacktestChart } from './backtest-chart';
import { downloadFile, exportCSV, number } from '../../lib/api';
import type { ValidationReport } from '../../lib/strategy-validation';

const choices = (values: Record<string, number>) =>
  Object.entries(values)
    .map(([key, value]) => `${key.replaceAll('_', ' ')} ${value}`)
    .join(' · ') || 'Fixed settings';
const date = (value: string) =>
  new Date(value).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' });

/** Recorded test executions and their earlier training choices, kept visibly distinct. */
export function ValidationResults({
  report,
  busy,
  onRerun,
  onError,
}: {
  report: ValidationReport;
  busy: string;
  onRerun: () => void;
  onError: (message: string) => void;
}) {
  const [windowIndex, setWindowIndex] = useState(0);
  const fold = report.folds[windowIndex];
  return (
    <section className="validation-result" aria-label="Walk-forward results">
      <div className="validation-result-heading">
        <div>
          <Badge tone={report.source === 'demo' ? 'sand' : 'blue'}>
            {report.source === 'demo' ? 'Demo · Walk-forward' : 'Walk-forward'}
          </Badge>
          <h3>
            {report.dataset.symbol} · {report.request.parameters.strategy}
          </h3>
          <p>
            {report.dataset.timeframe} · {report.candidate_count} candidates · {report.folds.length}{' '}
            independent test windows · {report.summary.test_bars} test bars ·{' '}
            {report.summary.trades} round trips
          </p>
          <p>
            Training objective:{' '}
            {
              {
                return_pct: 'highest net return',
                sharpe: 'highest Sharpe ratio',
                max_drawdown: 'lowest maximum drawdown',
              }[report.request.objective]
            }{' '}
            · {report.request.initial_train_pct}% initial training · minimum{' '}
            {report.request.min_train_trades} training round trips
          </p>
        </div>
        <AgentButton module="broker" context={{ validation_id: report.id }} />
      </div>
      <div className="validation-summary">
        <div>
          <small>Mean test return</small>
          <strong>
            <Change value={report.summary.mean_return_pct} />
          </strong>
        </div>
        <div>
          <small>Mean fixed-settings return</small>
          <strong>
            <Change value={report.summary.mean_fixed_return_pct} />
          </strong>
        </div>
        <div>
          <small>Mean buy &amp; hold return</small>
          <strong>
            <Change value={report.summary.mean_benchmark_pct} />
          </strong>
        </div>
        <div>
          <small>Profitable test windows</small>
          <strong>
            {report.summary.profitable_windows} / {report.folds.length}
          </strong>
        </div>
      </div>
      <p className="validation-caption">
        Each test resets to {number(report.request.parameters.capital)}{' '}
        {report.dataset.symbol.split('/')[1]} and closes its final position with costs. Means are
        unweighted independent returns, not a compounded equity curve.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Test window</th>
              <th>Training choice</th>
              <th>Test return</th>
              <th>Fixed settings</th>
              <th>Buy &amp; hold</th>
              <th>Max drawdown</th>
              <th>Round trips</th>
            </tr>
          </thead>
          <tbody>
            {report.folds.map((item, index) => (
              <tr key={item.index} aria-selected={index === windowIndex}>
                <td>
                  <button
                    type="button"
                    className="text-button"
                    aria-pressed={index === windowIndex}
                    onClick={() => setWindowIndex(index)}
                  >
                    Window {item.index} ↗
                  </button>
                  <small className="table-subline">
                    {date(item.test.start)} – {date(item.test.end)} (exclusive)
                  </small>
                </td>
                <td>
                  {choices(item.selected.overrides)}
                  <small className="table-subline">
                    Selected from {item.train.scored_bars} training bars
                  </small>
                </td>
                <td>
                  <Change value={item.out_of_sample.return_pct} />
                </td>
                <td>
                  <Change value={item.fixed_parameters.return_pct} />
                </td>
                <td>
                  <Change value={item.out_of_sample.benchmark_pct} />
                </td>
                <td>{number(item.out_of_sample.max_drawdown)}%</td>
                <td>{item.out_of_sample.trades}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="validation-window-heading">
        <h4>Window {fold.index} · out-of-sample executions</h4>
        <span>
          {fold.test.bars} test bars · {fold.train.bars} earlier context bars
        </span>
      </div>
      <BacktestChart
        key={`${report.id}:${fold.index}`}
        result={{ ...fold.out_of_sample, id: report.id, source: report.source }}
      />
      <details className="advanced-options">
        <summary>Training ranking for window {fold.index}</summary>
        <p>
          Only these earlier training scores selected the settings. No candidate was ranked on this
          window's test results.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Parameters</th>
                <th>Training return</th>
                <th>Sharpe</th>
                <th>Max drawdown</th>
                <th>Round trips</th>
                <th>Eligible</th>
              </tr>
            </thead>
            <tbody>
              {fold.training_ranking.map((candidate) => (
                <tr key={candidate.candidate_id}>
                  <td>
                    {choices(candidate.overrides)}
                    {candidate.candidate_id === fold.selected.candidate_id && (
                      <Badge>Selected</Badge>
                    )}
                  </td>
                  <td>
                    <Change value={candidate.return_pct} />
                  </td>
                  <td>{number(candidate.sharpe)}</td>
                  <td>{number(candidate.max_drawdown)}%</td>
                  <td>{candidate.trades}</td>
                  <td>{candidate.eligible ? 'Yes' : 'Too few trades'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <details className="advanced-options">
        <summary>Method &amp; input evidence</summary>
        <p>
          {report.method} · {report.engine_revision} · {report.dataset.source_label} ·{' '}
          {report.dataset.digest}
        </p>
        <ul>
          {report.assumptions.map((assumption) => (
            <li key={assumption}>{assumption}</li>
          ))}
        </ul>
        <p>
          Saved {new Date(report.created_at).toLocaleString()}.{' '}
          {report.rerun_of && `Rerun of ${report.rerun_of}.`}
        </p>
        <pre className="validation-settings">{JSON.stringify(report.request, null, 2)}</pre>
      </details>
      <div className="validation-actions">
        <button type="button" className="button secondary tiny" disabled={!!busy} onClick={onRerun}>
          <RotateCcw size={13} />
          {busy === 'rerun' ? 'Recomputing…' : 'Rerun exact study'}
        </button>
        <button
          type="button"
          className="text-button"
          onClick={() => {
            void downloadFile(
              `/strategies/validations/${report.id}`,
              `sibyl-validation-${report.id}.json`,
            ).catch((e) => onError((e as Error).message));
          }}
        >
          Export full evidence
        </button>
        <button
          type="button"
          className="text-button"
          onClick={() =>
            exportCSV('sibyl-validation-windows.csv', [
              [
                'Window',
                'Test start',
                'Test end (exclusive)',
                'Selected parameters',
                'Test return %',
                'Fixed return %',
                'Buy & hold %',
                'Max drawdown %',
                'Round trips',
              ],
              ...report.folds.map((f) => [
                f.index,
                f.test.start,
                f.test.end,
                choices(f.selected.overrides),
                f.out_of_sample.return_pct,
                f.fixed_parameters.return_pct,
                f.out_of_sample.benchmark_pct,
                f.out_of_sample.max_drawdown,
                f.out_of_sample.trades,
              ]),
            ])
          }
        >
          Export window summary
        </button>
      </div>
    </section>
  );
}
