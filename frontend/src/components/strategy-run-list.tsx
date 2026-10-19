import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Search } from 'lucide-react';
import { Badge, Change, Empty, Panel, PanelTitle } from './ui';
import { number } from '../lib/api';
import { date, monitorURL, runName, tone } from '../lib/strategy-monitor';
import type { Job, Strategy } from '../lib/types';

/** Searchable entry point for running, paused, completed, and stopped paper runs. */
export function StrategyList({ jobs, catalog }: { jobs: Job[]; catalog: Strategy[] }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const rows = jobs.filter(
    (job) =>
      (status === 'all' || job.status === status) &&
      `${runName(job, catalog)} ${job.parameters.symbol} ${job.id}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <Panel className="full-panel">
      <PanelTitle
        title="Your strategy runs"
        subtitle="Open a run to inspect its live observations, decisions, and paper account"
        action={
          <Badge>
            {jobs.filter((j) => j.status === 'running').length} running · {jobs.length} total
          </Badge>
        }
      />
      <div className="workspace-controls monitor-list-controls">
        <label className="monitor-search-label">
          Find a run
          <div className="search-field">
            <Search size={14} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Strategy, market, or run ID…"
              aria-label="Search strategy runs"
            />
          </div>
        </label>
        <label>
          Status
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            aria-label="Filter strategy status"
          >
            {['all', 'running', 'paused', 'completed', 'stopped'].map((s) => (
              <option key={s} value={s}>
                {s === 'all' ? 'All statuses' : s[0].toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {rows.length ? (
        <div className="table-scroll">
          <table className="strategy-runs-table">
            <thead>
              <tr>
                <th>Strategy / market</th>
                <th>Started</th>
                <th>Status</th>
                <th>Paper equity</th>
                <th>Return</th>
                <th>Last worker check</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((job) => (
                <tr key={job.id}>
                  <td>
                    <Link className="monitor-run-name" to={monitorURL(job.id)}>
                      {runName(job, catalog)}
                      <small>
                        {job.parameters.symbol} · {job.parameters.timeframe ?? '1d'} ·{' '}
                        {job.id.slice(0, 8)}
                      </small>
                    </Link>
                  </td>
                  <td>{date(job.created_at)}</td>
                  <td>
                    <Badge tone={tone(job.status)}>{job.status}</Badge>
                    {job.error && <small className="table-subline negative">Needs attention</small>}
                  </td>
                  <td>
                    {number(job.equity, job.parameters.symbol.endsWith('/BTC') ? 6 : 2)}{' '}
                    <small>{job.parameters.symbol.split('/')[1]}</small>
                  </td>
                  <td>
                    <Change value={(job.equity / job.parameters.capital - 1) * 100} />
                  </td>
                  <td>{date(job.checked_at)}</td>
                  <td>
                    <Link className="button secondary tiny" to={monitorURL(job.id)}>
                      Open monitor <ArrowUpRight size={12} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty title={jobs.length ? 'No matching runs' : 'Your first strategy starts here'}>
          {jobs.length
            ? 'Try another market, name, or status filter.'
            : 'Build an idea, then start a paper strategy. Its monitor will open automatically.'}
        </Empty>
      )}
    </Panel>
  );
}
