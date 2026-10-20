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
import type { Connection, ExchangeCatalog, ExchangeProvider } from '../lib/types';
import { ExchangeMark } from './exchange-mark';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from './ui';

function ConnectionForm({ provider, close }: { provider: ExchangeProvider; close: () => void }) {
  const exchange = provider.id;
  const [label, setLabel] = useState(`${provider.name} account`);
  const [apiKey, setApiKey] = useState('');
  const [secret, setSecret] = useState('');
  const [passphrase, setPassphrase] = useState('');
  const [uid, setUid] = useState('');
  const [sandbox, setSandbox] = useState(provider.test_environment);
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
        uid,
      });
      setApiKey('');
      setSecret('');
      setPassphrase('');
      setUid('');
      refresh();
      toast(
        provider.simulated
          ? 'Demo account connected.'
          : 'Connection saved. Use Check access to verify credentials.',
      );
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
          {provider.test_environment
            ? 'Use API credentials created in this test environment. This account holds test funds only.'
            : provider.simulated
              ? 'Explore with simulated funds and sample prices. No API keys are needed.'
              : 'Create a dedicated read-only key. Enable balance access and disable trading and withdrawals.'}
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
      {provider.credentials_required && (
        <>
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
        </>
      )}
      {provider.passphrase && (
        <label>
          API passphrase
          <input
            required
            type="password"
            value={passphrase}
            onChange={(event) => setPassphrase(event.target.value)}
            autoComplete="off"
          />
        </label>
      )}
      {provider.uid && (
        <label>
          API memo
          <input
            required
            type="password"
            value={uid}
            onChange={(event) => setUid(event.target.value)}
            autoComplete="off"
          />
        </label>
      )}
      {provider.sandbox && !provider.test_environment && (
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={sandbox}
            onChange={(event) => setSandbox(event.target.checked)}
          />
          Use sandbox / testnet credentials
        </label>
      )}
      <p className="footnote">
        {provider.account}. {provider.note}.
        {provider.id === 'coinbase-sandbox' &&
          ' Use Coinbase Exchange sandbox credentials, rather than Advanced Trade CDP keys.'}
      </p>
      {provider.setup_url && (
        <a className="text-link" href={provider.setup_url} target="_blank" rel="noreferrer">
          Open {provider.name} to create API keys <ArrowUpRight size={13} />
        </a>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <button type="submit" className="button primary full-width" disabled={busy}>
        <KeyRound size={15} />
        {busy
          ? 'Saving…'
          : provider.simulated
            ? 'Connect demo account'
            : 'Save encrypted connection'}
      </button>
      <p className="footnote">
        {provider.simulated
          ? 'Your demo wallet is saved locally. Reconnecting keeps its existing balances and paper trades.'
          : 'Credentials are encrypted on your server and cannot be retrieved through the API. Saved connections are verified separately.'}
      </p>
    </form>
  );
}

