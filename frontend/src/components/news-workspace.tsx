import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowUpRight,
  ChartNoAxesCombined,
  ChevronLeft,
  ChevronRight,
  Newspaper,
  Radio,
  RefreshCw,
  Search,
  Settings2,
  Sparkles,
} from 'lucide-react';
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AgentButton } from './agents';
import { FearGreedCard } from './fear-greed';
import { ComingSoon } from './coming-soon';
import { SectionPanel, SectionTabs } from './section-tabs';
import { Badge, Empty, ErrorState, Loading, Modal, PageTitle, Panel, PanelTitle } from './ui';
import { post, shortDate } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Agent, AgentContext, Article, NewsFeed } from '../lib/types';

const tabs = [
  { id: 'headlines', label: 'Headlines', icon: Newspaper },
  { id: 'sentiment', label: 'Tone & trends', icon: ChartNoAxesCombined },
  { id: 'sources', label: 'Sources', icon: Radio },
];
const polarity = (value: number | null | undefined) => {
  if (value == null) return '—';
  const rounded = Number(value.toFixed(3));
  return `${rounded > 0 ? '+' : ''}${rounded.toFixed(3)}`;
};
const timestamp = (value: string | null) =>
  value
    ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    : 'Not yet collected';

/** A backend-filtered news reader; public reporting is independent of trading mode. */
export function NewsWorkspace() {
  const [params, setParams] = useSearchParams();
  const tab = tabs.some((t) => t.id === params.get('tab')) ? params.get('tab')! : 'headlines';
  const hasLegacyMode = params.has('mode');
  // Saved workspace sources also apply to older links that included a mode override.
  useEffect(() => {
    if (!hasLegacyMode) return;
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.delete('mode');
        return next;
      },
      { replace: true },
    );
  }, [hasLegacyMode, setParams]);
  const publisher = params.get('publisher') ?? '';
  const asset = params.get('asset') ?? '';
  const sentiment = params.get('sentiment') ?? '';
  const days = ['0', '1', '7', '30'].includes(params.get('days') ?? '') ? params.get('days')! : '7';
  const summary = params.get('summary') === 'extractive' ? 'extractive' : 'excerpt';
  const offset = Math.min(5000, Math.max(0, Number(params.get('offset')) || 0));
  const query = params.get('q') ?? '';
  const [search, setSearch] = useState(query);
  useEffect(() => setSearch(query), [query]);
  const change = (values: Record<string, string>, resetPage = true) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (resetPage) next.delete('offset');
      for (const [key, value] of Object.entries(values))
        value ? next.set(key, value) : next.delete(key);
      return next;
    });
  };
  const request = new URLSearchParams({
    publisher,
    asset,
    sentiment,
    days,
    summary,
    q: query,
    offset: String(offset),
    limit: '18',
  });
  const news = useResource<NewsFeed>(`/news?${request}`, 60000);
  const agents = useResource<Agent[]>('/agents', 60000);
  const reporter = agents.error ? undefined : agents.data?.find((agent) => agent.id === 'reporter');
  const provider = reporter?.provider;
  const data = news.data;
  const context: AgentContext = {
    news_mode: data?.mode,
    news_publisher: publisher,
    news_asset: asset,
    news_sentiment: sentiment as AgentContext['news_sentiment'],
    news_days: Number(days),
    query,
  };
  const [sampleArticle, setSampleArticle] = useState<Article>();
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState('');
  const [refreshError, setRefreshError] = useState('');
  async function collect() {
    setRefreshing(true);
    setRefreshMessage('');
    setRefreshError('');
    try {
      const result = await post<{ attempted: number; in_progress: boolean }>('/news/refresh');
      setRefreshMessage(
        result.in_progress
          ? 'Collection is already in progress.'
          : result.attempted
            ? `${result.attempted} publisher feeds checked.`
            : 'Feeds were checked recently. Refresh is available once a minute.',
      );
      news.retry();
    } catch (error) {
      setRefreshError((error as Error).message);
    } finally {
      setRefreshing(false);
    }
  }
  const problems = data?.sources.filter((s) => s.status !== 'fresh') ?? [];
  return (
    <>
      <PageTitle
        eyebrow="LOOK BEYOND THE TICKER"
        title="News & insights"
        description="Follow the reporting. Understand the tone. Keep the context."
        action={<AgentButton module="reporter" context={context} />}
      />
      <SectionTabs
        id="news"
        label="News workspace"
        items={tabs}
        value={tab}
        onChange={(value) => change({ tab: value }, false)}
      />
      {(provider === 'none' || provider === 'mock' || reporter?.model_ready === false) && (
        <aside className="news-ai-note" aria-label="Reporter AI availability">
          <Sparkles size={16} aria-hidden="true" />
          <p>
            <strong>
              {provider === 'mock'
                ? 'Mock AI is active.'
                : provider === 'none'
                  ? 'No AI model connected.'
                  : 'Reporter model needs setup.'}
            </strong>{' '}
            {provider === 'mock'
              ? 'Reporter’s AI responses are simulated.'
              : 'Reporter can retrieve source excerpts; AI explanations need a model.'}{' '}
            News, sentiment and Fear & Greed still work.
          </p>
          <Link className="text-link" to="/settings?tab=models">
            Connect a model <ArrowUpRight size={13} aria-hidden="true" />
          </Link>
        </aside>
      )}
      <div className="news-reader-controls panel">
        <div className="news-settings-row">
          {data && (
            <Badge tone={data.mode === 'demo' ? 'purple' : 'blue'}>
              {data.mode === 'demo' ? 'Demo stories' : `${data.sources.length} sources`}
            </Badge>
          )}
          <p>Using your saved news sources.</p>
          <Link className="text-link" to="/settings?tab=news">
            <Settings2 size={14} aria-hidden="true" />
            News settings <ArrowUpRight size={13} aria-hidden="true" />
          </Link>
          {data?.mode === 'live' && (
            <button className="button secondary" onClick={collect} disabled={refreshing}>
              <RefreshCw size={14} className={refreshing ? 'spin' : ''} />
              {refreshing ? 'Collecting…' : 'Refresh feeds'}
            </button>
          )}
        </div>
        <div className="news-query-row">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              change({ q: search.trim() });
            }}
          >
            <label htmlFor="news-search">Search reporting</label>
            <div className="news-search-field">
              <Search size={15} />
              <input
                id="news-search"
                value={search}
                maxLength={200}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Headlines & excerpts"
              />
              <button type="submit" aria-label="Search news">
                <ArrowUpRight size={16} />
              </button>
            </div>
          </form>
          <label>
            Publisher
            <select value={publisher} onChange={(e) => change({ publisher: e.target.value })}>
              <option value="">All publishers</option>
              {data?.facets.publishers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Asset mentioned
            <select value={asset} onChange={(e) => change({ asset: e.target.value })}>
              <option value="">All assets</option>
              {data?.facets.assets.map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
          </label>
          <label>
            Time window
            <select value={days} onChange={(e) => change({ days: e.target.value })}>
              <option value="1">Last 24 hours</option>
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
              <option value="0">All retained · includes undated</option>
            </select>
          </label>
          <label>
            Text polarity
            <select value={sentiment} onChange={(e) => change({ sentiment: e.target.value })}>
              <option value="">All tones</option>
              <option value="positive">Positive</option>
              <option value="neutral">Neutral</option>
              <option value="negative">Negative</option>
            </select>
          </label>
        </div>
        {refreshMessage && (
          <p className="footnote" role="status">
            {refreshMessage}
          </p>
        )}
        {refreshError && (
          <p className="error-text" role="alert">
            {refreshError}
          </p>
        )}
      </div>
      <SectionPanel id="news" value={tab}>
        {news.error ? (
          <ErrorState message={news.error} retry={news.retry} />
        ) : news.loading || !data ? (
          <Loading />
        ) : (
          <>
            {data.mode === 'demo' && (
              <p className="news-source-note">
                <Badge tone="purple">Demo</Badge> Illustrative stories and dates. Choose public
                publisher feeds in News settings for current reporting.
              </p>
            )}
            {data.mode === 'live' && problems.length > 0 && (
              <p className="news-source-note" role="status">
                <Radio size={15} />
                {problems.length} of {data.sources.length} sources need attention. Available
                archived stories remain readable.
                <button onClick={() => change({ tab: 'sources' }, false)}>
                  View sources <ArrowUpRight size={13} />
                </button>
              </p>
            )}
            {tab !== 'sources' && (
              <div className="news-context-grid">
                <FearGreedCard mode={data.mode} />
                <Panel className="news-tone-overview">
                  <PanelTitle
                    title="The tone of this selection"
                    subtitle={`${data.total} matching stories · VADER · headline and excerpt wording`}
                  />
                  <div className="extended-metrics">
                    {(['positive', 'neutral', 'negative'] as const).map((label) => (
                      <div key={label}>
                        <small>{label} stories</small>
                        <strong>{data.sentiment[label]}</strong>
                      </div>
                    ))}
                    <div>
                      <small>Mean polarity · −1 to +1</small>
                      <strong>{polarity(data.sentiment.compound)}</strong>
                    </div>
                  </div>
                  <p className="footnote padded">
                    {data.sentiment.note} Totals cover every matching story, before pagination.
                  </p>
                </Panel>
              </div>
            )}
            {tab === 'headlines' && (
              <>
                <div className="news-topline">
                  <p className="footnote">
                    {data.items.length
                      ? `${offset + 1}–${Math.min(offset + data.items.length, data.total)} of ${data.total}`
                      : data.total
                        ? `No stories on this page · ${data.total} matching`
                        : 'No matching stories'}{' '}
                    · {data.archive_count} {data.mode === 'demo' ? 'sample' : 'archived'} stories
                  </p>
                  <label className="news-summary-control">
                    Summary
                    <select
                      value={summary}
                      onChange={(e) => change({ summary: e.target.value }, false)}
                    >
                      <option value="excerpt">Publisher excerpt</option>
                      <option value="extractive">Extractive · up to 2 sentences</option>
                    </select>
                  </label>
                </div>
                {data.items.length ? (
                  <div className="news-grid">
                    {data.items.map((item, i) => (
                      <article
                        className={`news-card panel ${i === 0 && data.items.length > 2 ? 'featured-story' : ''}`}
                        key={item.id}
                      >
                        <div className="news-content">
                          <div className="news-meta">
                            <strong className="news-publisher-name">{item.publisher}</strong>
                            <Badge>{item.category || 'Markets'}</Badge>
                            <Badge
                              tone={
                                item.sentiment.label === 'positive'
                                  ? 'lime'
                                  : item.sentiment.label === 'negative'
                                    ? 'rose'
                                    : 'neutral'
                              }
                            >
                              {item.sentiment.label} · {item.sentiment.compound.toFixed(2)}
                            </Badge>
                            <time
                              dateTime={item.published_at ?? undefined}
                              title={
                                item.published_at
                                  ? timestamp(item.published_at)
                                  : 'Publisher date unavailable'
                              }
                            >
                              {item.published_at ? shortDate(item.published_at) : 'Undated'}
                            </time>
                          </div>
                          <h2>{item.title}</h2>
                          <p>
                            {item.summary ||
                              'The publisher did not provide an excerpt. Open the source to read the reporting.'}
                          </p>
                          {item.assets.length > 0 && (
                            <div className="news-asset-tags">
                              {item.assets.map((a) => (
                                <button
                                  key={a}
                                  onClick={() => change({ asset: a })}
                                  aria-label={`Filter news mentioning ${a}`}
                                >
                                  {a}
                                </button>
                              ))}
                            </div>
                          )}
                          <div className="news-card-bottom">
                            <span>
                              {item.source_id === 'demo'
                                ? 'Demo briefing'
                                : item.source_id === 'newsapi'
                                  ? 'Via NewsAPI · publisher excerpt'
                                  : 'Publisher excerpt'}
                            </span>
                            {item.url && (
                              <a
                                className="button secondary news-read-article"
                                href={item.url}
                                target="_blank"
                                rel="noreferrer"
                                aria-label={`Read full article: ${item.title}`}
                              >
                                Read full article <ArrowUpRight size={15} />
                              </a>
                            )}
                            {!item.url && item.source_id === 'demo' && (
                              <button
                                className="button secondary news-read-article"
                                onClick={() => setSampleArticle(item)}
                              >
                                Read demo briefing <ArrowUpRight size={14} />
                              </button>
                            )}
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <Empty title="A quiet corner of the feed">
                    Try another asset, time window, or keyword.
                    {days !== '0' && ' Undated stories appear under All retained.'}
                  </Empty>
                )}
                <nav className="news-pagination" aria-label="News pagination">
                  <button
                    className="button secondary"
                    disabled={offset === 0}
                    onClick={() => change({ offset: String(Math.max(0, offset - 18)) }, false)}
                  >
                    <ChevronLeft size={15} />
                    Previous
                  </button>
                  <span>Page {Math.floor(offset / 18) + 1}</span>
                  <button
                    className="button secondary"
                    disabled={!data.has_more}
                    onClick={() => change({ offset: String(offset + 18) }, false)}
                  >
                    Next
                    <ChevronRight size={15} />
                  </button>
                </nav>
                <p className="footnote">
                  {data.note} Extractive summaries select sentences from the excerpt, never the full
                  article.
                </p>
              </>
            )}
            {tab === 'sentiment' && (
              <>
                <Panel className="full-panel">
                  <PanelTitle
                    title="Reporting over time"
                    subtitle="UTC publication dates · counts and equal-weight mean text polarity"
                  />
                  {data.sentiment.timeline.length ? (
                    <div className="news-sentiment-chart">
                      <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart
                          data={data.sentiment.timeline}
                          margin={{ top: 15, right: 16, left: 0, bottom: 8 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" vertical={false} />
                          <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 11 }} />
                          <YAxis yAxisId="count" allowDecimals={false} tick={{ fontSize: 11 }} />
                          <YAxis
                            yAxisId="polarity"
                            orientation="right"
                            domain={[-1, 1]}
                            tick={{ fontSize: 11 }}
                          />
                          <Tooltip labelFormatter={(label) => `UTC · ${label}`} />
                          <Legend />
                          <Bar
                            yAxisId="count"
                            dataKey="positive"
                            name="Positive stories"
                            stackId="stories"
                            fill="#85b6a4"
                          />
                          <Bar
                            yAxisId="count"
                            dataKey="neutral"
                            name="Neutral stories"
                            stackId="stories"
                            fill="#d4dce7"
                          />
                          <Bar
                            yAxisId="count"
                            dataKey="negative"
                            name="Negative stories"
                            stackId="stories"
                            fill="#dca8b0"
                            radius={[3, 3, 0, 0]}
                          />
                          <Line
                            yAxisId="polarity"
                            dataKey="compound"
                            name="Mean polarity"
                            stroke="#4675d2"
                            strokeWidth={2}
                            dot={{ r: 3 }}
                          />
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <Empty title="No dated samples">Try a wider time window.</Empty>
                  )}
                  <p className="footnote padded">
                    {data.sentiment.undated} undated stories are excluded from the chart. This is an
                    archive of collected reporting, not a complete historical news dataset.
                  </p>
                </Panel>
                <Panel className="full-panel">
                  <PanelTitle
                    title="Assets in the conversation"
                    subtitle="Article-level tone for stories mentioning an asset · keyword tags, not entity-targeted sentiment"
                  />
                  {data.sentiment.assets.length ? (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Asset mentioned</th>
                            <th>Stories</th>
                            <th>Positive</th>
                            <th>Neutral</th>
                            <th>Negative</th>
                            <th>Mean polarity</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.sentiment.assets.map((group) => (
                            <tr key={group.asset}>
                              <td>
                                <button
                                  className="text-link"
                                  onClick={() => change({ asset: group.asset, tab: 'headlines' })}
                                >
                                  {group.asset} <ArrowUpRight size={13} />
                                </button>
                              </td>
                              <td>{group.count}</td>
                              <td>{group.positive}</td>
                              <td>{group.neutral}</td>
                              <td>{group.negative}</td>
                              <td>{polarity(group.compound)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Empty title="No recognized asset mentions">
                      Asset tags recognize 20 familiar crypto names and uppercase tickers.
                    </Empty>
                  )}
                </Panel>
              </>
            )}
            {tab === 'sources' && (
              <>
                {data.mode === 'demo' ? (
                  <Panel className="full-panel">
                    <PanelTitle
                      title="Offline, by design"
                      subtitle="Sample briefings never enter the publisher archive."
                    />
                    <div className="padded">
                      <p>
                        Switch to public feeds to collect CoinDesk, Cointelegraph, Decrypt, The
                        Block, and CryptoSlate reporting.
                      </p>
                      <button
                        className="button secondary"
                        onClick={() => change({ mode: 'live', publisher: '' })}
                      >
                        Browse public news
                        <ArrowUpRight size={15} />
                      </button>
                    </div>
                  </Panel>
                ) : (
                  <div className="news-source-grid">
                    {data.sources.map((source) => (
                      <Panel key={source.id} className="news-source-card">
                        <div className="news-source-heading">
                          <h2>{source.name}</h2>
                          <Badge
                            tone={
                              source.status === 'fresh'
                                ? 'lime'
                                : source.status === 'stale'
                                  ? 'sand'
                                  : 'rose'
                            }
                          >
                            {source.status.replace('_', ' ')}
                          </Badge>
                        </div>
                        <p>{source.articles} retained stories</p>
                        <dl>
                          <dt>Last successful check</dt>
                          <dd>{timestamp(source.last_success)}</dd>
                          <dt>Last attempt</dt>
                          <dd>{timestamp(source.last_attempt)}</dd>
                        </dl>
                        {source.error && <p className="news-source-error">{source.error}</p>}
                        <div className="news-source-footer">
                          <a href={source.website} target="_blank" rel="noreferrer">
                            Publisher site
                            <ArrowUpRight size={13} />
                          </a>
                          <button
                            onClick={() => change({ publisher: source.id, tab: 'headlines' })}
                          >
                            View stories
                            <ArrowUpRight size={13} />
                          </button>
                        </div>
                      </Panel>
                    ))}
                  </div>
                )}
                <p className="footnote">
                  Enabled news collectors refresh every {data.collection.refresh_seconds / 60}{' '}
                  minutes when due. Manual collection has a one-minute cooldown. The archive retains
                  up to {data.collection.max_articles.toLocaleString()} stories for{' '}
                  {data.collection.retention_days} days; outages keep previous data with a visible
                  status. No full-article scraping or paid news API is required.
                </p>
              </>
            )}
          </>
        )}
      </SectionPanel>
      {data && (
        <div className="news-attribution">
          <h2>Where your news comes from</h2>
          <p>
            {data.mode === 'demo' ? (
              'These briefings are generated from the backend Demo provider. Their stories, dates, and index values are illustrative.'
            ) : (
              <>
                This feed collects headlines and excerpts from{' '}
                {data.sources.length
                  ? data.sources.map((source, i) => (
                      <span key={source.id}>
                        {i > 0 ? ', ' : ''}
                        <a href={source.website} target="_blank" rel="noreferrer">
                          {source.name}
                        </a>{' '}
                        (
                        {source.method === 'web'
                          ? 'website collector'
                          : source.method === 'api'
                            ? 'API'
                            : 'RSS'}
                        )
                      </span>
                    ))
                  : 'no enabled public sources'}
                . Original publishers are named on every article. Read full article opens the
                publisher’s original reporting; access may depend on the publisher.
              </>
            )}
          </p>
          <p>
            Fear & Greed is a separate Bitcoin market index
            {data.mode === 'live' ? (
              <>
                {' '}
                from{' '}
                <a
                  href="https://alternative.me/crypto/fear-and-greed-index/"
                  target="_blank"
                  rel="noreferrer"
                >
                  Alternative.me
                </a>
              </>
            ) : (
              ' with demo values here'
            )}
            . Article polarity scores describe wording in headlines and excerpts.
          </p>
          <Link className="text-link" to="/settings?tab=news">
            Manage news sources <ArrowUpRight size={13} />
          </Link>
        </div>
      )}
      {sampleArticle && (
        <Modal
          title={sampleArticle.title}
          onClose={() => setSampleArticle(undefined)}
          className="news-demo-reader"
        >
          <Badge tone="purple">Demo briefing</Badge>
          {(sampleArticle.body || sampleArticle.summary).split('\n\n').map((paragraph, i) => (
            <p key={i}>{paragraph}</p>
          ))}
        </Modal>
      )}
      <ComingSoon module="news" />
    </>
  );
}
