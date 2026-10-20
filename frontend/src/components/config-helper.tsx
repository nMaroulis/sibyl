import { useState } from 'react';
import { Check, Download, Radio } from 'lucide-react';
import { Badge, ErrorState, Loading, Panel, PanelTitle, useToast } from './ui';
import { post, refresh } from '../lib/api';
import type { ExchangeCatalog, MarketSettings } from '../lib/types';
import { useResource } from '../lib/hooks';

/** Save the next public price source without relabeling in-flight quotes. */
export function ConfigHelper() {
  const settings = useResource<MarketSettings>('/settings/market');
  const providers = useResource<ExchangeCatalog>('/exchanges');
  if (settings.error) return <ErrorState message={settings.error} retry={settings.retry} />;
  if (!settings.data) return <Loading />;
  return <MarketSourceForm initial={settings.data} providers={providers.data} />;
}

function MarketSourceForm({
  initial,
  providers,
}: {
  initial: MarketSettings;
  providers?: ExchangeCatalog;
}) {
  const [mode, setMode] = useState(initial.saved.mode);
  const [exchange, setExchange] = useState(initial.saved.exchange);
  const [saved, setSaved] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const snippet = `SIBYL_MODE=${mode}\nSIBYL_MARKET_EXCHANGE=${exchange}\n`;
  const download = () => {
    const link = document.createElement('a');
    const object = URL.createObjectURL(new Blob([snippet], { type: 'text/plain' }));
    link.href = object;
    link.download = 'sibyl-data.env';
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(object), 1000);
  };
  return (
    <Panel className="full-panel settings-config">
      <PanelTitle
        title="Prices & market history"
        subtitle={`Running source: ${saved.active.mode === 'demo' ? 'Demo client' : saved.active.exchange}`}
        action={
          <Badge tone={saved.restart_required ? 'sand' : 'lime'}>
            {saved.restart_required ? 'Restart pending' : 'Active'}
          </Badge>
        }
      />
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError('');
          try {
            const result = await post<MarketSettings>('/settings/market', { mode, exchange });
            setSaved(result);
            refresh();
            toast(
              result.restart_required
                ? 'Market source saved. Restart the API to apply it.'
                : 'Market source saved.',
            );
          } catch (reason) {
            setError((reason as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="workspace-controls">
          <label>
            Market mode
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as MarketSettings['saved']['mode'])}
            >
              <option value="demo">Demo client · offline prices</option>
              <option value="live">Public exchange prices</option>
            </select>
          </label>
          <label>
            Reference exchange
            <select value={exchange} onChange={(e) => setExchange(e.target.value)}>
              {(
                providers?.items.filter((p) => !p.simulated && !p.test_environment) ?? [
                  { id: exchange, name: exchange },
                ]
              ).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="config-preview">
          <p className="footnote">
            <Radio size={14} />
            Public quotes and candles use this source. Saved changes apply on the next API restart;
            they do not enable order execution. Private account data uses each connected exchange.
          </p>
          <button className="button primary" disabled={busy} type="submit">
            <Check size={14} />
            {busy ? 'Saving…' : 'Save market source'}
          </button>
          <details className="settings-snippet">
            <summary>Environment configuration</summary>
            <p className="footnote">
              Saved workspace choices take precedence over environment defaults. Use the form above
              to update an existing saved selection.
            </p>
            <pre>{snippet}</pre>
            <button className="button secondary" type="button" onClick={download}>
              <Download size={14} />
              Download data configuration
            </button>
          </details>
          {error && (
            <p role="alert" className="error-message">
              {error}
            </p>
          )}
        </div>
      </form>
    </Panel>
  );
}
