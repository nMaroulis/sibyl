import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  Check,
  KeyRound,
  Network,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { api, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Connection } from '../lib/types';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from './ui';

const exchanges = [
  {
    id: 'binance',
    name: 'Binance',
    mark: '◇',
    color: '#e9c855',
    description: 'Bring your spot balances into one view.',
    note: 'API key + secret · optional testnet',
  },
  {
    id: 'coinbase',
    name: 'Coinbase',
    mark: 'C',
    color: '#7e9cf5',
    description: 'Connect your Advanced Trade account.',
    note: 'CDP API key name + private key',
  },
  {
    id: 'kraken',
    name: 'Kraken',
    mark: '∩',
    color: '#bba4ed',
    description: 'A considered view of your Kraken assets.',
    note: 'API key + secret · read-only access',
  },
];

function ConnectionForm({ exchange, close }: { exchange: string; close: () => void }) {
  const [label, setLabel] = useState(
    `${exchanges.find((item) => item.id === exchange)?.name} account`,
  );
  const [apiKey, setApiKey] = useState('');
  const [secret, setSecret] = useState('');
  const [passphrase, setPassphrase] = useState('');
  const [sandbox, setSandbox] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      await post('/connections', {
        exchange,
        label,
        api_key: apiKey.trim(),
        secret: secret.trim(),
        passphrase,
        sandbox,
      });
      setApiKey('');
      setSecret('');
      setPassphrase('');
      refresh();
      toast('Connection saved. Use Check access to verify credentials.');
      close();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      className="form"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="form-callout">
        <ShieldCheck size={18} />
        <p>
          Create a dedicated read-only key. Enable balance access and disable trading and
          withdrawals.
        </p>
      </div>
      <label>
        Account label
        <input
          required
          maxLength={60}
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          autoComplete="off"
        />
      </label>
      <label>
        {exchange === 'coinbase' ? 'CDP API key name' : 'API key'}
        <input
          required
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      <label>
        {exchange === 'coinbase' ? 'Private key (PEM)' : 'API secret'}
        <textarea
          required
          rows={exchange === 'coinbase' ? 4 : 2}
          value={secret}
          onChange={(event) => setSecret(event.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      <details className="advanced-options">
        <summary>Advanced options</summary>
        <label>
          Passphrase, if required
          <input
            type="password"
            value={passphrase}
            onChange={(event) => setPassphrase(event.target.value)}
            autoComplete="off"
          />
        </label>
        {exchange === 'binance' && (
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={sandbox}
              onChange={(event) => setSandbox(event.target.checked)}
            />
            Use Binance testnet credentials
          </label>
        )}
        <p className="footnote">
          Coinbase and Kraken sandbox behavior varies. This form enables sandbox mode only for
          Binance.
        </p>
      </details>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <button type="submit" className="button primary full-width" disabled={busy}>
        <KeyRound size={15} />
        {busy ? 'Encrypting and saving…' : 'Save encrypted connection'}
      </button>
      <p className="footnote">
        Credentials are encrypted on your server and cannot be retrieved through the API. Saved
        connections are verified separately.
      </p>
    </form>
  );
}

export function ExchangeConnections() {
  const connections = useResource<Connection[]>('/connections');
  const [selected, setSelected] = useState<string>();
  const [removing, setRemoving] = useState<Connection>();
  const [busy, setBusy] = useState('');
  const [checks, setChecks] = useState<
    Record<string, { status: string; message?: string; assets?: number }>
  >({});
  const toast = useToast();
  const check = async (id: string) => {
    setBusy(id);
    try {
      const result = await post<{
        status: string;
        message?: string;
        assets?: number;
      }>(`/connections/${id}/check`);
      setChecks((old) => ({ ...old, [id]: result }));
      toast(
        result.status === 'connected'
          ? `Connection verified · ${result.assets} assets found.`
          : result.message || 'Connection check failed.',
        result.status !== 'connected',
      );
    } catch (reason) {
      toast((reason as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  const remove = async () => {
    if (!removing) return;
    setBusy(removing.id);
    try {
      await api(`/connections/${removing.id}`, { method: 'DELETE' });
      setRemoving(undefined);
      refresh();
      toast('Connection removed from this workspace.');
    } catch (reason) {
      toast((reason as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  return (
    <>
      <div className="settings-section-intro">
        <div>
          <h2>Exchange accounts</h2>
          <p>Connect your accounts and verify access, all in one place.</p>
        </div>
        <Badge tone="lime">
          <ShieldCheck size={12} /> Locally encrypted
        </Badge>
      </div>
      <div className="connection-provider-grid">
        {exchanges.map((exchange) => (
          <Panel key={exchange.id} className="provider-card">
            <div className="provider-top">
              <span
                className="provider-logo"
                style={{
                  background: `${exchange.color}18`,
                  color: exchange.color,
                }}
              >
                {exchange.mark}
              </span>
              <Badge>Read-only</Badge>
            </div>
            <h2>{exchange.name}</h2>
            <p>{exchange.description}</p>
            <small>{exchange.note}</small>
            <button
              className="button secondary full-width"
              onClick={() => setSelected(exchange.id)}
            >
              <Plus size={15} />
              Connect {exchange.name}
            </button>
          </Panel>
        ))}
      </div>
      <Panel className="full-panel">
        <PanelTitle
          title="Connected accounts"
          subtitle="Save credentials, then verify access with your exchange"
          action={<Badge>{connections.data?.length ?? 0} saved</Badge>}
        />
        {connections.loading ? (
          <Loading />
        ) : connections.error ? (
          <ErrorState message={connections.error} retry={connections.retry} />
        ) : connections.data?.length ? (
          connections.data.map((connection) => (
            <div className="connection-account" key={connection.id}>
              <span className="provider-logo small-logo">
                {exchanges.find((exchange) => exchange.id === connection.exchange)?.mark}
              </span>
              <div className="account-description">
                <strong>{connection.label}</strong>
                <small>
                  {connection.exchange} · {connection.sandbox ? 'sandbox' : 'production'} · saved{' '}
                  {new Date(connection.created_at).toLocaleDateString()}
                </small>
                {checks[connection.id]?.message && (
                  <small className="negative">{checks[connection.id].message}</small>
                )}
              </div>
              <Badge
                tone={
                  checks[connection.id]?.status === 'connected'
                    ? 'lime'
                    : checks[connection.id]?.status === 'error'
                      ? 'rose'
                      : 'neutral'
                }
              >
                {checks[connection.id]?.status === 'connected' ? (
                  <>
                    <Check size={11} />
                    Verified
                  </>
                ) : checks[connection.id]?.status === 'error' ? (
                  'Check failed'
                ) : (
                  'Saved · unverified'
                )}
              </Badge>
              <button
                className="button secondary tiny"
                disabled={!!busy}
                onClick={() => check(connection.id)}
              >
                <RefreshCw size={13} className={busy === connection.id ? 'spin' : ''} />
                Check access
              </button>
              <button
                className="icon-button danger"
                disabled={!!busy}
                aria-label={`Disconnect ${connection.label}`}
                onClick={() => setRemoving(connection)}
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))
        ) : (
          <Empty title="A connected view starts here">
            Choose an exchange above to add your first account. Multiple accounts per exchange are
            supported.
          </Empty>
        )}
      </Panel>
      <div className="connection-notes">
        <Panel>
          <ShieldCheck size={22} />
          <h3>Your keys stay with you.</h3>
          <p>
            Credentials are encrypted using a local vault key. They are used only by the Python
            exchange adapter, and are never passed to Oracle.
          </p>
        </Panel>
        <Panel>
          <Network size={22} />
          <h3>Start with a smaller permission set.</h3>
          <p>
            Balance access is enough. Restrict keys by IP when available. Disconnecting removes the
            saved credentials; revoke the key at your exchange to invalidate it.
          </p>
        </Panel>
        <Panel>
          <ArrowUpRight size={22} />
          <h3>Ready for connected data?</h3>
          <p>
            Demo mode uses your paper wallet. Live data mode reads saved exchange accounts and
            public market prices.
          </p>
          <Link to="/settings?tab=apis" className="text-link">
            View workspace configuration <ArrowUpRight size={13} />
          </Link>
        </Panel>
      </div>
      {selected && (
        <Modal
          title={`Connect ${exchanges.find((exchange) => exchange.id === selected)?.name}`}
          onClose={() => setSelected(undefined)}
        >
          <ConnectionForm exchange={selected} close={() => setSelected(undefined)} />
        </Modal>
      )}
      {removing && (
        <Modal title="Disconnect this account?" onClose={() => setRemoving(undefined)}>
          <p className="muted">
            Remove {removing.label} and its encrypted credentials from this workspace. Your exchange
            account is unaffected.
          </p>
          <div className="modal-actions">
            <button className="button secondary" onClick={() => setRemoving(undefined)}>
              Keep connection
            </button>
            <button className="button rose-button" disabled={!!busy} onClick={remove}>
              Disconnect account
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
