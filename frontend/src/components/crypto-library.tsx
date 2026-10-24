import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  ArrowUpRight,
  BookOpen,
  Clock3,
  ExternalLink,
  Globe2,
  RefreshCw,
  Search,
} from 'lucide-react';
import { AgentButton } from './agents';
import { AssetIcon, Badge, Change, Empty, ErrorState, Loading, Panel, PanelTitle } from './ui';
import { useResource } from '../lib/hooks';
import { money, number } from '../lib/api';
import type { CryptoAsset, CryptoCatalog, CryptoProfile } from '../lib/types';

const date = (value: string | null) =>
  value && Number.isFinite(Date.parse(value))
    ? new Date(value).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    : 'Not reported';
const usd = (value: number | null) =>
  value === null ? '—' : money(value, value > 0 && value < 0.01 ? 8 : 2);
const compact = (value: number | null, currency = false) =>
  value === null
    ? '—'
    : new Intl.NumberFormat('en-US', {
        notation: 'compact',
        maximumFractionDigits: 2,
        ...(currency ? { style: 'currency', currency: 'USD' } : {}),
      }).format(value);

/** Browse an API-owned selection; every profile narrative and observation comes from the backend. */
export function CryptoLibraryView() {
  const catalog = useResource<CryptoCatalog>('/research/crypto');
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All categories');
  if (catalog.loading) return <Loading />;
  if (catalog.error || !catalog.data)
    return (
      <ErrorState message={catalog.error || 'Crypto library unavailable.'} retry={catalog.retry} />
    );
  const data = catalog.data;
  const selectedId = params.get('asset') || data.items[0]?.id;
  const selected = data.items.find((asset) => asset.id === selectedId);
  const filtered = data.items.filter(
    (asset) =>
      (category === 'All categories' || category === asset.category) &&
      `${asset.name} ${asset.symbol}`.toLowerCase().includes(query.toLowerCase()),
  );
  const choose = (id: string) =>
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set('tab', 'crypto');
      next.set('asset', id);
      return next;
    });
  return (
    <>
      <div className="crypto-library-intro">
        <div>
          <h2>A little context goes a long way.</h2>
          <p>{data.selection_note}</p>
        </div>
        <Badge>
          <Globe2 size={12} /> Public research
        </Badge>
      </div>
      <div className="crypto-library-layout">
        <Panel className="crypto-browser">
          <PanelTitle title="Crypto library" subtitle={`${data.items.length} familiar assets`} />
          <div className="crypto-browser-controls">
            <div className="search-field">
              <Search size={15} />
              <input
                aria-label="Search cryptocurrencies"
                maxLength={80}
                placeholder="Name or symbol…"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            <label className="sr-only" htmlFor="crypto-category">
              Crypto category
            </label>
            <select
              id="crypto-category"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              {['All categories', ...new Set(data.items.map((asset) => asset.category))].map(
                (value) => (
                  <option key={value}>{value}</option>
                ),
              )}
            </select>
          </div>
          <div className="crypto-asset-list" role="group" aria-label="Cryptocurrency profiles">
            {filtered.map((asset) => (
              <button
                type="button"
                key={asset.id}
                aria-label={`Read about ${asset.name}`}
                aria-pressed={selected?.id === asset.id}
                onClick={() => choose(asset.id)}
              >
                <AssetIcon asset={asset.symbol} color={asset.color} />
                <span>
                  <strong>{asset.name}</strong>
                  <small>{asset.symbol}</small>
                </span>
                <ArrowUpRight size={13} />
              </button>
            ))}
            {!filtered.length && <p className="crypto-list-empty">No assets match this search.</p>}
          </div>
          <p className="crypto-browser-note">
            Public data is separate from your trading mode and exchange accounts.
          </p>
        </Panel>
        <div className="crypto-detail-column">
          {selected ? (
            <CryptoDetail key={selected.id} asset={selected} />
          ) : (
            <Panel>
              <Empty title="Asset not in this library">
                <button
                  className="text-link"
                  type="button"
                  onClick={() => choose(data.items[0].id)}
                >
                  Choose a cryptocurrency
                </button>
              </Empty>
            </Panel>
          )}
        </div>
      </div>
    </>
  );
}

