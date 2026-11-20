import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, Clock3, RefreshCw } from 'lucide-react';
import { post, number, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import { Badge, ErrorState, useToast } from './ui';

type Policy = {
  enabled: boolean;
  recent_days: number;
  divergence_threshold: number;
  min_new_days: number;
  cooldown_days: number;
};
type State = {
  revision: number;
  policy: Policy;
  confirmation: string;
  note: string;
  assessment: null | {
    status: string;
    checked_at: string;
    js_divergence?: number;
    new_candles: number;
    required_candles?: number;
    message?: string;
    mean_shift_in_reference_std?: number | null;
    volatility_ratio?: number | null;
    recent_start?: string;
    recent_end?: string;
  };
  history: {
    id: string;
    status: string;
    created_at: string;
    candidate_id?: string;
    candidate_version?: number;
    error?: string;
  }[];
};

/** Inspect saved drift, then opt into version-bound candidate research explicitly. */
export function ForecastDrift({ modelId }: { modelId: string }) {
  const resource = useResource<State>(`/forecast-models/${modelId}/drift`, 0);
  const [policy, setPolicy] = useState<Policy>();
  const [confirmation, setConfirmation] = useState(''),
    [busy, setBusy] = useState('');
  const toast = useToast();
  useEffect(() => setPolicy(resource.data?.policy), [resource.data?.revision, modelId]);
  const act = async (action: 'check' | 'save' | 'recalibrate' | 'schedule') => {
    if (!resource.data || !policy) return;
    setBusy(action);
    try {
      const current = resource.data;
      if (action === 'schedule') {
        await post('/workspace/jobs', {
          label: 'Forecast recalibration policy',
          kind: 'forecast.recalibrate',
          arguments: { model_id: modelId, revision: current.revision },
          interval_seconds: 86400,
          enabled: true,
          missed: 'skip',
        });
        toast('Daily retained-data policy check scheduled. Manage it in Settings → Workspace.');
      } else {
        const result = await post<{ status?: string; candidate_id?: string }>(
          `/forecast-models/${modelId}/${action === 'save' ? 'drift' : action === 'check' ? 'drift/check' : 'recalibrate'}`,
          action === 'save'
            ? { ...policy, revision: current.revision, confirmation }
            : action === 'recalibrate'
              ? { model_id: modelId, revision: current.revision }
              : {},
        );
        toast(
          action === 'save'
            ? 'Policy saved. Existing job revisions stay pinned.'
            : action === 'check'
              ? 'Drift evidence updated.'
              : `Recalibration: ${result.status?.replaceAll('_', ' ') ?? 'finished'}.`,
        );
      }
      resource.retry();
      refresh();
    } catch (error) {
      toast((error as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  const current = resource.data,
    sample = current?.assessment;
  return (
    <details className="advanced-options">
      <summary>
        <Activity size={15} /> Drift &amp; candidate recalibration
      </summary>
      <p className="footnote">
        Compare original training returns with later retained daily observations. No prices are
        fetched here. Review source history in <Link to="/markets?view=history">Markets</Link>.
      </p>
      {resource.error && <ErrorState message={resource.error} retry={resource.retry} />}
      {sample && (
        <>
          <Badge tone={sample.status === 'shift' ? 'amber' : 'neutral'}>
            {sample.status.replaceAll('_', ' ')}
          </Badge>
          <div className="metrics-inline">
            <span>
              New closed days <strong>{sample.new_candles}</strong>
            </span>
            {sample.js_divergence != null && (
              <span>
                JS divergence <strong>{number(sample.js_divergence, 4)}</strong>
              </span>
            )}
            {sample.volatility_ratio != null && (
              <span>
                Volatility ratio <strong>{number(sample.volatility_ratio, 2)}×</strong>
              </span>
            )}
          </div>
          <p className="footnote">
            {sample.message ??
              `Compared ${sample.recent_start?.slice(0, 10)} – ${sample.recent_end?.slice(0, 10)}. Descriptive shift, not a calibrated significance or forecast-accuracy test.`}
          </p>
        </>
      )}
      <button className="button secondary tiny" disabled={!!busy} onClick={() => act('check')}>
        <RefreshCw size={13} />
        {busy === 'check' ? 'Checking…' : 'Check retained observations'}
      </button>
      {current && policy && (
        <>
          <details className="advanced-options">
            <summary>Candidate policy</summary>
            <form
              className="form"
              onSubmit={(event) => {
                event.preventDefault();
                act('save');
              }}
            >
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={policy.enabled}
                  onChange={(event) => setPolicy({ ...policy, enabled: event.target.checked })}
                />
                Allow new research candidates when this policy is met
              </label>
              {(
                [
                  ['recent_days', 'Recent return days', 30, 180],
                  ['divergence_threshold', 'Minimum JS divergence', 0.0001, 0.69],
                  ['min_new_days', 'Minimum new closed days', 30, 365],
                  ['cooldown_days', 'Cooldown after a candidate · days', 1, 365],
                ] as const
              ).map(([key, label, min, max]) => (
                <label key={key}>
                  {label}
                  <input
                    type="number"
                    min={min}
                    max={max}
                    step={key === 'divergence_threshold' ? 'any' : 1}
                    value={policy[key]}
                    onChange={(event) =>
                      setPolicy({ ...policy, [key]: Number(event.target.value) })
                    }
                  />
                </label>
              ))}
              <p className="footnote">
                Uses the original recipe and exact source, with a recent consecutive window the size
                of the original input. A new version keeps independent chronological
                train/calibration/test evidence. It never replaces your selection. Saving
                invalidates jobs pinned to an older revision.
              </p>
              <label>
                Type {current.confirmation}
                <input
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                  autoComplete="off"
                />
              </label>
              <button
                className="button primary"
                disabled={!!busy || confirmation !== current.confirmation}
              >
                Save candidate policy
              </button>
            </form>
          </details>
          <div className="inline-actions">
            <button
              className="button secondary tiny"
              disabled={!!busy || !current.policy.enabled}
              onClick={() => act('recalibrate')}
            >
              {busy === 'recalibrate' ? 'Evaluating policy…' : 'Run candidate policy once'}
            </button>
            <button
              className="button secondary tiny"
              disabled={!!busy || !current.policy.enabled}
              onClick={() => act('schedule')}
            >
              <Clock3 size={13} />
              Schedule daily check
            </button>
          </div>
          <p className="footnote">
            Checks run only while the backend is running. New policy revisions require a new job.
            Cancellation cannot undo a model already fitted; training interrupted by restart is not
            replayed.
          </p>
          {!!current.history.length && (
            <details className="advanced-options">
              <summary>Candidate outcomes · {current.history.length}</summary>
              {current.history.map((row) => (
                <p key={row.id}>
                  <Badge>{row.status}</Badge> {new Date(row.created_at).toLocaleString()}{' '}
                  {row.candidate_id && (
                    <Link to={`/forecast?tab=models&model=${row.candidate_id}`}>
                      Review candidate v{row.candidate_version} ↗
                    </Link>
                  )}
                  {row.error && <span className="footnote">{row.error}</span>}
                </p>
              ))}
            </details>
          )}
        </>
      )}
    </details>
  );
}
