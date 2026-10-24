import { useState } from 'react';
import { ArrowUpRight, Check, KeyRound, Newspaper, Save } from 'lucide-react';
import { Badge, ErrorState, Loading, Panel, PanelTitle, useToast } from './ui';
import { NewsSourceMark } from './news-source-mark';
import { post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { NewsSettings as Settings } from '../lib/types';

/** Save collector preferences and a write-only provider credential through the backend. */
export function NewsSettings() {
  const resource = useResource<Settings>('/settings/news');
  if (resource.error) return <ErrorState message={resource.error} retry={resource.retry} />;
  if (!resource.data) return <Loading />;
  return <NewsSettingsForm initial={resource.data} />;
}

function NewsSettingsForm({ initial }: { initial: Settings }) {
  const [saved, setSaved] = useState(initial);
  const [demo, setDemo] = useState(initial.resolved_mode === 'demo');
  const [sources, setSources] = useState(initial.resolved_mode === 'demo' ? [] : initial.sources);
  const [method, setMethod] = useState(initial.cryptoslate_method);
  const [query, setQuery] = useState(initial.query);
  const [key, setKey] = useState('');
  const [removeKey, setRemoveKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const canSave = demo || sources.length > 0;
  const choose = (id: string) => {
    setError('');
    if (id === 'demo') {
      setDemo(true);
      setSources([]);
      return;
    }
    setDemo(false);
    setSources((current) =>
      demo
        ? [id]
        : current.includes(id)
          ? current.filter((source) => source !== id)
          : [...current, id],
    );
  };
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await post<Settings>('/settings/news', {
        mode: demo ? 'demo' : 'live',
        sources: demo ? [] : sources,
        cryptoslate_method: method,
        query,
        ...(!demo && key ? { api_key: key } : {}),
        clear_api_key: removeKey,
      });
      setSaved(result);
      setSources(result.sources);
      setKey('');
      setRemoveKey(false);
      refresh();
      toast('News sources saved. New reads use your selection.');
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
          title="Choose your news sources"
          subtitle="Use Demo on its own, or combine public sources."
          action={
            <Badge tone={demo ? 'purple' : 'blue'}>
              {demo
                ? 'Demo only'
                : sources.length
                  ? `${sources.length} selected`
                  : 'Choose a source'}
            </Badge>
          }
        />
        <div className="news-picker-body">
          <button
            type="button"
            className="news-demo-choice"
            aria-label="Demo briefings"
            aria-pressed={demo}
            disabled={busy}
            onClick={() => choose('demo')}
          >
            <NewsSourceMark source="demo" />
            <span className="news-choice-copy">
              <strong>Demo briefings</strong>
              <small>Sample news and Fear & Greed. Used on its own.</small>
            </span>
            <span className="news-demo-exclusive">Exclusive</span>
            <span className="news-choice-check" aria-hidden="true">
              {demo && <Check size={14} />}
            </span>
          </button>
          <div className="news-public-heading">
            <h3>Publishers & APIs</h3>
            <span>Select one or more</span>
          </div>
          <div className="news-provider-grid" role="group" aria-label="Public news sources">
            {initial.catalog
              .filter((source) => source.id !== 'demo')
              .map((source) => {
                const selected = !demo && sources.includes(source.id);
                return (
                  <button
                    type="button"
                    key={source.id}
                    className="news-provider-card"
                    aria-label={source.name}
                    aria-pressed={selected}
                    disabled={busy}
                    onClick={() => choose(source.id)}
                  >
                    <NewsSourceMark source={source.id} />
                    <span className="news-choice-copy">
                      <strong>{source.name}</strong>
                      <small>
                        {source.kind === 'api'
                          ? saved.has_api_key
                            ? 'API · key saved'
                            : 'API · key required'
                          : source.id === 'cryptoslate' && method === 'web'
                            ? 'Website collector'
                            : 'Public RSS feed'}
                      </small>
                    </span>
                    <span className="news-choice-check" aria-hidden="true">
                      {selected && <Check size={14} />}
                    </span>
                  </button>
                );
              })}
          </div>
          <p className="news-picker-note" role="status">
            {demo
              ? 'Only Demo is selected. Choose any publisher to switch to public news.'
              : sources.length
                ? 'Only your selected sources contribute to News and Reporter. Public news can run with demo exchange accounts.'
                : 'Select a public source, or choose Demo to continue.'}
          </p>
        </div>
      </Panel>
      {!demo && sources.includes('cryptoslate') && (
        <Panel className="news-collector-options">
          <div>
            <NewsSourceMark source="cryptoslate" />
            <div>
              <h3>CryptoSlate collection</h3>
              <p>Choose how to collect public headlines and excerpts.</p>
            </div>
          </div>
          <div
            className="news-collector-switch"
            role="group"
            aria-label="CryptoSlate collection method"
          >
            <button
              type="button"
              aria-pressed={method === 'rss'}
              disabled={busy}
              onClick={() => setMethod('rss')}
            >
              Publisher RSS
            </button>
            <button
              type="button"
              aria-pressed={method === 'web'}
              disabled={busy}
              onClick={() => setMethod('web')}
            >
              Website collector
            </button>
          </div>
        </Panel>
      )}
      <div hidden={demo || !sources.includes('newsapi')}>
        <Panel className="full-panel">
          <PanelTitle
            title="NewsAPI connection"
            subtitle="Search across publishers with your encrypted provider key."
            action={
              <div className="news-api-heading-actions">
                <Badge tone={saved.has_api_key ? 'lime' : 'neutral'}>
                  {saved.has_api_key ? 'Key saved' : 'No key saved'}
                </Badge>
                <a
                  className="text-link"
                  href="https://newsapi.org"
                  target="_blank"
                  rel="noreferrer"
                >
                  API access & plans <ArrowUpRight size={12} />
                </a>
              </div>
            }
          />
          <div className="source-api-fields">
            <label>
              NewsAPI key
              <input
                type="password"
                autoComplete="off"
                value={key}
                onChange={(e) => {
                  setKey(e.target.value);
                  setRemoveKey(false);
                }}
                placeholder={
                  saved.has_api_key ? 'Leave blank to keep the saved key' : 'Enter your NewsAPI key'
                }
              />
            </label>
            <label>
              NewsAPI search query
              <input
                value={query}
                maxLength={200}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="bitcoin OR ethereum OR cryptocurrency"
              />
            </label>
          </div>
          <div className="source-key-note">
            <KeyRound size={14} />
            <p>
              Keys are encrypted on the server and never returned to the browser. NewsAPI access and
              freshness depend on your plan.
            </p>
            {saved.has_api_key && (
              <label>
                <input
                  type="checkbox"
                  checked={removeKey}
                  onChange={(e) => {
                    setRemoveKey(e.target.checked);
                    setKey('');
                    if (e.target.checked)
                      setSources((current) => current.filter((s) => s !== 'newsapi'));
                  }}
                />
                Remove saved key
              </label>
            )}
          </div>
        </Panel>
      </div>
      <Panel className="source-save-row">
        <div>
          <Newspaper size={18} />
          <p>
            {demo
              ? 'Demo uses only backend sample briefings and illustrative index values.'
              : 'RSS feeds need no key. Full articles open at the publisher. Fear & Greed uses Alternative.me.'}
          </p>
        </div>
        <button className="button primary" disabled={busy || !canSave} type="submit">
          {busy ? <Save size={14} /> : <Check size={14} />}
          {busy ? 'Saving…' : 'Save news sources'}
        </button>
      </Panel>
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