function CryptoDetail({ asset }: { asset: CryptoAsset }) {
  const resource = useResource<CryptoProfile>(`/research/crypto/${encodeURIComponent(asset.id)}`);
  const data = resource.data;
  const profile = data?.profile,
    history = data?.history,
    market = data?.market;
  return (
    <>
      <Panel className="crypto-identity-panel">
        <div className="crypto-identity">
          <AssetIcon asset={asset.symbol} color={asset.color} />
          <div>
            <div className="crypto-name-row">
              <h2>{asset.name}</h2>
              <span>{asset.symbol}</span>
            </div>
            <p>
              {asset.category}
              {market?.rank != null && ` · Market cap rank #${number(market.rank, 0)}`}
            </p>
          </div>
          <AgentButton module="wiki" context={{ crypto_id: asset.id }} />
        </div>
        <div className="crypto-profile-caption">
          <span>
            <Globe2 size={12} /> Fetched public sources
          </span>
          <span>
            {resource.loading
              ? 'Loading profile…'
              : data?.status === 'unavailable'
                ? 'Sources unavailable'
                : data?.status === 'partial'
                  ? 'Partial profile'
                  : 'Background, fundamentals & history'}
          </span>
        </div>
      </Panel>
      {resource.loading ? (
        <Loading />
      ) : resource.error || !data ? (
        <ErrorState message={resource.error || 'Profile unavailable.'} retry={resource.retry} />
      ) : (
        <>
          {data.sources.some((source) => source.error) && (
            <div className="crypto-source-alert" role="status">
              <p>
                {data.sources
                  .filter((source) => source.error)
                  .map(
                    (source) =>
                      `${source.source}: ${source.error}${source.stale ? ' Showing the last successful observation.' : ''}`,
                  )
                  .join(' ')}
              </p>
              <button type="button" className="text-button" onClick={resource.retry}>
                <RefreshCw size={12} /> Retry sources
              </button>
              <small>Failed sources retry at most once per minute.</small>
            </div>
          )}
          {market && (
            <Panel className="crypto-market-panel">
              <PanelTitle
                title="Market snapshot"
                subtitle={`USD · Provider update ${date(market.updated_at)}`}
                action={<Badge>CoinPaprika</Badge>}
              />
              <div className="crypto-market-metrics">
                <div>
                  <small>Price</small>
                  <strong>{usd(market.price)}</strong>
                </div>
                <div>
                  <small>Market cap</small>
                  <strong>{compact(market.market_cap, true)}</strong>
                </div>
                <div>
                  <small>24h volume</small>
                  <strong>{compact(market.volume_24h, true)}</strong>
                </div>
              </div>
              <div className="crypto-period-changes">
                {(
                  [
                    ['24 hours', market.percent_change_24h],
                    ['7 days', market.percent_change_7d],
                    ['30 days', market.percent_change_30d],
                    ['1 year', market.percent_change_1y],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label}>
                    <small>{label}</small>
                    {value === null ? <span>—</span> : <Change value={value} />}
                  </div>
                ))}
              </div>
            </Panel>
          )}
          {(profile || history) && (
            <div className="crypto-fundamentals-grid">
              <Panel className="crypto-about">
                <PanelTitle
                  title="About the project"
                  subtitle={
                    profile?.description
                      ? 'CoinPaprika project description'
                      : 'Wikipedia introduction'
                  }
                />
                <p className="crypto-prose">
                  {profile?.description ||
                    history?.introduction ||
                    'No description was supplied by the sources.'}
                </p>
                {!!profile?.tags.length && (
                  <div className="crypto-tags">
                    {profile.tags.map((tag) => (
                      <Badge key={tag}>{tag}</Badge>
                    ))}
                  </div>
                )}
              </Panel>
              <Panel>
                <PanelTitle title="At a glance" subtitle="Facts reported by the sources" />
                <dl className="crypto-facts">
                  <div>
                    <dt>Provider launch date</dt>
                    <dd>{date(profile?.launch_date ?? null)}</dd>
                  </div>
                  <div>
                    <dt>Consensus</dt>
                    <dd>{profile?.proof_type || 'Not reported'}</dd>
                  </div>
                  <div>
                    <dt>Organization</dt>
                    <dd>{profile?.organization || 'Not reported'}</dd>
                  </div>
                  <div>
                    <dt>Development status</dt>
                    <dd>{profile?.development_status || 'Not reported'}</dd>
                  </div>
                  <div>
                    <dt>Open source</dt>
                    <dd>
                      {profile?.open_source == null
                        ? 'Not reported'
                        : profile.open_source
                          ? 'Yes'
                          : 'No'}
                    </dd>
                  </div>
                  {market && (
                    <>
                      <div>
                        <dt>Circulating supply</dt>
                        <dd>
                          {market.circulating_supply == null
                            ? 'Not reported'
                            : `${compact(market.circulating_supply)} ${asset.symbol}`}
                        </dd>
                      </div>
                      <div>
                        <dt>Total supply</dt>
                        <dd>
                          {market.total_supply == null
                            ? 'Not reported'
                            : `${compact(market.total_supply)} ${asset.symbol}`}
                        </dd>
                      </div>
                      <div>
                        <dt>Maximum supply</dt>
                        <dd>
                          {market.max_supply == null
                            ? 'Not reported'
                            : `${compact(market.max_supply)} ${asset.symbol}`}
                        </dd>
                      </div>
                      <div>
                        <dt>Reported all-time high</dt>
                        <dd>
                          {usd(market.ath_price)}
                          <small>{date(market.ath_date)}</small>
                        </dd>
                      </div>
                    </>
                  )}
                </dl>
              </Panel>
            </div>
          )}
          {history && (
            <Panel className="crypto-history-panel">
              <PanelTitle
                title="Origins & history"
                subtitle={`Wikipedia · ${history.title}`}
                action={<BookOpen size={17} />}
              />
              {history.article_note && (
                <p className="crypto-article-note">{history.article_note}</p>
              )}
              {profile?.description && <p className="crypto-prose">{history.introduction}</p>}
              <div className="crypto-history-sections">
                {history.sections.map((section, index) => (
                  <details key={`${section.title}-${index}`} open={index < 2}>
                    <summary>
                      <span>{String(index + 1).padStart(2, '0')}</span>
                      {section.title}
                    </summary>
                    <p className="crypto-prose">{section.text}</p>
                  </details>
                ))}
              </div>
              <div className="crypto-history-attribution">
                <p>
                  Selected excerpts from Wikipedia, not a complete project history.{' '}
                  <a href={history.license_url} target="_blank" rel="noreferrer">
                    CC BY-SA 4.0
                  </a>
                  {history.revision && <> · Revision {history.revision}</>}. Fetched{' '}
                  {date(data.sources.find((source) => source.part === 'history')?.as_of ?? null)}.
                </p>
                <a className="text-link" href={history.url} target="_blank" rel="noreferrer">
                  Read the full article <ExternalLink size={12} />
                </a>
              </div>
            </Panel>
          )}
          {!!profile?.team.length && (
            <Panel className="crypto-team-panel">
              <PanelTitle
                title="People & contributors"
                subtitle="People listed by CoinPaprika; this is not an exhaustive or current team directory"
              />
              <div className="crypto-team-list">
                {profile.team.map((member, index) => (
                  <div key={`${member.name}-${index}`}>
                    <strong>{member.name}</strong>
                    <span>{member.position || 'Role not specified'}</span>
                  </div>
                ))}
              </div>
            </Panel>
          )}
          {!!profile?.links.length && (
            <Panel className="crypto-links-panel">
              <PanelTitle
                title="Go to the source"
                subtitle="Project links supplied by CoinPaprika"
              />
              <div className="crypto-official-links">
                {profile.links.map((link) => (
                  <a
                    key={`${link.label}-${link.url}`}
                    href={link.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <Globe2 size={16} />
                    <span>
                      <strong>{link.label}</strong>
                      <small>{new URL(link.url).hostname}</small>
                    </span>
                    <ArrowUpRight size={14} />
                  </a>
                ))}
              </div>
            </Panel>
          )}
          {data.status === 'unavailable' && (
            <Panel>
              <Empty title="Public sources are unavailable">
                Choose another asset or retry once the providers are reachable. Profile text and
                prices are never replaced with invented data.
              </Empty>
            </Panel>
          )}
          <Panel className="crypto-sources-panel">
            <PanelTitle
              title="Sources & freshness"
              subtitle="Each source is fetched and cached independently"
            />
            <div className="crypto-source-list">
              {data.sources.map((source) => (
                <div key={source.part}>
                  <span>
                    <a className="text-link" href={source.url} target="_blank" rel="noreferrer">
                      <strong>{source.source}</strong>
                      <ExternalLink size={11} />
                    </a>
                    <small>
                      <Clock3 size={11} />{' '}
                      {source.as_of
                        ? new Date(source.as_of).toLocaleString()
                        : 'No successful observation'}
                    </small>
                  </span>
                  <Badge tone={source.error ? 'rose' : 'neutral'}>
                    {source.stale
                      ? 'Stale'
                      : source.error
                        ? 'Unavailable'
                        : source.cached
                          ? 'Cached'
                          : 'Fetched'}
                  </Badge>
                </div>
              ))}
            </div>
            <p className="footnote padded">
              Profiles and encyclopedia text cache for 24 hours; market snapshots for 15 minutes.
              Prices and supply come from a public aggregator and can differ from your exchange.
              Stablecoin prices can move away from their target.
            </p>
          </Panel>
        </>
      )}
    </>
  );
}
