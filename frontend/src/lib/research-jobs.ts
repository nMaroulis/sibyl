import { post } from './api';

export type ResearchJobRun = {
  id: string;
  job_id: string;
  state: string;
  error: string | null;
  result: { report_id: string; kind: string; research_status?: string } | null;
};

/** Save one paused typed recipe, then explicitly queue its single idempotent run. */
export async function queueResearch(
  kind: 'strategy.adaptive' | 'strategy.plugin',
  label: string,
  args: unknown,
) {
  const job = await post<{ id: string }>('/workspace/jobs', { label, kind, arguments: args });
  return post<ResearchJobRun>(`/workspace/jobs/${job.id}/runs`, {
    request_id: crypto.randomUUID().replaceAll('-', ''),
  });
}
