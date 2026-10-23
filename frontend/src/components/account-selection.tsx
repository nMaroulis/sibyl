import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, FlaskConical, Layers3, Plus, Power } from 'lucide-react';
import { post, refresh, number } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { AccountSelection, Portfolio } from '../lib/types';
import { ExchangeMark } from './exchange-mark';
import { SearchPicker } from './search-picker';
import { Badge, Panel, useToast } from './ui';

export const useAccounts = () => useResource<AccountSelection>('/accounts', 30000);

/** First-use state: exchange connections are primary; Demo is an explicit preview. */
export function AccountSetup({
  selection,
  page = 'account',
  description,
}: {
  selection: AccountSelection;
  page?: string;
  description?: string;
}) {
  const [busy, setBusy] = useState('');
  const toast = useToast();
  const activate = async (id: string) => {
    setBusy(id);
    try {
      await post(
        id === 'demo' ? '/accounts/demo' : `/connections/${id}/activation`,
        id === 'demo' ? undefined : { active: true },
      );
      refresh();
    } catch (error) {
      toast((error as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  return (
    <Panel className="account-onboarding">
      <span className="account-onboarding-icon">
        <Layers3 size={28} />
      </span>
      <Badge>No active accounts</Badge>
      <h2>Your exchanges. One connected view.</h2>
      <p>
        {description ??
          `Connect one or many exchange accounts to use your ${page}. See balances across all exchanges together, or focus on a single exchange or account.`}
      </p>
      <Link className="button primary" to="/settings?tab=exchanges">
        <Plus size={16} /> Connect exchange accounts
      </Link>
      {selection.accounts.some((account) => account.exchange !== 'demo') && (
        <div className="account-saved-choices">
          <span>Or activate a saved account</span>
          {selection.accounts
            .filter((account) => account.exchange !== 'demo')
            .map((account) => (
              <button
                className="button secondary"
                key={account.id}
                disabled={!!busy}
                onClick={() => activate(account.id)}
              >
                <ExchangeMark exchange={account.exchange} size={20} /> {account.label}{' '}
                {account.sandbox && <Badge tone="purple">Test funds</Badge>}{' '}
                <ArrowRight size={13} />
              </button>
            ))}
        </div>
      )}
      <div className="account-demo-invitation">
        <FlaskConical size={17} />
        <div>
          <strong>Just exploring?</strong>
          <span>Preview the app with a virtual Demo wallet. No keys needed.</span>
        </div>
        <button
          className="text-button"
          disabled={!!busy || !selection.demo_available}
          onClick={() => activate('demo')}
        >
          {busy === 'demo' ? 'Opening…' : 'Preview with Demo'} <ArrowRight size={13} />
        </button>
      </div>
    </Panel>
  );
}

/** Keep sample/test funds unmistakable without labeling public market data as Demo. */
export function AccountContext({
  selection,
  demoDescription = 'These are virtual balances. Activating an exchange account turns Demo off automatically.',
}: {
  selection: AccountSelection;
  demoDescription?: string;
}) {
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  if (selection.mode !== 'demo' && selection.mode !== 'test') return null;
  return (
    <div
      className={`account-context-banner ${selection.mode === 'demo' ? 'demo-preview' : 'test-preview'}`}
    >
      <FlaskConical size={21} />
      <div>
        <strong>
          {selection.mode === 'demo' ? 'Demo preview is active' : 'Test accounts are active'}
        </strong>
        <span>
          {selection.mode === 'demo'
            ? demoDescription
            : 'These accounts contain test funds. They are never added to production totals.'}
        </span>
      </div>
      {selection.mode === 'demo' && (
        <button
          className="text-button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await post('/connections/demo/activation', { active: false });
              refresh();
            } catch (error) {
              toast((error as Error).message, true);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Power size={13} /> Exit preview
        </button>
      )}
      <Link className="text-link" to="/settings?tab=exchanges">
        {selection.mode === 'demo' ? 'Connect your exchanges' : 'Manage accounts'}{' '}
        <ArrowRight size={13} />
      </Link>
    </div>
  );
}

export function PortfolioScope({
  selection,
  scope,
  onChange,
}: {
  selection: AccountSelection;
  scope: string;
  onChange: (scope: string) => void;
}) {
  return (
    <div className="portfolio-scope-bar">
      <SearchPicker
        label="Account view"
        value={scope}
        onChange={onChange}
        placeholder="Find an exchange or account…"
        groups={[
          {
            label: 'Combined',
            options: selection.scopes
              .filter((item) => item.kind === 'combined')
              .map((item) => ({
                value: item.id,
                label: item.label,
                description: `${item.count} active ${item.count === 1 ? 'account' : 'accounts'} · ${selection.mode === 'test' ? 'test funds' : selection.mode === 'demo' ? 'virtual funds' : 'production funds'}`,
                icon: <Layers3 size={20} />,
              })),
          },
          {
            label: 'By exchange',
            options: selection.scopes
              .filter((item) => item.kind === 'exchange')
              .map((item) => ({
                value: item.id,
                label: item.label.charAt(0).toUpperCase() + item.label.slice(1),
                description: `${item.count} active ${item.count === 1 ? 'account' : 'accounts'}`,
                icon: <ExchangeMark exchange={item.exchange!} size={24} />,
              })),
          },
          {
            label: 'Individual accounts',
            options: selection.scopes
              .filter((item) => item.kind === 'account')
              .map((item) => ({
                value: item.id,
                label: item.label,
                description: item.sandbox
                  ? 'Test funds · separate view'
                  : item.exchange === 'demo'
                    ? 'Virtual funds'
                    : item.exchange,
                icon: <ExchangeMark exchange={item.exchange!} size={24} />,
                badge: item.sandbox ? <Badge tone="purple">Test</Badge> : undefined,
              })),
          },
        ]}
      />
      <p>
        Choose a combined view or drill into an exchange or account.{' '}
        <Link to="/settings?tab=exchanges">
          Manage active accounts <ArrowRight size={12} />
        </Link>
      </p>
    </div>
  );
}

/** Account totals explain the constituents of a combined portfolio. */
export function PortfolioAccounts({
  portfolio,
  select,
}: {
  portfolio: Portfolio;
  select: (scope: string) => void;
}) {
  return (
    <div className="portfolio-account-cards">
      {portfolio.venues.map((account) => (
        <button
          key={account.id}
          className="portfolio-account-card"
          onClick={() => select(`account:${account.id}`)}
        >
          <ExchangeMark exchange={account.exchange} size={25} />
          <span>
            <strong>{account.name}</strong>
            <small>
              {account.sandbox
                ? 'Test funds'
                : account.exchange === 'demo'
                  ? 'Virtual funds'
                  : account.exchange}{' '}
              · {account.assets} assets
            </small>
          </span>
          <span className="portfolio-account-value">
            <strong className="monetary">
              {account.total === null ? 'Unavailable' : `${number(account.total)} USDT`}
            </strong>
            {account.unpriced > 0 && <small>{account.unpriced} unpriced</small>}
          </span>
          <ArrowRight size={13} />
        </button>
      ))}
    </div>
  );
}
