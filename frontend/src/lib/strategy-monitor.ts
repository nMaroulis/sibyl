import type { Job, Strategy } from './types';
import { number } from './api';

export const monitorURL = (id?: string) =>
  `/strategies?view=monitor${id ? `&job=${encodeURIComponent(id)}` : ''}`;
export const runName = (job: Job, catalog: Strategy[]) =>
  catalog.find((item) => item.id === job.parameters.strategy)?.name ?? job.parameters.strategy;
export const date = (value?: string | null) => (value ? new Date(value).toLocaleString() : '—');
export const formatted = (value: number | null | undefined, digits = 2) =>
  value == null ? '—' : number(value, digits);
export const tone = (status: string) =>
  status === 'running' ? 'lime' : status === 'stopped' ? 'rose' : 'neutral';
