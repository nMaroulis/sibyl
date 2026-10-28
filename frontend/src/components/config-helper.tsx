import { useState } from 'react';
import { ArrowUpRight, Check, KeyRound, Radio, Trash2, BarChart3 } from 'lucide-react';
import { Badge, ErrorState, Loading, Panel, PanelTitle, useToast } from './ui';
import { ExchangeMark } from './exchange-mark';
import { api, post, refresh } from '../lib/api';
import type { MarketSettings, MarketSource } from '../lib/types';
import { useResource } from '../lib/hooks';

/** Reuse local exchange logos and distinct API-provider icon marks. */
export function MarketSourceMark({ source }: { source: Pick<MarketSource, 'kind' | 'provider'> }) {
  return (
    <span className="news-source-mark" aria-hidden="true">
      {source.kind === 'api' ? (
        source.provider.startsWith('coingecko') ? (
          <img src="/market/coingecko.ico" width={30} height={30} alt="" />
        ) : (
          <BarChart3 size={24} color="#3779bb" />
        )
      ) : (
        <ExchangeMark exchange={source.provider} />
      )}
    </span>
  );
}

/** Source cards share the News picker language; one feed supplies each complete read. */
export function ConfigHelper() {
  const resource = useResource<MarketSettings>('/settings/market');
  if (resource.error) return <ErrorState message={resource.error} retry={resource.retry} />;
  if (!resource.data) return <Loading />;
  return <MarketSourceForm initial={resource.data} />;
}

