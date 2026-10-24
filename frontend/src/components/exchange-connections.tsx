import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  CircleHelp,
  Check,
  KeyRound,
  Network,
  Plus,
  Power,
  FlaskConical,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { api, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Connection, ExchangeCatalog, ExchangeProvider, System } from '../lib/types';
import { exchangeCategoryIcons } from '../lib/category-icons';
import { ExchangeProviderCard } from './exchange-provider-card';
import { SectionPanel, SectionTabs } from './section-tabs';
import { ExchangeMark } from './exchange-mark';
import { AccountContext, useAccounts } from './account-selection';
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
              : provider.limit_orders
                ? 'Use a dedicated key with balance and order-history read access. Add spot trading permission only if you want to place manual orders in Trade. Keep withdrawals and wallet transfers disabled.'
                : 'Use a dedicated read-only key for balances and order history. Trading is not enabled for this exchange in Sibyl. Keep withdrawals and wallet transfers disabled.'}
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
      {provider.id === 'bybit' && (
        <p className="footnote">
          Use a Unified Trading Account (UTA). Classic accounts are not supported by this adapter.
        </p>
      )}
      {provider.id === 'kucoin' && (
        <p className="footnote">
          Use a classic spot trading account. KuCoin Unified Trading Accounts are not supported by
          this adapter.
        </p>
      )}
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
          : 'API keys are stored locally and encrypted on the machine running the Python backend. They cannot be retrieved through the API or read by AI agents. Check access verifies balance access separately.'}
      </p>
    </form>
  );
}

