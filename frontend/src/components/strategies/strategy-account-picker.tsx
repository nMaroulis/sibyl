import { Database, FlaskConical } from 'lucide-react';
import type { Connection } from '../../lib/types';
import { ExchangeMark } from '../exchange-mark';
import { SearchPicker, type PickerGroup } from '../search-picker';
import { Badge } from '../ui';

export type StrategyAccount = Connection & { provider_name: string; supported: boolean };

export type StrategyExecutionOptions = {
  enabled: boolean;
  server_enabled: boolean;
  controls: { halted: boolean };
  accounts: StrategyAccount[];
  handoff_sources: {
    id: string;
    connection_id: string;
    symbol: string;
    quantity: number;
    cost_basis: number;
  }[];
};

/** Choose the account's exact feed before selecting a strategy or a run mode. */
export function StrategyAccountPicker({
  accounts,
  demo,
  loading,
  value,
  onChange,
}: {
  accounts: StrategyAccount[];
  demo: boolean;
  loading: boolean;
  value: string;
  onChange: (id: string) => void;
}) {
  if (demo) {
    return (
      <div className="strategy-demo-selection">
        <FlaskConical size={19} aria-hidden="true" />
        <strong>Demo account</strong>
        <Badge tone="sand">Simulated funds</Badge>
      </div>
    );
  }
  const groups: PickerGroup[] = [false, true].map((sandbox) => ({
    label: sandbox ? 'Test environments' : 'Production',
    options: accounts
      .filter((account) => account.sandbox === sandbox)
      .map((account) => ({
        value: account.id,
        label: account.label,
        description:
          (account.label === account.provider_name ? 'Spot account' : account.provider_name) +
          (account.supported ? '' : ' · research and paper'),
        keywords: account.exchange + (sandbox ? ' sandbox testnet' : ' production'),
        icon: (
          <span className="strategy-account-mark">
            <ExchangeMark exchange={account.exchange} size={22} />
          </span>
        ),
        badge: (
          <Badge tone={sandbox ? 'sand' : 'rose'}>{sandbox ? 'Test funds' : 'Real funds'}</Badge>
        ),
      })),
  }));
  groups.push({
    label: 'Research without an account',
    options: [
      {
        value: 'workspace-feed',
        label: 'Workspace market feed',
        description: 'Backtests and paper strategies',
        icon: (
          <span className="strategy-account-mark">
            <Database size={17} aria-hidden="true" />
          </span>
        ),
      },
    ],
  });
  return (
    <SearchPicker
      className="strategy-account-picker"
      menuClassName="strategy-account-menu"
      label="Account or feed"
      value={value}
      groups={groups}
      loading={loading}
      onChange={onChange}
      placeholder="Search accounts or exchanges…"
      messages={{
        prompt: 'Choose an exchange account or a market feed',
        loading: 'Loading exchange accounts…',
        empty: 'No accounts or feeds match your search.',
      }}
    />
  );
}
