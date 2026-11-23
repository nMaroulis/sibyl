import { useState } from 'react';
import { Link } from 'react-router-dom';
import { FlaskConical, Plus, X } from 'lucide-react';
import { AgentButton } from './agents';
import { Badge, Panel, useToast } from './ui';
import { api, downloadFile, number, post } from '../lib/api';
import { useResource } from '../lib/hooks';

type Method = 'keyword' | 'semantic' | 'hybrid';
type Judgment = { query: string; expected: string[] };
type Suite = { id: string; title: string; kind: string; cases: Judgment[] };
type Metrics = {
  precision: number;
  recall: number;
  reciprocal_rank: number;
  ndcg: number;
  hit: number;
  mean_milliseconds?: number;
};
type Run = {
  id: string;
  suite_id: string;
  title: string;
  state: string;
  completed: number;
  total: number;
  k: number;
  error: string | null;
  note: string;
  summary: Record<string, Metrics>;
  snapshot: { corpus: string; passages: number; model?: string };
  coverage?: { indexed: number; total: number; partial: boolean };
  results: {
    method: Method;
    case: number;
    query: string;
    metrics: Metrics;
    milliseconds: number;
    items: { id: string; url: string; text: string; source?: { title: string } }[];
  }[];
};
const base = '/library/evaluations';
const active = (run?: Run) => !!run && ['queued', 'running'].includes(run.state);