function MarketSourceForm({ initial }: { initial: MarketSettings }) {
  const [saved, setSaved] = useState(initial);
  const [identity, setIdentity] = useState(initial.active.id);
  const [query, setQuery] = useState('');
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const selected = saved.catalog.find((s) => s.id === identity);
  const choose = (id: string) => {
    setIdentity(id);
    setKey('');
    setError('');
  };
  const card = (source: MarketSource) => (
    <button
      type="button"
      key={source.id}
      className="news-provider-card"
      aria-label={source.name}
      aria-pressed={identity === source.id}
      disabled={busy}
      onClick={() => choose(source.id)}
    >
      <MarketSourceMark source={source} />
      <span className="news-choice-copy">
        <strong>
          {source.name}{' '}
          {source.id === saved.active.id && <span className="picker-default-badge">Default</span>}
        </strong>
        <small>
          {source.kind === 'connection'
            ? `${source.provider} · ${source.environment === 'test' ? 'Test environment' : 'Connected account'}`
            : source.kind === 'api'
              ? `${source.candles ? 'Quotes & candles' : 'Quotes only'} · ${source.has_api_key ? 'Key saved' : source.requires_key ? 'Key required' : 'Optional key'}`
              : 'Public spot feed · no key'}
        </small>
      </span>
      <span className="news-choice-check" aria-hidden="true">
        {identity === source.id && <Check size={14} />}
      </span>
    </button>
  );
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await post<MarketSettings>('/settings/market', {
        source: identity,
        ...(key ? { api_key: key } : {}),
      });
      setSaved(result);
      setKey('');
      refresh();
      toast('Market source saved. New reads use your selection.');
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function removeKey() {
    setBusy(true);
    setError('');
    try {
      const result = await api<MarketSettings>(`/settings/market/${identity}/key`, {
        method: 'DELETE',
      });
      setSaved(result);
      setKey('');
      refresh();
      toast('Market API key removed.');
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save} className="news-settings-form">
      <Panel className="news-source-picker">
        <PanelTitle
          title="Choose your market source"
          subtitle="One consistent feed for prices, charts and market tools."
          action={
            <Badge tone={saved.active.id === identity ? 'lime' : 'sand'}>
              {saved.active.id === identity ? 'Active default' : 'Unsaved selection'}
            </Badge>
          }
        />
        <div className="news-picker-body">
          <div className="news-public-heading">
            <h3>Connected exchanges</h3>
            <span>Your saved accounts</span>
          </div>
          {saved.catalog.some((s) => s.kind === 'connection') ? (
            <div className="news-provider-grid">
              {saved.catalog.filter((s) => s.kind === 'connection').map(card)}
            </div>
          ) : (
            <p className="news-picker-note">
              Connect an exchange under Exchanges to use its account environment here. Public feeds
              below work without an account.
            </p>
          )}
          <div className="news-public-heading">
            <h3>Public exchange feeds</h3>
            <span>No API key required</span>
          </div>
          <label className="market-source-search">
            Find an exchange
            <input
              type="search"
              placeholder="Search exchanges…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div
            className="news-provider-grid market-provider-grid"
            role="group"
            aria-label="Public market sources"
          >
            {saved.catalog
              .filter(
                (s) => s.kind === 'exchange' && s.name.toLowerCase().includes(query.toLowerCase()),
              )
              .map(card)}
          </div>
          <div className="news-public-heading">
            <h3>Market APIs</h3>
            <span>Aggregated reference data</span>
          </div>
          <div className="news-provider-grid">
            {saved.catalog.filter((s) => s.kind === 'api').map(card)}
          </div>
          <div className="news-public-heading">
            <h3>Demo</h3>
            <span>Offline sample data</span>
          </div>
          <button
            type="button"
            className="news-demo-choice"
            aria-label="Demo prices"
            aria-pressed={identity === 'demo'}
            disabled={busy}
            onClick={() => choose('demo')}
          >
            <MarketSourceMark source={saved.catalog.find((source) => source.id === 'demo')!} />
            <span className="news-choice-copy">
              <strong>Demo prices</strong>
              <small>Offline prices, candles and order books. Used on its own.</small>
            </span>
            <span className="news-demo-exclusive">Offline</span>
            <span className="news-choice-check" aria-hidden="true">
              {identity === 'demo' && <Check size={14} />}
            </span>
          </button>
          <p className="news-picker-note">
            Active default: {saved.active.name}. Markets can use a temporary page selection. Private
            balances keep using each account’s own exchange.
          </p>
        </div>
      </Panel>
      {selected?.kind === 'api' && (
        <Panel className="full-panel">
          <PanelTitle
            title={`${selected.name} connection`}
            subtitle={selected.description}
            action={
              <a className="text-link" href={selected.website!} target="_blank" rel="noreferrer">
                API access & documentation <ArrowUpRight size={12} />
              </a>
            }
          />
          <div className="source-api-fields">
            <label>
              {selected.requires_key ? 'API key' : 'API key · optional'}
              <input
                type="password"
                autoComplete="off"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder={
                  selected.has_api_key
                    ? 'Leave blank to keep the saved key'
                    : 'Enter your provider key'
                }
              />
            </label>
            <p className="muted">{selected.note}</p>
          </div>
          <div className="source-key-note">
            <KeyRound size={14} />
            <p>
              Keys are encrypted on the server and never returned to the browser. Access and rate
              limits depend on your provider plan.
            </p>
            {selected.has_api_key && (
              <button
                className="text-button"
                type="button"
                disabled={busy || (saved.active.id === identity && selected.requires_key)}
                onClick={removeKey}
              >
                <Trash2 size={13} /> Remove saved key
              </button>
            )}
          </div>
          {selected.has_api_key && selected.requires_key && saved.active.id === identity && (
            <p className="market-key-hint">
              Select and save another default before removing this provider’s key.
            </p>
          )}
        </Panel>
      )}
      <Panel className="source-save-row">
        <div>
          <Radio size={18} />
          <p>
            {identity === 'demo'
              ? 'Demo uses deterministic data supplied by the backend.'
              : 'New reads use this feed immediately. Account mode and trading permissions stay separate.'}
          </p>
        </div>
        <button
          className="button primary"
          type="submit"
          disabled={busy || !selected || (selected.requires_key && !selected.has_api_key && !key)}
        >
          <Check size={14} />
          {busy ? 'Saving…' : 'Save market source'}
        </button>
      </Panel>
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
    </form>
  );
}
