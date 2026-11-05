import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowLeftRight,
  ArrowUpRight,
  Download,
  FileSearch,
  LoaderCircle,
  Plus,
  RotateCcw,
  Square,
  Trash2,
} from 'lucide-react';
import { Badge, Empty, ErrorState, Loading, Modal, useToast } from '../ui';
import { SibylProgress } from '../sibyl-activity';
import { useResource } from '../../lib/hooks';
import { api, post } from '../../lib/api';
import { InvestigationForm } from './form';
import { InvestigationReport } from './report';
import { Briefings } from './briefings';
import { running, runLabel } from './types';
import type { Investigation, ResearchRun } from './types';
import '../../styles/investigations.css';

/** Saved research reopens from durable reports; navigating away never resubmits inference. */
export function Investigations() {
  const [params, setParams] = useSearchParams();
  const selected = params.get('investigation') ?? '';
  const selectedRun = params.get('run') ?? '';
  const [following, setFollowing] = useState(false);
  const library = useResource<Investigation[]>('/investigations', following ? 2000 : 0);
  const definition = useResource<Investigation>(
    `/investigations/${selected}`,
    following ? 2000 : 0,
    Boolean(selected),
  );
  const runId =
    selectedRun || (definition.data?.id === selected ? definition.data.runs[0]?.id : undefined);
  const result = useResource<ResearchRun>(
    `/investigations/${selected}/runs/${runId}`,
    following ? 1000 : 0,
    Boolean(selected && runId),
  );
  const [comparison, setComparison] = useState('');
  const compared = useResource<ResearchRun>(
    `/investigations/${selected}/runs/${comparison}`,
    0,
    Boolean(selected && comparison),
  );
  const status = useResource<{ ready: boolean; reason: string; simulated: boolean }>(
    '/sibyl',
    30000,
  );
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const toast = useToast();
  const item = definition.data?.id === selected ? definition.data : undefined;
  const run = result.data?.id === runId ? result.data : undefined;
  const active = item?.runs.find(running);
  const ready = Boolean(status.data?.ready);
  const refreshReports = useCallback(() => {
    definition.retry();
    library.retry();
  }, [definition.retry, library.retry]);
  useEffect(
    () =>
      setFollowing(
        Boolean(library.data?.some((entry) => entry.runs.some(running)) || active || running(run)),
      ),
    [library.data, active?.id, active?.status, run?.status],
  );
  useEffect(() => {
    setComparison('');
    setError('');
  }, [selected]);
  useEffect(() => {
    if (run && !running(run)) {
      definition.retry();
      library.retry();
    }
  }, [run?.id, run?.status, definition.retry, library.retry]);
  const navigate = (identity: string, version?: string) => {
    const next = new URLSearchParams(params);
    next.set('tab', 'investigations');
    next.set('investigation', identity);
    if (version) next.set('run', version);
    else next.delete('run');
    setParams(next);
  };
  const start = async (identity: string) => {
    setBusy('run');
    setError('');
    try {
      const next = await post<ResearchRun>(`/investigations/${identity}/runs`, {
        request_id: crypto.randomUUID().replaceAll('-', ''),
      });
      navigate(identity, next.id);
      setFollowing(true);
      definition.retry();
      library.retry();
      toast('Investigation started. You can leave this page and return to the report.');
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  const stop = async () => {
    if (!active) return;
    setBusy('stop');
    try {
      await post(`/investigations/${selected}/runs/${active.id}/cancel`);
      result.retry();
      definition.retry();
      library.retry();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  const remove = async () => {
    setBusy('delete');
    try {
      await api(`/investigations/${selected}`, { method: 'DELETE' });
      const next = new URLSearchParams(params);
      next.delete('investigation');
      next.delete('run');
      setParams(next);
      setDeleting(false);
      library.retry();
      toast('Investigation reports deleted.');
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  const download = async () => {
    if (!run) return;
    setBusy('export');
    try {
      const data = await api(`/investigations/${selected}/runs/${run.id}/export`);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
      );
      const link = document.createElement('a');
      link.href = url;
      link.download = `sibyl-investigation-v${run.version}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  return (
    <div className="investigations-workspace">
      {creating && (
        <InvestigationForm
          ready={ready}
          onClose={() => setCreating(false)}
          onCreated={async (created, shouldRun) => {
            setCreating(false);
            library.retry();
            navigate(created.id);
            if (shouldRun) await start(created.id);
            else toast('Investigation saved. Run it when you’re ready.');
          }}
        />
      )}
      {deleting && (
        <Modal title="Delete this investigation?" onClose={() => setDeleting(false)}>
          <p>
            All saved report versions and source previews in this investigation will be removed. Its
            separate conversations remain available in Chat.
          </p>
          <div className="form-actions">
            <button className="button" onClick={() => setDeleting(false)}>
              Keep reports
            </button>
            <button className="button danger" disabled={!!busy} onClick={() => void remove()}>
              Delete reports
            </button>
          </div>
        </Modal>
      )}
      {!ready && !status.loading && (
        <div className="investigation-setup">
          <FileSearch size={19} />
          <div>
            <strong>Your research, ready when you are.</strong>
            <p>
              {status.error || status.data?.reason || 'Connect an AI model to run investigations.'}{' '}
              Saved reports remain available.
            </p>
          </div>
          <Link className="button" to="/settings?tab=models">
            AI model settings
            <ArrowUpRight size={13} />
          </Link>
        </div>
      )}
      {error && <ErrorState message={error} />}
      <div className="investigation-layout">
        <aside className="investigation-library">
          <header>
            <div>
              <span className="sibyl-eyebrow">Your research</span>
              <h2>Investigations</h2>
            </div>
            <button
              className="icon-button"
              aria-label="New investigation"
              onClick={() => setCreating(true)}
            >
              <Plus size={18} />
            </button>
          </header>
          <p>Questions worth coming back to.</p>
          {library.error ? (
            <ErrorState message={library.error} retry={library.retry} />
          ) : library.loading ? (
            <Loading />
          ) : !library.data?.length ? (
            <div className="investigation-library-empty">
              <FileSearch size={24} />
              <p>Your saved questions will live here.</p>
              <button className="button" onClick={() => setCreating(true)}>
                <Plus size={14} />
                New investigation
              </button>
            </div>
          ) : (
            library.data.map((entry) => (
              <button
                key={entry.id}
                className={`investigation-library-item ${selected === entry.id ? 'selected' : ''}`}
                onClick={() => navigate(entry.id)}
              >
                <span>
                  <strong>{entry.title}</strong>
                  <small>
                    {entry.context.symbol} · {entry.context.timeframe}
                  </small>
                </span>
                {entry.runs[0] ? (
                  <Badge tone={entry.runs[0].status === 'completed' ? 'lime' : 'neutral'}>
                    {running(entry.runs[0]) && <LoaderCircle size={10} className="spin" />}
                    {runLabel(entry.runs[0].status)}
                  </Badge>
                ) : (
                  <Badge>Saved</Badge>
                )}
              </button>
            ))
          )}
        </aside>
        <section className="investigation-reading" aria-label="Investigation report">
          {!selected ? (
            <div className="investigation-welcome">
              <span className="investigation-welcome-icon">
                <FileSearch size={32} />
              </span>
              <span className="sibyl-eyebrow">A question. More perspective.</span>
              <h2>Bring the evidence together.</h2>
              <p>
                Let Sibyl connect specialist insights into a report you can revisit, compare and
                build on.
              </p>
              <button className="button primary" onClick={() => setCreating(true)}>
                <Plus size={15} />
                New investigation
              </button>
              <div className="investigation-welcome-details">
                <span>Sources you can inspect</span>
                <span>Every rerun, a new version</span>
                <span>Your research stays local</span>
              </div>
            </div>
          ) : definition.error ? (
            <ErrorState message={definition.error} retry={definition.retry} />
          ) : !item ? (
            <Loading />
          ) : (
            <>
              <header className="investigation-heading">
                <div>
                  <span className="sibyl-eyebrow">Saved investigation</span>
                  <h2>{item.title}</h2>
                  <p>{item.question}</p>
                </div>
                <button
                  className="icon-button"
                  disabled={!!active || !!busy}
                  aria-label="Delete investigation"
                  onClick={() => setDeleting(true)}
                >
                  <Trash2 size={15} />
                </button>
              </header>
              <Briefings
                key={item.id}
                investigation={item.id}
                ready={ready}
                onChanged={refreshReports}
                onStarted={(identity) => {
                  navigate(item.id, identity);
                  setFollowing(true);
                  refreshReports();
                }}
              />
              <div className="investigation-toolbar">
                <div>
                  {item.runs.length > 0 && (
                    <label className="investigation-version-label">
                      Report
                      <select
                        aria-label="Report version"
                        value={runId ?? ''}
                        onChange={(event) => navigate(selected, event.target.value)}
                      >
                        {item.runs.map((version) => (
                          <option key={version.id} value={version.id}>
                            Version {version.version} · {runLabel(version.status)}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  {item.runs.filter(
                    (version) => version.status === 'completed' && version.id !== runId,
                  ).length > 0 && (
                    <label className="investigation-version-label">
                      <ArrowLeftRight size={13} />
                      <select
                        aria-label="Compare with report version"
                        value={comparison}
                        onChange={(event) => setComparison(event.target.value)}
                      >
                        <option value="">Compare versions</option>
                        {item.runs
                          .filter(
                            (version) => version.status === 'completed' && version.id !== runId,
                          )
                          .map((version) => (
                            <option key={version.id} value={version.id}>
                              Compare with version {version.version}
                            </option>
                          ))}
                      </select>
                    </label>
                  )}
                </div>
                <div>
                  {run?.report && (
                    <button className="button" onClick={() => void download()} disabled={!!busy}>
                      <Download size={14} />
                      Export
                    </button>
                  )}
                  {active ? (
                    <button className="button" onClick={() => void stop()} disabled={!!busy}>
                      <Square size={12} />
                      {busy === 'stop' ? 'Stopping…' : 'Stop'}
                    </button>
                  ) : (
                    <button
                      className="button primary"
                      disabled={!ready || !!busy || item.runs.length >= 50}
                      onClick={() => void start(selected)}
                    >
                      {busy === 'run' ? (
                        <LoaderCircle size={14} className="spin" />
                      ) : (
                        <RotateCcw size={14} />
                      )}
                      {item.runs.length ? 'Rerun investigation' : 'Investigate'}
                    </button>
                  )}
                </div>
              </div>
              {active && (
                <SibylProgress
                  activity={running(run) ? run?.activity : undefined}
                  stopping={busy === 'stop'}
                />
              )}
              {!item.runs.length ? (
                <Empty title="Your question is saved">
                  Start an investigation to bring the relevant specialists and their evidence
                  together.
                </Empty>
              ) : result.error ? (
                <ErrorState message={result.error} retry={result.retry} />
              ) : !run ? (
                <Loading />
              ) : (
                <>
                  <div className="investigation-context-strip">
                    <span>
                      {run.context.symbol} · {run.context.timeframe}
                    </span>
                    <span>Market: {run.context.market_source}</span>
                    <span>
                      News:{' '}
                      {run.context.news_mode === 'demo' ? 'Demo · synthetic' : 'Publisher archive'}
                    </span>
                    {run.context.market_source === 'demo' && (
                      <Badge tone="demo">Demo market data</Badge>
                    )}
                    {run.session_id && (
                      <Link to={`/sibyl?chat=${run.session_id}`}>
                        Open conversation
                        <ArrowUpRight size={12} />
                      </Link>
                    )}
                  </div>
                  {run.error && (
                    <p className="inline-alert" role="alert">
                      {run.error}
                    </p>
                  )}
                  {!run.report && !running(run) && (
                    <Empty title={runLabel(run.status)}>
                      No completed report was saved. Previous versions remain available; rerun
                      explicitly when you’re ready.
                    </Empty>
                  )}
                  <div className={`investigation-comparison ${comparison ? 'comparing' : ''}`}>
                    <div>
                      {run.report && <InvestigationReport run={run} />}
                      {!run.report && !!run.sources?.length && (
                        <details className="investigation-partial-evidence">
                          <summary>{run.sources.length} completed tool observations</summary>
                          {run.sources.map((source) => (
                            <section key={source.id}>
                              <strong>{source.key}</strong>
                              <pre>{source.preview}</pre>
                            </section>
                          ))}
                        </details>
                      )}
                    </div>
                    {comparison && (
                      <div>
                        {compared.error ? (
                          <ErrorState message={compared.error} retry={compared.retry} />
                        ) : compared.data?.id === comparison ? (
                          <InvestigationReport run={compared.data} compact />
                        ) : (
                          <Loading />
                        )}
                      </div>
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
