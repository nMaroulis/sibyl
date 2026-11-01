import type { SibylActivity } from '../sibyl-activity';

export type ResearchContext = {
  symbol: string;
  timeframe: string;
  market_source: string;
  portfolio_scope: string;
  news_mode: '' | 'live' | 'demo';
};
export type ResearchReport = {
  summary: string;
  findings: { title: string; detail: string; sources: string[] }[];
  uncertainties: string[];
  next_questions: string[];
};
export type ResearchSource = {
  id: string;
  key: string;
  agent_id: string;
  tool: string;
  retrieved_at: string;
  links: string[];
  fingerprint: string;
  preview: string;
  truncated: boolean;
};
export type ResearchRun = {
  id: string;
  investigation_id: string;
  version: number;
  status: string;
  created_at: string;
  finished_at: string | null;
  session_id: string | null;
  native_run_id: string | null;
  question: string;
  context: ResearchContext;
  models: Record<string, { provider: string; model: string; selection: string }>;
  report?: ResearchReport | null;
  sources?: ResearchSource[];
  activity?: SibylActivity | null;
  error: string | null;
};
export type Investigation = {
  id: string;
  title: string;
  question: string;
  context: ResearchContext;
  created_at: string;
  runs: ResearchRun[];
};
export const running = (run?: ResearchRun) =>
  Boolean(run && ['queued', 'running', 'cancelling'].includes(run.status));
export const runLabel = (status: string) =>
  ({
    queued: 'Queued',
    running: 'Researching',
    cancelling: 'Stopping',
    completed: 'Ready',
    cancelled: 'Stopped',
    interrupted: 'Interrupted',
    failed: 'Needs attention',
  })[status] ?? status;