/** Feature truth comes from the backend's reviewed app paths, not raw SDK flags. */
function ExchangeDetails({
  provider,
  keyStorage,
  initialSection,
  close,
}: {
  provider: ExchangeProvider;
  keyStorage: string;
  initialSection: string;
  close: () => void;
}) {
  const [section, setSection] = useState(initialSection);
  const [connecting, setConnecting] = useState(false);
  const system = useResource<System>('/system');
  const group = provider.support.find((item) => item.id === section);
  return (
    <div className="exchange-details">
      <div className="exchange-details-intro">
        <span className="provider-logo">
          <ExchangeMark exchange={provider.id} />
        </span>
        <div>
          <strong>{provider.account}</strong>
          <p>{provider.note}</p>
        </div>
        {provider.test_environment && <Badge tone="purple">Test funds</Badge>}
        {provider.simulated && <Badge tone="demo">Demo</Badge>}
      </div>
      {connecting ? (
        <>
          <button className="text-link" onClick={() => setConnecting(false)}>
            ← Back to supported features
          </button>
          <ConnectionForm provider={provider} close={close} />
        </>
      ) : (
        <>
          <p className="footnote">
            Support describes what Sibyl implements. Access still depends on your account, region
            and API permissions. Private accounts and real orders have not been acceptance-tested.
          </p>
          <SectionTabs
            id="exchange-support"
            label="Exchange features"
            compact
            items={provider.support.map((item) => ({
              id: item.id,
              label: item.label,
              icon:
                exchangeCategoryIcons[item.id as keyof typeof exchangeCategoryIcons] ?? CircleHelp,
            }))}
            value={section}
            onChange={setSection}
          />
          <SectionPanel id="exchange-support" value={section}>
            {section === 'spot' && !provider.simulated && (
              <div className="callout exchange-execution-note">
                <strong>
                  {provider.limit_orders
                    ? system.loading
                      ? 'Checking server execution setting…'
                      : system.error
                        ? 'Server execution setting unavailable'
                        : system.data?.allow_live_trading
                          ? 'Manual execution enabled on this server'
                          : 'Manual execution disabled on this server'
                    : 'Trading is not implemented for this exchange'}
                </strong>
                <p>
                  {provider.limit_orders
                    ? 'Supported orders require a trading-enabled key and an explicit review in Trade. Saving a connection or checking access never submits an order.'
                    : 'Connect for account and market reads. A trading-enabled key does not enable pending Sibyl features.'}
                </p>
              </div>
            )}
            <div className="exchange-feature-list">
              {group?.features.map((feature) => (
                <div className="exchange-feature" key={feature.id}>
                  <div>
                    <strong>{feature.label}</strong>
                    <p>{feature.detail}</p>
                  </div>
                  <Badge
                    tone={
                      feature.status === 'available'
                        ? 'lime'
                        : feature.status === 'simulated'
                          ? 'demo'
                          : 'neutral'
                    }
                  >
                    {feature.status === 'available' ? (
                      <>
                        <Check size={11} /> Supported
                      </>
                    ) : feature.status === 'simulated' ? (
                      'Simulated'
                    ) : feature.status === 'pending' ? (
                      'Not implemented'
                    ) : (
                      'Unavailable'
                    )}
                  </Badge>
                </div>
              ))}
            </div>
          </SectionPanel>
          <div className="exchange-details-footer">
            <p className="footnote">
              <ShieldCheck size={14} /> {keyStorage}
            </p>
            <button className="button primary" onClick={() => setConnecting(true)}>
              <Plus size={15} /> Connect {provider.name}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export function ExchangeConnections() {
  const selection = useAccounts();
  const connections = useResource<Connection[]>('/connections');
  const catalog = useResource<ExchangeCatalog>('/exchanges');
  const exchanges = catalog.data?.items ?? [];
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<string>();
  const [selectedSection, setSelectedSection] = useState('account');
  const openExchange = (identity: string, section = 'account') => {
    setSelectedSection(section);
    setSelected(identity);
  };
  const [removing, setRemoving] = useState<Connection>();
  const [busy, setBusy] = useState('');
  const [checks, setChecks] = useState<
    Record<string, { status: string; message?: string; assets?: number }>
  >({});
  const toast = useToast();
  const activate = async (connection: Connection) => {
    setBusy(`activate:${connection.id}`);
    try {
      await post(`/connections/${connection.id}/activation`, { active: !connection.active });
      refresh();
      toast(
        connection.active
          ? 'Account deactivated. Saved credentials and records are retained.'
          : connection.exchange === 'demo'
            ? 'Demo preview is active.'
            : 'Account activated. Demo preview is off.',
      );
    } catch (reason) {
      toast((reason as Error).message, true);
    } finally {
      setBusy('');
    }
  };
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
          <p>Choose an exchange to see supported features, then connect one or more accounts.</p>
        </div>
        <Badge tone="lime">
          <ShieldCheck size={12} /> Locally encrypted
        </Badge>
      </div>
      {catalog.data && (
        <div className="exchange-vault-notice" role="note" aria-label="API key storage">
          <span className="exchange-vault-icon">
            <ShieldCheck size={19} />
          </span>
          <div>
            <strong>Local, encrypted storage</strong>
            <p>{catalog.data.key_storage}</p>
          </div>
        </div>
      )}
      {selection.data && <AccountContext selection={selection.data} />}
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
      <div className="exchange-coverage-legend" aria-label="Implementation coverage legend">
        <span>
          <i className="coverage-supported" /> Full
        </span>
        <span>
          <i className="coverage-partial" /> Partial
        </span>
        <span>
          <i className="coverage-unsupported" /> Not implemented
        </span>
        <p>Listed feature coverage · not account verification. Select an icon for details.</p>
      </div>
      {catalog.loading ? (
        <Loading />
      ) : catalog.error ? (
        <ErrorState message={catalog.error} retry={catalog.retry} />
      ) : (
        <div className="exchange-client-grid" data-card-style="brand">
          {exchanges
            .filter((provider) => !provider.simulated)
            .filter((provider) =>
              `${provider.name} ${provider.id}`.toLowerCase().includes(query.trim().toLowerCase()),
            )
            .map((provider) => (
              <ExchangeProviderCard
                key={provider.id}
                provider={provider}
                onOpen={(section) => openExchange(provider.id, section)}
              />
            ))}
          {exchanges.length > 0 &&
            !exchanges.some((provider) =>
              `${provider.name} ${provider.id}`.toLowerCase().includes(query.trim().toLowerCase()),
            ) && <p className="muted">No matching exchange.</p>}
        </div>
      )}
      <Panel className="full-panel">
        <PanelTitle
          title="Saved accounts"
          subtitle="Active accounts appear in Account and Trade. Deactivating keeps credentials and history."
          action={
            <Badge>
              {selection.data?.active_ids.length ?? 0} active · {connections.data?.length ?? 0}{' '}
              saved
            </Badge>
          }
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
              <button
                className={`account-activation ${connection.active ? 'is-active' : ''}`}
                aria-pressed={connection.active}
                aria-label={`${connection.active ? 'Deactivate' : 'Activate'} ${connection.label}`}
                disabled={
                  !!busy ||
                  (connection.exchange === 'demo' &&
                    !connection.active &&
                    !selection.data?.demo_available)
                }
                onClick={() => activate(connection)}
              >
                <Power size={13} /> {connection.active ? 'Active' : 'Inactive'}
              </button>
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
                className="button secondary tiny"
                onClick={() => openExchange(connection.exchange)}
              >
                Features
              </button>
              <Link
                className="button secondary tiny"
                to={`/trade?tab=history&account=${encodeURIComponent(connection.id)}`}
              >
                Account history <ArrowUpRight size={13} />
              </Link>
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
      {selection.data?.mode !== 'demo' && (
        <Panel className="demo-settings-invitation">
          <FlaskConical size={21} />
          <div>
            <h3>Explore with Demo</h3>
            <p>
              {selection.data?.demo_available
                ? 'An optional virtual wallet to preview Sibyl. Your saved balances are retained when you leave.'
                : 'Demo stays off while exchange accounts are active. Deactivate them first to preview virtual funds.'}
            </p>
          </div>
          <button
            className="button secondary tiny"
            disabled={!!busy || !selection.data?.demo_available}
            onClick={async () => {
              setBusy('demo');
              try {
                await post('/accounts/demo');
                refresh();
                toast('Demo preview is active.');
              } catch (reason) {
                toast((reason as Error).message, true);
              } finally {
                setBusy('');
              }
            }}
          >
            Preview with Demo <ArrowUpRight size={12} />
          </button>
        </Panel>
      )}
      <div className="connection-notes">
        <Panel>
          <ShieldCheck size={22} />
          <h3>Your keys stay with you.</h3>
          <p>
            Credentials are encrypted using a local vault key. They are used only by the Python
            exchange adapter, and are never passed to AI agents.
          </p>
        </Panel>
        <Panel>
          <Network size={22} />
          <h3>Start with a smaller permission set.</h3>
          <p>
            Use read permissions for balances and trade history. Restrict keys by IP when available.
            Disconnecting removes saved credentials and stops imports; retained fills remain in your
            workspace. Revoke the key at your exchange to invalidate it.
          </p>
        </Panel>
        <Panel>
          <ArrowUpRight size={22} />
          <h3>A view across all exchanges.</h3>
          <p>
            Activate several exchange accounts to see combined holdings. Account can focus on one
            exchange or account. Demo turns off automatically when an exchange account is activated.
          </p>
          <Link to="/account" className="text-link">
            Open Account <ArrowUpRight size={13} />
          </Link>
        </Panel>
      </div>
      {selected && exchanges.find((provider) => provider.id === selected) && (
        <Modal
          title={`${exchanges.find((exchange) => exchange.id === selected)?.name}`}
          className="exchange-details-modal"
          onClose={() => setSelected(undefined)}
        >
          <ExchangeDetails
            key={selected}
            initialSection={selectedSection}
            keyStorage={catalog.data?.key_storage ?? ''}
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
