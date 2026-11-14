import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, RefreshCw, ShieldCheck, X } from 'lucide-react';
import { api, downloadFile, number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { SemanticStatus } from '../lib/semantic-types';
import { Badge, Panel, useToast } from './ui';
import { AgentButton } from './agents';
import './library-calibration.css';

type Scope = 'all' | 'document' | 'news';
type Partition = 'fit' | 'validation';
type Counts = {
  questions: number;
  answerable: number;
  no_source: number;
  accepted: number;
  correct_accepts: number;
  incorrect_accepts: number;
  accepted_no_source: number;
  missed_answerable: number;
  precision: number | null;
  answerable_coverage: number | null;
};
type Policy = {
  kind: Scope;
  revision: number;
  enabled: boolean;
  state: string;
  report_id: string | null;
};
type Run = {
  id: string;
  title: string;
  kind: Scope;
  state: string;
  completed: number;
  total: number;
  error: string | null;
  snapshot_current?: boolean;
  snapshot: { corpus: string; passages: number; model?: string };
  calibration: {
    threshold: number;
    eligible: boolean;
    fit: Counts;
    validation: Counts;
    note: string;
  } | null;
  results?: {
    query: string;
    partition: Partition;
    expected: string[];
    passage_id: string | null;
    similarity: number | null;
    citation: { url: string; text: string; source?: { title: string } } | null;
  }[];
};
type Catalog = { reports: Run[]; policies: Record<Scope, Policy>; note: string };
type Draft = { query: string; partition: Partition; expected: string; noSource: boolean };
const base = '/library/calibrations';
const initial = (): Draft[] =>
  (['fit', 'validation'] as Partition[]).flatMap((partition) =>
    Array.from({ length: 4 }, (_, i) => ({ query: '', partition, expected: '', noSource: i > 1 })),
  );
const active = (run?: Run) => !!run && ['queued', 'running'].includes(run.state);

/** Explicit human labels, an untouched validation partition and separately reviewed activation. */
export function LibraryCalibration({ semantic }: { semantic?: SemanticStatus }) {
  const [open, setOpen] = useState(false);
  const catalog = useResource<Catalog>(base, 0, open);
  const [kind, setKind] = useState<Scope>('document');
  const coverage = semantic?.coverage[kind];
  const semanticReady = !!semantic?.configured && !!coverage?.total && !coverage.partial;
  const [runId, setRunId] = useState('');
  const [poll, setPoll] = useState(1500);
  const report = useResource<Run>(`${base}/${runId}`, poll, open && !!runId);
  const run = report.data;
  const [partition, setPartition] = useState<Partition>('fit');
  const [title, setTitle] = useState('My semantic cutoff');
  const [cases, setCases] = useState<Draft[]>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [remove, setRemove] = useState(false);
  const toast = useToast();
  const policy = catalog.data?.policies[kind];
  const current = catalog.data?.reports.find((row) => row.id === runId)?.snapshot_current;
  const ready =
    !!title.trim() &&
    new Set(cases.map((c) => c.query.trim().toLowerCase())).size === cases.length &&
    cases.every((c) => c.query.trim() && (c.noSource || c.expected.trim())) &&
    (['fit', 'validation'] as Partition[]).every(
      (p) =>
        cases.filter((c) => c.partition === p && c.noSource).length >= 2 &&
        cases.filter((c) => c.partition === p && !c.noSource).length >= 2,
    );
  useEffect(() => {
    setPoll(active(run) ? 1500 : 0);
    if (run) catalog.retry();
  }, [run?.id, run?.state, catalog.retry]);
  const perform = async (action: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try {
      await action();
      catalog.retry();
      report.retry();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const edit = (index: number, patch: Partial<Draft>) =>
    setCases((old) => old.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  const updatePolicy = (enabled: boolean) =>
    void perform(async () => {
      await post(`/library/calibration-policy/${kind}`, {
        revision: policy?.revision ?? 0,
        enabled,
        report_id: enabled ? run?.id : null,
      });
      refresh();
      toast(
        enabled
          ? 'Semantic cutoff enabled for this source scope.'
          : 'Semantic cutoff disabled. Raw rankings are available again.',
      );
    });
  return (
    <Panel className="full-panel library-calibration">
      <details onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary>
          <ShieldCheck size={18} />
          <strong>Know when search should abstain</strong>
          <Badge>Optional · advanced</Badge>
        </summary>
        <p>
          Fit a semantic similarity cutoff with your own questions, then check it on separate
          questions. An active cutoff releases only the leading passage, or says there is not enough
          evidence.
        </p>
        <div className="calibration-toolbar">
          <label>
            Source scope
            <select
              aria-label="Calibration source scope"
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as Scope);
                setRunId('');
                setRemove(false);
              }}
            >
              <option value="document">My documents</option>
              <option value="news">Retained news</option>
              <option value="all">All sources</option>
            </select>
          </label>
          <div className="calibration-policy">
            <Badge tone={policy?.state === 'active' ? 'lime' : 'neutral'}>
              {policy?.state ?? 'Not loaded'}
            </Badge>
            <span>Semantic only · this exact source scope</span>
            <span>
              {policy?.state === 'stale'
                ? 'Recheck source/index changes'
                : `${coverage?.indexed ?? 0}/${coverage?.total ?? 0} passages indexed${!semanticReady ? ' · complete this index first' : ''}`}
            </span>
            {policy?.enabled && (
              <button className="text-button" disabled={busy} onClick={() => updatePolicy(false)}>
                Disable cutoff
              </button>
            )}
          </div>
          <button className="text-button" onClick={catalog.retry}>
            <RefreshCw size={13} /> Recheck index
          </button>
        </div>
        {policy?.state === 'stale' && (
          <p className="inline-alert">
            The bound corpus or index changed. Semantic results in this scope are withheld until you
            calibrate again or explicitly disable the cutoff.
          </p>
        )}
        <p className="footnote">
          Keyword and hybrid search remain uncalibrated. Other source scopes have separate settings.
          A cutoff measures retrieval on your labels; it is not answer confidence, source
          verification or a guarantee.
        </p>
        <label className="calibration-reports">
          Saved experiment
          <select
            aria-label="Saved calibration"
            value={runId}
            onChange={(e) => {
              setRunId(e.target.value);
              setPoll(1500);
              setRemove(false);
            }}
          >
            <option value="">Choose an experiment</option>
            {catalog.data?.reports
              .filter((r) => r.kind === kind)
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title} · {r.state}
                  {r.snapshot_current === false ? ' · stale' : ''} · {r.id.slice(0, 8)}
                </option>
              ))}
          </select>
        </label>
        <details className="calibration-editor">
          <summary>Create a calibration experiment</summary>
          <label>
            Experiment title
            <input value={title} maxLength={100} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <p className="footnote">
            Each partition needs at least two questions with relevant passage IDs and two for which
            no relevant passage exists. Open a source below and use Copy passage ID. Use distinct,
            representative questions—including difficult no-source questions. Do not tune the cutoff
            or rewrite labels after inspecting validation; use fresh validation questions for a new
            experiment.
          </p>
          <div className="calibration-partitions" role="group" aria-label="Question partition">
            {(['fit', 'validation'] as Partition[]).map((p) => (
              <button
                key={p}
                className={partition === p ? 'is-active' : ''}
                aria-pressed={partition === p}
                onClick={() => setPartition(p)}
              >
                {p === 'fit' ? '1. Fit questions' : '2. Held-out validation'}
                <span>{cases.filter((c) => c.partition === p).length} questions</span>
              </button>
            ))}
          </div>
          {cases.map(
            (row, index) =>
              row.partition === partition && (
                <div className="calibration-question" key={index}>
                  <label>
                    Question {index + 1}
                    <input
                      aria-label={`Calibration question ${index + 1}`}
                      value={row.query}
                      maxLength={300}
                      onChange={(e) => edit(index, { query: e.target.value })}
                    />
                  </label>
                  <label className="calibration-no-source">
                    <input
                      type="checkbox"
                      checked={row.noSource}
                      onChange={(e) => edit(index, { noSource: e.target.checked })}
                    />{' '}
                    No relevant source exists in this scope
                  </label>
                  {!row.noSource && (
                    <label>
                      Relevant passage IDs
                      <textarea
                        rows={2}
                        value={row.expected}
                        placeholder="Paste IDs, separated by commas or newlines"
                        onChange={(e) => edit(index, { expected: e.target.value })}
                      />
                    </label>
                  )}
                  {cases.filter((c) => c.partition === partition).length > 4 && (
                    <button
                      className="text-button"
                      onClick={() => setCases((old) => old.filter((_, i) => i !== index))}
                    >
                      <X size={12} /> Remove question
                    </button>
                  )}
                </div>
              ),
          )}
          <div className="workspace-actions">
            {cases.length < 32 && (
              <button
                className="text-button"
                onClick={() =>
                  setCases((old) => [
                    ...old,
                    { query: '', expected: '', noSource: false, partition },
                  ])
                }
              >
                <Plus size={13} /> Add question
              </button>
            )}
            <button
              className="button secondary tiny"
              disabled={busy || !semanticReady || !ready || active(run)}
              onClick={() =>
                void perform(async () => {
                  const result = await post<Run>(base, {
                    title,
                    kind,
                    cases: cases.map((c) => ({
                      query: c.query,
                      partition: c.partition,
                      expected: c.noSource
                        ? []
                        : c.expected
                            .split(/[,\n]/)
                            .map((v) => v.trim())
                            .filter(Boolean),
                    })),
                  });
                  setRunId(result.id);
                  setPoll(1500);
                  toast(
                    'Calibration queued. The cutoff stays disabled until you review and enable it.',
                  );
                })
              }
            >
              Embed {cases.length} questions &amp; fit cutoff
            </button>
          </div>
          <p className="footnote">
            A complete semantic index for this scope is required. Each query uses your selected
            embedding provider. Hosted queries are sent under saved permission and may incur
            charges. Stop prevents future queries; it cannot undo queries already sent.
          </p>
        </details>
        {(error || catalog.error || report.error) && (
          <p className="form-error" role="alert">
            {error || catalog.error || report.error}
          </p>
        )}
        {run && (
          <section className="calibration-report" aria-label="Calibration results">
            <header>
              <Badge tone={run.state === 'completed' ? 'lime' : 'neutral'}>{run.state}</Badge>
              <strong>{run.title}</strong>
              <AgentButton module="wiki" context={{ retrieval_calibration_id: run.id }} />
              <span>
                {run.completed}/{run.total} questions
              </span>
            </header>
            {run.error && <p className="inline-alert">{run.error}</p>}
            <p className="footnote">
              {run.snapshot.passages} passages · {run.snapshot.model} · corpus{' '}
              {run.snapshot.corpus.slice(0, 12)}…
              {current === false && ' · changed since this experiment'}
            </p>
            {run.calibration && (
              <>
                <div className="calibration-statistics">
                  <div>
                    <span>Cosine cutoff</span>
                    <strong title={String(run.calibration.threshold)}>
                      {run.calibration.threshold.toPrecision(6)}
                    </strong>
                  </div>
                  <div>
                    <span>Validation relevant matches</span>
                    <strong>
                      {run.calibration.validation.correct_accepts}/
                      {run.calibration.validation.answerable}
                    </strong>
                  </div>
                  <div>
                    <span>Validation incorrect accepts</span>
                    <strong>
                      {run.calibration.validation.incorrect_accepts}/
                      {run.calibration.validation.questions}
                    </strong>
                  </div>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Questions</th>
                        <th>Relevant / no-source</th>
                        <th>Correct accepts</th>
                        <th>Incorrect accepts</th>
                        <th>Relevant coverage</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(['fit', 'validation'] as Partition[]).map((p) => {
                        const m = run.calibration![p];
                        return (
                          <tr key={p}>
                            <td>{p === 'fit' ? 'Fit' : 'Held-out validation'}</td>
                            <td>
                              {m.answerable} / {m.no_source}
                            </td>
                            <td>{m.correct_accepts}</td>
                            <td>{m.incorrect_accepts}</td>
                            <td>
                              {m.answerable_coverage == null
                                ? '—'
                                : `${number(m.answerable_coverage * 100)}%`}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <p className="footnote">
                  {run.calibration.note} Only the top passage can be released. Exact scores and
                  cutoff are in the export.
                </p>
                {!run.calibration.eligible && (
                  <p className="inline-alert">
                    This cutoff cannot be enabled: fit and validation both need relevant matches,
                    and validation must have zero observed incorrect accepts. Inspect the evidence
                    rather than tuning to the same validation set.
                  </p>
                )}
                <button
                  className="button secondary tiny"
                  disabled={
                    busy ||
                    !run.calibration.eligible ||
                    current === false ||
                    !policy ||
                    (policy.enabled && policy.report_id === run.id)
                  }
                  onClick={() => updatePolicy(true)}
                >
                  {policy?.enabled && policy.report_id === run.id
                    ? policy.state === 'stale'
                      ? 'Enabled cutoff is stale'
                      : 'This cutoff is enabled'
                    : 'Use this cutoff for semantic search'}
                </button>
                <details className="calibration-evidence">
                  <summary>Inspect actual scores and citations</summary>
                  {run.results?.map((row, i) => (
                    <div key={i} className="calibration-question">
                      <strong>{row.query}</strong>
                      <p>
                        {row.partition} ·{' '}
                        {row.expected.length
                          ? 'Relevant passage expected'
                          : 'No relevant source expected'}{' '}
                        · top cosine{' '}
                        {row.similarity == null ? 'unavailable' : row.similarity.toPrecision(8)}
                      </p>
                      {row.citation && (
                        <>
                          <Link to={row.citation.url}>
                            {row.citation.source?.title || row.passage_id}
                          </Link>
                          <p>{row.citation.text}</p>
                        </>
                      )}
                    </div>
                  ))}
                </details>
              </>
            )}
            <div className="workspace-actions">
              {active(run) && (
                <button
                  className="button secondary tiny"
                  disabled={busy}
                  onClick={() =>
                    void perform(async () => {
                      await post(`${base}/${run.id}/stop`);
                    })
                  }
                >
                  Stop experiment
                </button>
              )}
              <button
                className="text-button"
                onClick={() =>
                  void perform(async () => {
                    await downloadFile(
                      `${base}/${run.id}`,
                      `sibyl-search-calibration-${run.id}.json`,
                    );
                  })
                }
              >
                Export evidence
              </button>
              {!active(run) && (
                <button
                  className="text-button"
                  disabled={busy || (policy?.enabled && policy.report_id === run.id)}
                  onClick={() => {
                    if (!remove) {
                      setRemove(true);
                      return;
                    }
                    void perform(async () => {
                      await api(`${base}/${run.id}`, { method: 'DELETE' });
                      setRunId('');
                      setRemove(false);
                    });
                  }}
                >
                  {remove ? 'Confirm delete experiment' : 'Delete experiment'}
                </button>
              )}
              {remove && (
                <button className="text-button" onClick={() => setRemove(false)}>
                  Keep experiment
                </button>
              )}
            </div>
          </section>
        )}
      </details>
    </Panel>
  );
}
