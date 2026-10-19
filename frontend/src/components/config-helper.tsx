import { useState } from 'react';
import { Download } from 'lucide-react';
import { Panel, PanelTitle } from './ui';
import type { System } from '../lib/types';

/** Generate a scoped, non-secret snippet for an explicit server environment edit. */
export function ConfigHelper({ section, system }: { section: 'models' | 'data'; system: System }) {
  const [mode, setMode] = useState(system.mode);
  const [exchange, setExchange] = useState(system.market_exchange);
  const [provider, setProvider] = useState(system.llm_provider);
  const [model, setModel] = useState(system.llm_model);
  const [url, setUrl] = useState('http://127.0.0.1:11434');
  const clean = (value: string) => JSON.stringify(value.replace(/[\r\n\0]/g, ''));
  const models = section === 'models';
  const snippet =
    '# Merge into your server .env, then restart the API.\n' +
    (models
      ? `SIBYL_LLM_PROVIDER=${provider}\nSIBYL_LLM_MODEL=${clean(model)}\n${['ollama', 'openai-compatible'].includes(provider) ? `SIBYL_LLM_BASE_URL=${clean(url)}\n` : ''}`
      : `SIBYL_MODE=${mode}\nSIBYL_MARKET_EXCHANGE=${exchange}\n`);
  const download = () => {
    const link = document.createElement('a');
    const object = URL.createObjectURL(new Blob([snippet], { type: 'text/plain' }));
    link.href = object;
    link.download = `sibyl-${section}.env`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(object), 1000);
  };
  return (
    <Panel className="full-panel settings-config">
      <PanelTitle
        title={models ? 'Model configuration' : 'Market data configuration'}
        subtitle="Prepare an environment snippet for your server"
      />
      <div className="workspace-controls">
        {models ? (
          <>
            <label>
              Model provider
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                <option value="none">Tool mode · no model</option>
                <option value="ollama">Ollama</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="openai-compatible">OpenAI compatible</option>
              </select>
            </label>
            {provider !== 'none' && (
              <label>
                Model name
                <input
                  value={model}
                  maxLength={200}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="Your installed or provider model"
                />
              </label>
            )}
            {['ollama', 'openai-compatible'].includes(provider) && (
              <label>
                Model server URL
                <input
                  type="url"
                  maxLength={500}
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                />
              </label>
            )}
          </>
        ) : (
          <>
            <label>
              Market mode
              <select value={mode} onChange={(e) => setMode(e.target.value as System['mode'])}>
                <option value="demo">Demo fixtures</option>
                <option value="live">Live providers</option>
              </select>
            </label>
            <label>
              Reference exchange
              <select value={exchange} onChange={(e) => setExchange(e.target.value)}>
                {['binance', 'coinbase', 'kraken'].map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </label>
          </>
        )}
      </div>
      <div className="config-preview">
        <p className="footnote">
          Downloading does not change the running server. Merge the snippet into your existing .env
          and restart the API.
          {models &&
            (provider === 'openai'
              ? ' Set OPENAI_API_KEY on the server.'
              : provider === 'anthropic'
                ? ' Set ANTHROPIC_API_KEY on the server.'
                : provider === 'openai-compatible'
                  ? ' Set OPENAI_COMPATIBLE_API_KEY on the server if your endpoint requires it.'
                  : '')}
          {!models && ' Exchange execution permissions are configured separately.'}
        </p>
        <details className="settings-snippet">
          <summary>Preview environment snippet</summary>
          <pre>{snippet}</pre>
        </details>
        <button className="button secondary" onClick={download}>
          <Download size={14} /> Download {models ? 'model' : 'data'} configuration
        </button>
      </div>
    </Panel>
  );
}
