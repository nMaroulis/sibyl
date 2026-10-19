import { useState } from 'react';
import { Download } from 'lucide-react';
import { Panel, PanelTitle } from './ui';
import type { System } from '../lib/types';

/** Market settings remain an explicit server edit; model settings have their own live editor. */
export function ConfigHelper({ system }: { system: System }) {
  const [mode, setMode] = useState(system.mode);
  const [exchange, setExchange] = useState(system.market_exchange);
  const snippet = `# Merge into your server .env, then restart the API.\nSIBYL_MODE=${mode}\nSIBYL_MARKET_EXCHANGE=${exchange}\n`;
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
        title="Market data configuration"
        subtitle="Prepare an environment snippet for your server"
      />
      <div className="workspace-controls">
        <label>
          Market mode
          <select value={mode} onChange={(event) => setMode(event.target.value as System['mode'])}>
            <option value="demo">Demo fixtures</option>
            <option value="live">Live providers</option>
          </select>
        </label>
        <label>
          Reference exchange
          <select value={exchange} onChange={(event) => setExchange(event.target.value)}>
            {['binance', 'coinbase', 'kraken'].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="config-preview">
        <p className="footnote">
          Downloading does not change the running server. Merge the snippet into your existing .env
          and restart the API. Exchange execution permissions are configured separately.
        </p>
        <details className="settings-snippet">
          <summary>Preview environment snippet</summary>
          <pre>{snippet}</pre>
        </details>
        <button className="button secondary" onClick={download}>
          <Download size={14} /> Download data configuration
        </button>
      </div>
    </Panel>
  );
}
