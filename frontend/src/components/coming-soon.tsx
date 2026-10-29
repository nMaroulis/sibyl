import { Clock3, ArrowUpRight, ListChecks } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { Badge, PageTitle, Loading, ErrorState } from './ui';
import { SectionPanel, SectionTabs } from './section-tabs';
import { useResource } from '../lib/hooks';

/** Explicit feature boundaries, shared by each module and the workspace roadmap. */
export const futureFeatures: { module: string; title: string; text: string; deferred?: boolean }[] =
  [
    {
      module: 'sibyl',
      title: 'Sibyl beyond the dashboard',
      text: 'WhatsApp, Discord, Slack, Signal and Email clients, plus richer Telegram media and delivery controls. Telegram private text chats are available now in Settings → Messaging.',
    },
    {
      module: 'sibyl',
      title: 'Deeper investigations',
      text: 'Token-by-token answers, scheduled and resumable research, and evaluated collaboration. Per-agent models, live consultation progress, Stop and retained request outcomes are available now.',
    },
    {
      module: 'markets',
      title: 'Deeper relationships',
      text: 'Granger causality, distance correlation, MIC, regression, and SHAP explanations.',
    },
    {
      module: 'strategies',
      title: 'More ways to test an idea',
      text: 'Nested validation, broader search methods, Freqtrade integration and ML/RL strategies. Bounded parameter search and chronological walk-forward tests are available now.',
    },
    {
      module: 'strategies',
      title: 'More execution controls',
      text: 'Portfolio-wide exposure/daily-loss limits and more providers. A durable global submission halt, reviewed position exits, order expiry and Stop & cancel are available now; residual sells need fresh reviews and private venue acceptance remains pending.',
    },
    {
      module: 'trade',
      title: 'Advanced exchange orders',
      text: 'Stop, take-profit, trailing, OCO, cancel/replace, post-only, iceberg and additional time-in-force controls. Market and GTC limit orders with reviewed cancellation are available.',
    },
    {
      module: 'forecast',
      title: 'More forecasting models and evaluation',
      text: 'Neural/ARIMA models, rolling evaluation, automatic recalibration and calibrated drift monitoring. Versioned autoregressive ridge models, chronological evaluation, empirical bands and saved forecasts are available now.',
    },
    {
      module: 'knowledge',
      title: 'Your research library',
      text: 'Document ingestion, embeddings, hybrid RAG, citations, and optional web search. The current knowledge tool searches the curated glossary.',
    },
    {
      module: 'news',
      title: 'Deeper language analysis',
      text: 'Finance-trained sentiment models, entity-targeted analysis, and licensed full-article summaries. Today: publisher feeds, a website collector, optional NewsAPI access, and VADER headline/excerpt polarity.',
    },
    {
      module: 'stocks',
      title: 'Public portfolio archive',
      text: 'Senator portfolio aggregation, disclosure filters, and historical allocation views.',
    },
    {
      module: 'explorer',
      title: 'Beyond Bitcoin',
      text: 'Litecoin and additional chains, transaction inspection, and longer historical network datasets.',
    },
    {
      module: 'markets',
      title: 'Streaming markets',
      text: 'WebSocket streams, reviewed endpoint-weight budgets and richer operational metrics. Shared read limits, cooldowns, saved HTTP read history, source diagnostics, retained candles and saved datasets are available now.',
    },
    {
      module: 'alerts',
      title: 'More signals, more ways to hear',
      text: 'Broader risk metrics, silent-worker outage detection and optional external delivery. Value-floor, concentration and observed-value drawdown watches, price/crossing rules, strategy/connection alerts and the persistent in-app inbox are available now.',
    },
    {
      module: 'workspace',
      title: 'Hosted multi-user workspaces',
      deferred: true,
      text: 'Deferred for now: user accounts, permissions, tenant isolation and multiple-worker coordination. Sibyl remains focused on the local single-user workspace.',
    },
    {
      module: 'settings',
      title: 'More local model tools',
      text: 'Model downloads, quantization and additional runtime managers are planned. Ollama status, installed models and local start/stop controls are available in AI models.',
    },
  ];