export function ExchangeConnections() {
  const connections = useResource<Connection[]>('/connections');
  const catalog = useResource<ExchangeCatalog>('/exchanges');
  const exchanges = catalog.data?.items ?? [];
  const [query, setQuery] = useState('');
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
      <div className="exchange-catalog-heading">
        <label className="exchange-search">
          Find an exchange
          <input
            type="search"
            placeholder="Search exchanges…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <span className="muted">
          {exchanges.filter((provider) => !provider.simulated && !provider.test_environment).length}{' '}
          exchanges · {exchanges.filter((provider) => provider.test_environment).length} test
          environments · {exchanges.filter((provider) => provider.simulated).length} demo
        </span>
      </div>
      {catalog.loading ? (
        <Loading />
      ) : catalog.error ? (
        <ErrorState message={catalog.error} retry={catalog.retry} />
      ) : (
        <div className="exchange-client-grid">
          {exchanges
            .filter((provider) =>
              `${provider.name} ${provider.id}`.toLowerCase().includes(query.trim().toLowerCase()),
            )
            .map((provider) => (
              <button
                key={provider.id}
                className="exchange-client-option"
                aria-label={`Connect ${provider.name}`}
                disabled={
                  provider.simulated &&
                  connections.data?.some((connection) => connection.exchange === 'demo')
                }
                onClick={() => setSelected(provider.id)}
              >
                <span
                  className={`provider-logo small-logo ${provider.simulated ? 'demo-exchange-mark' : ''}`}
                >
                  <ExchangeMark exchange={provider.id} />
                </span>
                <span>
                  <strong>{provider.name}</strong>
                  <small>
                    {provider.simulated
                      ? connections.data?.some((connection) => connection.exchange === 'demo')
                        ? 'Account connected'
                        : 'Simulated funds · no keys'
                      : provider.test_environment
                        ? provider.id === 'binance-testnet'
                          ? 'Spot test network · test keys'
                          : 'Exchange API · key, secret & passphrase'
                        : provider.id === 'coinbase'
                          ? 'CDP key & PEM'
                          : provider.passphrase
                            ? 'Key, secret & passphrase'
                            : provider.uid
                              ? 'Key, secret & memo'
                              : 'API key & secret'}
                  </small>
                </span>
                {provider.simulated ? (
                  <Badge tone="demo">Demo</Badge>
                ) : provider.test_environment ? (
                  <Badge tone="purple">
                    {provider.id === 'binance-testnet' ? 'Testnet' : 'Sandbox'}
                  </Badge>
                ) : (
                  <Plus size={15} />
                )}
              </button>
            ))}
          {exchanges.length > 0 &&
            !exchanges.some((provider) =>
              `${provider.name} ${provider.id}`.toLowerCase().includes(query.trim().toLowerCase()),
            ) && <p className="muted">No matching exchange.</p>}
        </div>
      )}
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
              <span
                className={`provider-logo small-logo ${connection.exchange === 'demo' ? 'demo-exchange-mark' : ''}`}
              >
                <ExchangeMark exchange={connection.exchange} />
              </span>
              <div className="account-description">
                <strong>{connection.label}</strong>
                <small>
                  {connection.exchange === 'demo'
                    ? 'Simulated funds'
                    : `${exchanges.find((provider) => provider.id === connection.exchange)?.name ?? connection.exchange} · ${connection.sandbox ? 'test funds' : 'production'}`}{' '}
                  · saved {new Date(connection.created_at).toLocaleDateString()}
                </small>
                {checks[connection.id]?.message && (
                  <small className="negative">{checks[connection.id].message}</small>
                )}
              </div>
              {connection.exchange === 'demo' && <Badge tone="demo">Demo</Badge>}
              {connection.sandbox && (
                <Badge tone="purple">
                  {connection.exchange === 'binance-testnet' || connection.exchange === 'binance'
                    ? 'Testnet'
                    : 'Sandbox'}
                </Badge>
              )}
              <Badge
                tone={
                  connection.exchange === 'demo' || checks[connection.id]?.status === 'connected'
                    ? 'lime'
                    : checks[connection.id]?.status === 'error'
                      ? 'rose'
                      : 'neutral'
                }
              >
                {connection.exchange === 'demo' || checks[connection.id]?.status === 'connected' ? (
                  <>
                    <Check size={11} />
                    {connection.exchange === 'demo' ? 'Connected' : 'Verified'}
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
                {connection.exchange === 'demo' ? 'Check account' : 'Check access'}
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
          <Link to="/settings?tab=market" className="text-link">
            View workspace configuration <ArrowUpRight size={13} />
          </Link>
        </Panel>
      </div>
      {selected && exchanges.find((provider) => provider.id === selected) && (
        <Modal
          title={`Connect ${exchanges.find((exchange) => exchange.id === selected)?.name}`}
          onClose={() => setSelected(undefined)}
        >
          <ConnectionForm
            provider={exchanges.find((provider) => provider.id === selected)!}
            close={() => setSelected(undefined)}
          />
        </Modal>
      )}
      {removing && (
        <Modal title="Disconnect this account?" onClose={() => setRemoving(undefined)}>
          <p className="muted">
            {removing.exchange === 'demo'
              ? `Disconnect ${removing.label} from this workspace. Its paper balances and trades are retained for reconnection.`
              : `Remove ${removing.label} and its encrypted credentials from this workspace. Your exchange account is unaffected.`}
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
