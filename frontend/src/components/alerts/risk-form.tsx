import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, ShieldAlert } from 'lucide-react';
import { Badge } from '../ui';
import { ExchangeMark } from '../exchange-mark';
import { MarketSourcePicker } from '../market-source-picker';
import { post, refresh } from '../../lib/api';
import type { AccountSelection, Connection, MarketSettings, MarketSource } from '../../lib/types';
import {
  fundsEnvironment,
  riskLabel,
  riskValue,
  type RiskRule,
  type RiskMetric,
} from '../../lib/risk-alerts';

/** A fixed account set and one limit first; recovery/delivery controls stay optional. */
export function RiskForm({
  rule,
  accounts,
  settings,
  initialScope,
  onSaved,
}: {
  rule?: RiskRule;
  accounts: AccountSelection;
  settings: MarketSettings;
  initialScope: string;
  onSaved: () => void;
}) {
  const active = accounts.accounts.filter((a) => a.active);
  const primary = active.filter((a) => !a.sandbox).length
    ? active.filter((a) => !a.sandbox)
    : active;
  const initial =
    rule?.accounts ||
    (initialScope.startsWith('account:')
      ? active.filter((a) => a.id === initialScope.slice(8))
      : initialScope.startsWith('exchange:')
        ? primary.filter((a) => a.exchange === initialScope.slice(9))
        : primary);
  const [environment, setEnvironment] = useState(
    rule?.environment || (initial[0] ? fundsEnvironment(initial[0]) : 'production'),
  );
  const [ids, setIds] = useState(
    rule?.account_ids || (initial.length <= 10 ? initial.map((a) => a.id) : []),
  );
  const choices: Connection[] = [
    ...accounts.accounts,
    ...(rule?.accounts
      .filter((a) => !accounts.accounts.some((current) => current.id === a.id))
      .map((a) => ({ ...a, active: false })) || []),
  ];
  const selectable = choices.filter(
    (a) => fundsEnvironment(a) === environment && (a.active || ids.includes(a.id)),
  );
  const environments = ['production', 'test', 'demo'].filter((env) =>
    choices.some((a) => fundsEnvironment(a) === env && (a.active || ids.includes(a.id))),
  );
  const sourceChoices = (env: string) =>
    settings.catalog.filter((s) => (s.id === 'demo') === (env === 'demo'));
  const initialSources = sourceChoices(environment);
  const [source, setSource] = useState(
    rule?.source ||
      (initialSources.some((s) => s.id === settings.active.id && s.available)
        ? settings.active.id
        : initialSources.find((s) => s.available)?.id || ''),
  );
  const [metric, setMetric] = useState<RiskMetric>(rule?.metric || 'value_floor');
  const [asset, setAsset] = useState(rule?.asset || '');
  const [threshold, setThreshold] = useState(rule ? String(rule.threshold) : '');
  const [reset, setReset] = useState(rule ? String(rule.reset_threshold) : '');
  const [cooldown, setCooldown] = useState(rule?.cooldown_seconds || 300),
    [recovery, setRecovery] = useState(rule?.notify_recovery ?? true);
  const [label, setLabel] = useState(rule?.label || ''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const catalog = sourceChoices(environment);
  if (rule && !catalog.some((s) => s.id === rule.source))
    catalog.push({
      id: rule.source,
      name: rule.source_info.source_label,
      kind: rule.source_info.source_kind,
      provider: rule.source_info.provider,
      environment: rule.source_info.environment,
      available: false,
      requires_key: false,
      has_api_key: false,
      candles: false,
      order_book: false,
    } as MarketSource);
  const fallbackReset =
    threshold && Number(threshold) > 0
      ? metric === 'value_floor'
        ? Number(threshold) * 1.01
        : Math.max(0, Number(threshold) - 1)
      : null;
  return (
    <form
      className="form risk-alert-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError('');
        try {
          await post(rule ? `/risk-alerts/${rule.id}/edit` : '/risk-alerts', {
            account_ids: ids,
            source,
            metric,
            threshold: Number(threshold),
            ...(reset !== '' ? { reset_threshold: Number(reset) } : {}),
            asset: metric === 'concentration' ? asset : '',
            cooldown_seconds: cooldown,
            notify_recovery: recovery,
            label,
            ...(rule ? { revision: rule.revision } : {}),
          });
          onSaved();
        } catch (reason) {
          setError((reason as Error).message);
          refresh();
        } finally {
          setBusy(false);
        }
      }}
    >
      {environments.length > 1 && (
        <label>
          Account environment
          <select
            value={environment}
            disabled={busy}
            onChange={(e) => {
              const env = e.target.value;
              setEnvironment(env);
              const group = active.filter((a) => fundsEnvironment(a) === env);
              setIds(group.length <= 10 ? group.map((a) => a.id) : []);
              setSource(sourceChoices(env).find((s) => s.available)?.id || '');
            }}
          >
            {environments.map((env) => (
              <option key={env} value={env}>
                {env === 'production'
                  ? 'Production funds'
                  : env === 'test'
                    ? 'Test funds'
                    : 'Demo preview'}
              </option>
            ))}
          </select>
        </label>
      )}
      <fieldset className="risk-account-choices">
        <legend>
          Accounts to watch <small>{ids.length}/10 · fixed selection</small>
        </legend>
        {selectable.map((account) => (
          <label
            key={account.id}
            className={`risk-account-option ${ids.includes(account.id) ? 'selected' : ''}`}
          >
            <input
              type="checkbox"
              checked={ids.includes(account.id)}
              disabled={busy || (!ids.includes(account.id) && ids.length >= 10)}
              onChange={(e) =>
                setIds(
                  e.target.checked ? [...ids, account.id] : ids.filter((id) => id !== account.id),
                )
              }
            />
            <ExchangeMark exchange={account.exchange} size={25} />
            <span>
              <strong>{account.label}</strong>
              <small>
                {account.exchange}
                {!account.active ? ' · inactive or disconnected; checks wait' : ''}
              </small>
            </span>
            {account.exchange === 'demo' && <Badge tone="demo">Demo</Badge>}
            {account.sandbox && <Badge tone="peach">Test</Badge>}
          </label>
        ))}
      </fieldset>
      {!selectable.length && (
        <p className="inline-alert">
          Activate one or more exchange accounts in Settings, or explicitly enable Demo there.{' '}
          <Link to="/settings?tab=exchanges">Manage accounts ↗</Link>
        </p>
      )}
      <p className="footnote">
        Choose up to ten accounts per watch. New accounts won’t be added automatically. Test,
        production and Demo funds stay separate.
      </p>
      <MarketSourcePicker
        settings={{ ...settings, catalog }}
        value={source}
        onChange={setSource}
        allowUnavailable={!!rule}
      />
      <label>
        Watch for
        <select
          value={metric}
          disabled={busy}
          onChange={(e) => {
            setMetric(e.target.value as RiskMetric);
            setThreshold('');
            setReset('');
          }}
        >
          <option value="value_floor">Account value at or below a floor</option>
          <option value="concentration">An asset reaching an allocation limit</option>
          <option value="drawdown">Account value falling from an observed peak</option>
        </select>
      </label>
      <div className="form-row">
        {metric === 'concentration' && (
          <label>
            Asset
            <input
              required
              maxLength={24}
              pattern="[A-Z0-9]+"
              placeholder="BTC"
              value={asset}
              disabled={busy}
              onChange={(e) => setAsset(e.target.value.toUpperCase())}
            />
          </label>
        )}
        <label>
          {metric === 'value_floor'
            ? 'Value floor · USDT'
            : metric === 'concentration'
              ? 'Allocation limit · %'
              : 'Drawdown limit · %'}
          <input
            type="number"
            required
            min="0.00000001"
            max={metric === 'value_floor' ? 1e15 : 100}
            step="any"
            placeholder="Enter your limit"
            value={threshold}
            disabled={busy}
            onChange={(e) => setThreshold(e.target.value)}
          />
        </label>
      </div>
      <p className="footnote">
        {metric === 'drawdown'
          ? 'The first positive complete check establishes the peak. Deposits and withdrawals affect this account-value metric; it is not investment return.'
          : metric === 'concentration'
            ? 'Allocation uses the complete selected account value. An unheld asset has 0% weight; an empty wallet has no percentage assessment.'
            : 'Values use observed conversion rates into USDT; USD and other stablecoins are not assumed equal.'}
      </p>
      <details className="risk-advanced">
        <summary>Recovery & notification controls</summary>
        <div className="form-row">
          <label>
            Recovery level · {metric === 'value_floor' ? 'USDT' : '%'}
            <input
              type="number"
              min="0"
              max={metric === 'value_floor' ? 1e16 : 100}
              step="any"
              value={reset}
              disabled={busy}
              placeholder={
                fallbackReset == null
                  ? 'Set a limit first'
                  : String(Number(fallbackReset.toFixed(8)))
              }
              onChange={(e) => setReset(e.target.value)}
            />
          </label>
          <label>
            Minimum time between breaches
            <select
              disabled={busy}
              value={cooldown}
              onChange={(e) => setCooldown(Number(e.target.value))}
            >
              {[...new Set([60, 300, 900, 3600, 21600, 86400, cooldown])]
                .sort((a, b) => a - b)
                .map((s) => (
                  <option value={s} key={s}>
                    {s < 3600
                      ? `${s / 60} ${s === 60 ? 'minute' : 'minutes'}`
                      : `${s / 3600} ${s === 3600 ? 'hour' : 'hours'}`}
                  </option>
                ))}
            </select>
          </label>
        </div>
        <label className="alert-archive-toggle">
          <input
            type="checkbox"
            disabled={busy}
            checked={recovery}
            onChange={(e) => setRecovery(e.target.checked)}
          />{' '}
          Notify when the recovery level is reached
        </label>
        <p className="footnote">
          Recovery{' '}
          {metric === 'value_floor' ? 'must be above the floor' : 'must be below the limit'}.
          Default: {riskValue(fallbackReset, metric)}. A new breach during cooldown needs another
          fresh qualifying check afterward.
        </p>
      </details>
      <label>
        <span>
          Name <small>Optional</small>
        </span>
        <input
          value={label}
          maxLength={80}
          disabled={busy}
          onChange={(e) => setLabel(e.target.value)}
          placeholder={riskLabel(metric, asset)}
        />
      </label>
      <div className="alert-delivery-note">
        <ShieldAlert size={18} />
        <span>
          {rule
            ? 'Changes save paused. Resume resets the peak and incident state.'
            : 'Starting a watch authorizes background spot-balance and quote reads, roughly once a minute.'}{' '}
          Complete fresh valuation is required. No orders or external messages are sent.
        </span>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="price-alert-actions">
        <button
          className="button primary"
          disabled={
            busy || !ids.length || !source || !threshold || (metric === 'concentration' && !asset)
          }
        >
          <ShieldAlert size={15} />
          {busy ? 'Saving…' : rule ? 'Save paused' : 'Start watching'}
        </button>
        <Link className="text-link" to="/settings?tab=exchanges">
          Manage accounts <ArrowUpRight size={12} />
        </Link>
      </div>
    </form>
  );
}