/** Explicit human judgments and retained rankings; no inferred ground truth or confidence scores. */
export function LibraryEvaluations({ semanticReady }: { semanticReady: boolean }) {
  const [open, setOpen] = useState(false);
  const catalog = useResource<{ suites: Suite[]; runs: Run[] }>(base, 2500, open);
  const [suiteId, setSuiteId] = useState('');
  const [runId, setRunId] = useState('');
  const report = useResource<Run>(`${base}/runs/${runId}`, 1500, open && !!runId);
  const [title, setTitle] = useState('My retrieval benchmark');
  const [kind, setKind] = useState('all');
  const [cases, setCases] = useState([{ query: '', expected: '' }]);
  const [methods, setMethods] = useState<Method[]>(['keyword']);
  const [k, setK] = useState(5);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
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
  const run = report.data;
  return (
    <Panel className="full-panel">
      <details className="research-evaluation" onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary>
          <FlaskConical size={18} />
          <strong>Retrieval quality lab</strong>
          <Badge>Advanced research</Badge>
        </summary>
        <p>
          Compare search methods against passages you judge relevant. These scores measure retrieval
          on your questions; they do not verify answers or calibrate confidence.
        </p>
        <div className="form-row">
          <label>
            Evaluation suite
            <select
              value={suiteId}
              onChange={(e) => {
                setSuiteId(e.target.value);
                setConfirmDelete(false);
              }}
            >
              <option value="">Create a suite</option>
              {catalog.data?.suites.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title} · {s.cases.length} questions
                </option>
              ))}
            </select>
          </label>
          <label>
            Saved evaluation
            <select value={runId} onChange={(e) => setRunId(e.target.value)}>
              <option value="">Choose a report</option>
              {catalog.data?.runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title} · {r.state} · {r.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
        </div>
        {!suiteId && (
          <div className="evaluation-setup">
            <div className="form-row">
              <label>
                Suite title
                <input value={title} maxLength={100} onChange={(e) => setTitle(e.target.value)} />
              </label>
              <label>
                Source type
                <select value={kind} onChange={(e) => setKind(e.target.value)}>
                  <option value="all">All retained sources</option>
                  <option value="document">Uploaded documents</option>
                  <option value="news">Retained news</option>
                </select>
              </label>
            </div>
            <p className="footnote">
              Open a source below and copy its passage ID. Label every passage you consider
              relevant. Use representative questions, including paraphrases; incomplete judgments
              can penalize useful matches.
            </p>
            {cases.map((row, index) => (
              <div className="evaluation-case" key={index}>
                <div className="form-row">
                  <label>
                    Question {index + 1}
                    <input
                      value={row.query}
                      maxLength={300}
                      onChange={(e) =>
                        setCases((old) =>
                          old.map((c, i) => (i === index ? { ...c, query: e.target.value } : c)),
                        )
                      }
                    />
                  </label>
                  <label>
                    Relevant passage IDs {index + 1}
                    <textarea
                      rows={2}
                      value={row.expected}
                      placeholder="Paste IDs, separated by commas or newlines"
                      onChange={(e) =>
                        setCases((old) =>
                          old.map((c, i) => (i === index ? { ...c, expected: e.target.value } : c)),
                        )
                      }
                    />
                  </label>
                </div>
                {cases.length > 1 && (
                  <button
                    className="text-button"
                    onClick={() => setCases((old) => old.filter((_, i) => i !== index))}
                  >
                    <X size={13} /> Remove question {index + 1}
                  </button>
                )}
              </div>
            ))}
            <div className="workspace-actions">
              {cases.length < 8 && (
                <button
                  className="text-button"
                  onClick={() => setCases((old) => [...old, { query: '', expected: '' }])}
                >
                  <Plus size={14} /> Add question
                </button>
              )}
              <button
                className="button secondary tiny"
                disabled={busy}
                onClick={() =>
                  void perform(async () => {
                    const saved = await post<Suite>(`${base}/suites`, {
                      title,
                      kind,
                      cases: cases.map((c) => ({
                        query: c.query,
                        expected: c.expected
                          .split(/[,\n]/)
                          .map((v) => v.trim())
                          .filter(Boolean),
                      })),
                    });
                    setSuiteId(saved.id);
                    toast('Judgments saved with exact passage evidence.');
                  })
                }
              >
                Save judgments
              </button>
            </div>
          </div>
        )}
        {suiteId && (
          <>
            <div className="evaluation-methods">
              {(['keyword', 'semantic', 'hybrid'] as Method[]).map((method) => (
                <label key={method}>
                  <input
                    type="checkbox"
                    checked={methods.includes(method)}
                    disabled={method !== 'keyword' && !semanticReady && !methods.includes(method)}
                    onChange={(e) =>
                      setMethods((old) =>
                        e.target.checked ? [...old, method] : old.filter((m) => m !== method),
                      )
                    }
                  />
                  {method === 'keyword' ? 'Keyword' : method === 'semantic' ? 'Semantic' : 'Hybrid'}
                </label>
              ))}
              <label>
                Cutoff
                <select value={k} onChange={(e) => setK(Number(e.target.value))}>
                  {[1, 3, 5, 10].map((n) => (
                    <option key={n} value={n}>
                      Top {n}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {!semanticReady && (
              <p className="footnote">
                Keyword search needs no model. Configure and index an embedding model above to
                compare semantic methods.
              </p>
            )}
            <div className="workspace-actions">
              <button
                className="button secondary tiny"
                disabled={busy || !methods.length || active(run)}
                onClick={() =>
                  void perform(async () => {
                    const result = await post<Run>(`${base}/suites/${suiteId}/runs`, {
                      methods,
                      k,
                    });
                    setRunId(result.id);
                  })
                }
              >
                Run comparison
              </button>
              <button
                className="text-button"
                disabled={busy || active(run)}
                onClick={() => {
                  if (!confirmDelete) {
                    setConfirmDelete(true);
                    return;
                  }
                  void perform(async () => {
                    await api(`${base}/suites/${suiteId}`, { method: 'DELETE' });
                    setSuiteId('');
                    setRunId('');
                    setConfirmDelete(false);
                    toast('Suite and its evaluation reports removed.');
                  });
                }}
              >
                {confirmDelete ? 'Confirm permanent removal' : 'Delete suite & reports'}
              </button>
            </div>
          </>
        )}
        {confirmDelete && (
          <p className="inline-alert">
            This permanently removes the selected suite and all its evaluation reports. Sources stay
            in the library.{' '}
            <button className="text-button" onClick={() => setConfirmDelete(false)}>
              Keep suite
            </button>
          </p>
        )}
        {(error || catalog.error || report.error) && (
          <p className="form-error" role="alert">
            {error || catalog.error || report.error}
          </p>
        )}
        {run && (
          <section className="evaluation-report" aria-label="Retrieval evaluation results">
            <header>
              <Badge tone={run.state === 'completed' ? 'lime' : 'neutral'}>{run.state}</Badge>
              <strong>{run.title}</strong>
              <span>
                {run.completed}/{run.total} queries · top {run.k}
              </span>
              <AgentButton module="wiki" context={{ retrieval_evaluation_id: run.id }} />
            </header>
            {run.error && <p className="inline-alert">{run.error}</p>}
            <p className="footnote">
              {run.snapshot.passages} retained passages · corpus {run.snapshot.corpus.slice(0, 12)}…{' '}
              {run.snapshot.model && `· ${run.snapshot.model}`}
              {run.coverage?.partial &&
                ` · Partial semantic index: ${run.coverage.indexed}/${run.coverage.total}`}
            </p>
            {Object.keys(run.summary).length > 0 && (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Method</th>
                      <th>Precision@{run.k}</th>
                      <th>Recall@{run.k}</th>
                      <th>MRR@{run.k}</th>
                      <th>nDCG@{run.k}</th>
                      <th>Hit rate</th>
                      <th>Mean latency</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(run.summary).map(([method, m]) => (
                      <tr key={method}>
                        <td>{method}</td>
                        <td>{number(m.precision * 100)}%</td>
                        <td>{number(m.recall * 100)}%</td>
                        <td>{number(m.reciprocal_rank, 3)}</td>
                        <td>{number(m.ndcg, 3)}</td>
                        <td>{number(m.hit * 100)}%</td>
                        <td>{number(m.mean_milliseconds ?? 0)} ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="footnote">
              Precision divides by the requested cutoff, recall by all labeled passages. Means
              weight questions equally. Empty results score zero; partial runs have no aggregate
              comparison.
            </p>
            <details>
              <summary>Inspect query rankings and citations</summary>
              <p className="footnote">{run.note}</p>
              {run.results.map((result, i) => (
                <div className="evaluation-case" key={i}>
                  <strong>
                    {result.query} · {result.method}
                  </strong>
                  <p>
                    Recall {number(result.metrics.recall * 100)}% · reciprocal rank{' '}
                    {number(result.metrics.reciprocal_rank, 3)} · {number(result.milliseconds)} ms
                  </p>
                  {result.items.length ? (
                    <ol>
                      {result.items.map((item) => (
                        <li key={item.id}>
                          <Link to={item.url}>{item.source?.title || item.id}</Link>
                          <p>{item.text}</p>
                          <code>{item.id}</code>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p>No matches.</p>
                  )}
                </div>
              ))}
            </details>
            <div className="workspace-actions">
              {active(run) && (
                <button
                  className="button secondary tiny"
                  disabled={busy}
                  onClick={() =>
                    void perform(async () => {
                      await post(`${base}/runs/${run.id}/stop`);
                    })
                  }
                >
                  Stop evaluation
                </button>
              )}
              <button
                className="text-button"
                onClick={() =>
                  void perform(async () => {
                    await downloadFile(`${base}/runs/${run.id}`, `sibyl-retrieval-${run.id}.json`);
                  })
                }
              >
                Export evidence
              </button>
            </div>
          </section>
        )}
      </details>
    </Panel>
  );
}