export function ComingSoon({ module }: { module: string }) {
  return (
    <section className="future-section" aria-label="Upcoming features">
      <div className="future-heading">
        <span>
          <Clock3 size={14} /> On the horizon
        </span>
        <Link to="/roadmap">
          View roadmap <ArrowUpRight size={12} />
        </Link>
      </div>
      <div className="future-grid">
        {futureFeatures
          .filter((item) => item.module === module)
          .map((item) => (
            <article className="future-card" key={item.title}>
              <Badge>{item.deferred ? 'Deferred' : 'Coming soon'}</Badge>
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </article>
          ))}
      </div>
    </section>
  );
}

type ImplementationArea = {
  id: string;
  name: string;
  status: string;
  priority: string;
  working: string;
  pending: string[];
  note?: string;
};
type ImplementationStatus = {
  reviewed_on: string;
  scope: string;
  areas: ImplementationArea[];
  current_focus: string;
  execution_note: string;
};
const roadmapTabs = [
  { id: 'status', label: 'Implementation status', icon: ListChecks },
  { id: 'future', label: 'Coming soon', icon: Clock3 },
];

/** The complete pending inventory comes from the audited backend capability list. */
export function Roadmap() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'future' ? 'future' : 'status';
  const inventory = useResource<ImplementationStatus>('/roadmap');
  return (
    <>
      <PageTitle
        title="Coming soon"
        description="What works today, what’s still pending, and what we’ve set aside. No release dates are promised."
      />
      <SectionTabs
        id="roadmap"
        label="Roadmap sections"
        items={roadmapTabs}
        value={tab}
        onChange={(value) => setParams({ tab: value })}
      />
      <SectionPanel id="roadmap" value={tab}>
        {tab === 'status' ? (
          inventory.error ? (
            <ErrorState message={inventory.error} retry={inventory.retry} />
          ) : !inventory.data ? (
            <Loading />
          ) : (
            <>
              <div className="roadmap-scope">
                <Badge>Local workspace</Badge>
                <span>
                  Reviewed {new Date(inventory.data.reviewed_on).toLocaleDateString()} ·{' '}
                  {inventory.data.areas.length - 1} areas in scope · Multi-user deferred
                </span>
                <p>{inventory.data.current_focus}</p>
                <small>{inventory.data.execution_note}</small>
              </div>
              <div className="implementation-list">
                {inventory.data.areas.map((area) => (
                  <article className={`panel implementation-area ${area.priority}`} key={area.id}>
                    <div className="implementation-heading">
                      <h2>{area.name}</h2>
                      <Badge
                        tone={
                          area.status === 'deferred'
                            ? 'neutral'
                            : area.priority === 'next'
                              ? 'purple'
                              : 'neutral'
                        }
                      >
                        {area.status.replaceAll('-', ' ')}
                      </Badge>
                    </div>
                    <p>
                      <strong>Working today</strong> {area.working}
                    </p>
                    <details>
                      <summary>
                        {area.pending.length} pending workstreams{' '}
                        {area.priority === 'next' && <span>· Foundations first</span>}
                      </summary>
                      <ul>
                        {area.pending.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </details>
                    {area.note && <p className="footnote">{area.note}</p>}
                  </article>
                ))}
              </div>
            </>
          )
        ) : (
          <div className="future-grid">
            {futureFeatures.map((item) => (
              <article className="panel future-card" key={item.title}>
                <Badge>{item.deferred ? 'Deferred' : 'Coming soon'}</Badge>
                <small>{item.module}</small>
                <h2>{item.title}</h2>
                <p>{item.text}</p>
              </article>
            ))}
          </div>
        )}
      </SectionPanel>
    </>
  );
}
