import { useState } from 'react';
import { Badge, ErrorState, Loading } from '../ui';
import { useResource } from '../../lib/hooks';

type Incident = {
  id: string;
  worker_id: string;
  state: 'active' | 'recovered' | 'observation_ended';
  first_detected_at: string;
  last_observed_at: string;
  evidence: {
    first_phase: string;
    last_phase: string;
    observations: number;
    first: { iterations: number | null };
    last: { iterations: number | null; elapsed_seconds: number | null };
  };
};
type Incidents = {
  observer: {
    status: string;
    last_sample_at: string | null;
    failed_samples: number;
    sample_age_seconds: number | null;
  };
  items: Incident[];
  total: number;
  offset: number;
  limit: number;
  gaps: { detected_at: string; seconds: number }[];
  scope: string;
};

/** Read persisted local incidents; browser visits never create samples or imply recovery. */
export function WorkerIncidents() {
  const [offset, setOffset] = useState(0);
  const resource = useResource<Incidents>(`/workspace/incidents?offset=${offset}`, 5000);
  const data = resource.data;
  return (
    <details className="worker-incidents">
      <summary>
        Retained worker incidents <span>{data?.total ?? 0}</span>
      </summary>
      {resource.error ? (
        <ErrorState message={resource.error} retry={resource.retry} />
      ) : resource.loading ? (
        <Loading />
      ) : (
        data && (
          <>
            <p className="footnote">
              Observer · {data.observer.status}
              {data.observer.last_sample_at &&
                ` · Last actual sample ${new Date(data.observer.last_sample_at).toLocaleTimeString()}`}
              {data.observer.failed_samples > 0 &&
                ` · ${data.observer.failed_samples} failed samples`}
            </p>
            {data.items.length ? (
              <div className="worker-incident-list">
                {data.items.map((item) => (
                  <article key={item.id}>
                    <div>
                      <strong>{item.worker_id.replaceAll('-', ' ')}</strong>
                      <small>
                        First detected {new Date(item.first_detected_at).toLocaleString()}
                      </small>
                      <small>
                        Last observed {new Date(item.last_observed_at).toLocaleString()} ·{' '}
                        {item.evidence.last_phase} · {item.evidence.observations} issue samples
                      </small>
                    </div>
                    <Badge
                      tone={
                        item.state === 'active'
                          ? 'rose'
                          : item.state === 'recovered'
                            ? 'sage'
                            : 'neutral'
                      }
                    >
                      {item.state === 'observation_ended'
                        ? 'Recovery unknown'
                        : item.state === 'recovered'
                          ? 'Progress resumed'
                          : 'Needs attention'}
                    </Badge>
                  </article>
                ))}
              </div>
            ) : (
              <p className="footnote">
                No worker incidents have been observed. This does not verify provider readiness.
              </p>
            )}
            {data.total > data.limit && (
              <div className="alert-pagination">
                <button
                  className="text-button"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - data.limit))}
                >
                  Previous
                </button>
                <small>
                  {offset + 1}–{Math.min(data.total, offset + data.limit)} of {data.total}
                </small>
                <button
                  className="text-button"
                  disabled={offset + data.limit >= data.total}
                  onClick={() => setOffset(offset + data.limit)}
                >
                  Next
                </button>
              </div>
            )}
            {data.gaps.length > 0 && (
              <details>
                <summary>{data.gaps.length} recent observation gaps</summary>
                {data.gaps.map((gap) => (
                  <p className="footnote" key={gap.detected_at}>
                    {new Date(gap.detected_at).toLocaleString()} · {Math.round(gap.seconds)} seconds
                    between actual samples · prior interval unobserved
                  </p>
                ))}
              </details>
            )}
            <p className="footnote">{data.scope}</p>
          </>
        )
      )}
    </details>
  );
}
