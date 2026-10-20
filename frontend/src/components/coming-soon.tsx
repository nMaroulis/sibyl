import { Clock3, ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge, PageTitle } from './ui';

/** Explicit feature boundaries, shared by each module and the workspace roadmap. */
export const futureFeatures = [
  {
    module: 'markets',
    title: 'Deeper relationships',
    text: 'Granger causality, distance correlation, MIC, regression, and SHAP explanations.',
  },
  {
    module: 'strategies',
    title: 'More ways to test an idea',
    text: 'Freqtrade integration, machine learning strategies, and reinforcement learning.',
  },
  {
    module: 'strategies',
    title: 'Live strategy execution',
    text: 'Automated exchange trading with strategy-level controls and monitoring. Current strategy jobs use isolated paper funds.',
  },
  {
    module: 'trade',
    title: 'Advanced exchange orders',
    text: 'Limit, stop, take-profit, trailing, OCO, time-in-force, post-only, and iceberg controls. Current execution supports market orders.',
  },
  {
    module: 'forecast',
    title: 'Trained Chronos models',
    text: 'A new training and evaluation pipeline for LSTM and other forecasting models, with saved model comparisons.',
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
    module: 'settings',
    title: 'Local model manager',
    text: 'Download, quantize, and manage local model runtimes from the app. Existing model servers connect through ProtoLink configuration.',
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
              <Badge>Coming soon</Badge>
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </article>
          ))}
      </div>
    </section>
  );
}

export function Roadmap() {
  return (
    <>
      <PageTitle
        title="On the horizon"
        description="Planned additions, clearly separated from what works today. No release dates are promised."
      />
      <div className="future-grid">
        {futureFeatures.map((item) => (
          <article className="panel future-card" key={item.title}>
            <Badge>Coming soon</Badge>
            <small>{item.module}</small>
            <h2>{item.title}</h2>
            <p>{item.text}</p>
          </article>
        ))}
      </div>
    </>
  );
}
