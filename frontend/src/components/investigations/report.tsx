import { ArrowUpRight, ChevronDown, FileSearch, Link2, ShieldCheck } from 'lucide-react';
import { Badge } from '../ui';
import { AgentRunDetails } from '../agent-run';
import type { ResearchRun } from './types';

function preview(value: string, truncated: boolean) {
  if (truncated) return value;
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

/** Narrative is model interpretation; every source card comes from a retained native tool receipt. */
export function InvestigationReport({
  run,
  compact = false,
}: {
  run: ResearchRun;
  compact?: boolean;
}) {
  const data = run.report;
  if (!data) return null;
  return (
    <article className={`investigation-report ${compact ? 'compact' : ''}`}>
      <div className="investigation-report-meta">
        <Badge>Version {run.version}</Badge>
        {run.origin?.startsWith('schedule:') && <Badge>Scheduled</Badge>}
        {run.models.sibyl?.provider === 'mock' && <Badge tone="demo">Simulated model</Badge>}
        <span>{new Date(run.finished_at || run.created_at).toLocaleString()}</span>
      </div>
      <section className="investigation-summary">
        <span className="sibyl-eyebrow">The bigger picture</span>
        <p>{data.summary}</p>
      </section>
      {!run.sources?.length && (
        <p className="inline-alert">
          No tool observations were recorded. This report contains model interpretation without
          supporting source receipts.
        </p>
      )}
      <div className="investigation-findings">
        {data.findings.map((finding, index) => (
          <section key={index}>
            <span className="investigation-finding-number">
              {String(index + 1).padStart(2, '0')}
            </span>
            <div>
              <h3>{finding.title}</h3>
              <p>{finding.detail}</p>
              <div className="investigation-citations">
                {finding.sources.length ? (
                  finding.sources.map((key) => {
                    const source = run.sources?.find((item) => item.key === key);
                    return source ? (
                      <a key={key} href={`#source-${run.id}-${source.id}`}>
                        <Link2 size={11} />
                        {source.agent_id} · {source.tool.replaceAll('_', ' ')}
                      </a>
                    ) : null;
                  })
                ) : (
                  <small>No source cited for this interpretation</small>
                )}
              </div>
            </div>
          </section>
        ))}
      </div>
      {data.uncertainties.length > 0 && (
        <section className="investigation-limitations">
          <ShieldCheck size={17} />
          <div>
            <h3>What remains uncertain</h3>
            <ul>
              {data.uncertainties.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </div>
        </section>
      )}
      {data.next_questions.length > 0 && (
        <section className="investigation-next">
          <h3>Questions worth exploring</h3>
          {data.next_questions.map((question, index) => (
            <p key={index}>
              <ArrowUpRight size={13} />
              {question}
            </p>
          ))}
        </section>
      )}
      <details className="investigation-sources">
        <summary>
          <FileSearch size={16} />
          <span>
            Recorded evidence <small>{run.sources?.length ?? 0} observations</small>
          </span>
          <ChevronDown size={14} />
        </summary>
        <p className="footnote">
          Tool observations support the investigation; they do not independently verify every model
          interpretation. Retrieval time is separate from the observation dates inside each source.
        </p>
        {run.sources?.map((source) => (
          <section key={source.id} id={`source-${run.id}-${source.id}`}>
            <header>
              <strong>
                {source.agent_id} · {source.tool.replaceAll('_', ' ')}
              </strong>
              <small>Retrieved {new Date(source.retrieved_at).toLocaleString()}</small>
            </header>
            <div className="investigation-source-links">
              {source.links.map((url) => (
                <a
                  key={url}
                  href={url}
                  target={url.startsWith('/') ? undefined : '_blank'}
                  rel="noreferrer noopener"
                >
                  {url.startsWith('/') ? 'Open in Sibyl' : new URL(url).hostname}
                  <ArrowUpRight size={12} />
                </a>
              ))}
            </div>
            <details>
              <summary>Inspect observation {source.truncated ? '· bounded preview' : ''}</summary>
              <pre>{preview(source.preview, source.truncated)}</pre>
              <p className="footnote">SHA-256 · {source.fingerprint}</p>
            </details>
          </section>
        ))}
      </details>
      <AgentRunDetails runId={run.native_run_id ?? undefined} />
    </article>
  );
}
