import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowUpRight,
  BookOpen,
  Bot,
  Check,
  Code2,
  KeyRound,
  Network,
  Newspaper,
  ChartNoAxesCombined,
  PlugZap,
  Settings2,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { AgentButton } from '../components/agents';
import { ComingSoon } from '../components/coming-soon';
import { ConfigHelper } from '../components/config-helper';
import { NewsSettings } from '../components/news-settings';
import { ModelSettings } from '../components/model-settings';
import { ExchangeConnections } from '../components/exchange-connections';
import { SectionPanel, SectionTabs } from '../components/section-tabs';
import { Badge, PageTitle, Panel, PanelTitle, useToast } from '../components/ui';
import { setToken } from '../lib/api';
import type { System } from '../lib/types';

const sections = [
  { id: 'exchanges', label: 'Exchanges', icon: PlugZap },
  { id: 'models', label: 'AI models', icon: Bot },
  { id: 'news', label: 'News', icon: Newspaper },
  { id: 'market', label: 'Market data', icon: ChartNoAxesCombined },
  { id: 'workspace', label: 'Workspace', icon: Settings2 },
];

/** One home for accounts, model providers, data sources, and workspace access. */
export function SettingsPage({ system }: { system?: System }) {
  const [search, setSearch] = useSearchParams();
  const requested = search.get('tab') ?? 'exchanges';
  const selected = requested === 'apis' ? 'market' : requested;
  const tab = sections.some((section) => section.id === selected) ? selected : 'exchanges';
  return (
    <>
      <PageTitle
        title="Settings"
        description="Your accounts, agents, and workspace. All connected."
        action={<AgentButton module="technician" />}
      />
      <SectionTabs
        id="settings"
        label="Settings sections"
        items={sections}
        value={tab}
        onChange={(value) => setSearch({ tab: value })}
      />
      <SectionPanel id="settings" value={tab}>
        {/* Keep drafts in memory while switching sections; never persist credentials here. */}
        <div hidden={tab !== 'exchanges'}>
          <ExchangeConnections />
        </div>
        <div hidden={tab !== 'models'}>
          <SectionIntro
            title="A model for your agents"
            description="Choose how your ProtoLink specialists reason with their module tools."
          />
          <ModelSettings />
          <ComingSoon module="settings" />
        </div>
        <div hidden={tab !== 'news'}>
          <SectionIntro
            title="Reporting, from your sources"
            description="Choose publishers, web collectors, API connections, or the offline demo."
          />
          <NewsSettings />
        </div>
        <div hidden={tab !== 'market'}>
          <SectionIntro
            title="Market & research data"
            description="Choose a market feed, connect provider keys, and explore the services behind Research."
          />
          {system ? <ConfigHelper /> : <AccessNote />}
          <div className="settings-provider-grid">
            {[
              {
                title: 'mempool.space',
                type: 'Public API',
                copy: 'Bitcoin blocks and network activity in Research. No API key required.',
              },
              {
                title: 'CoinPaprika',
                type: 'Public API',
                copy: 'Project profiles, fundamentals, and market snapshots in Research. No API key required.',
              },
              {
                title: 'Wikipedia',
                type: 'Public API',
                copy: 'Attributed background and history excerpts for Crypto profiles. No API key required.',
              },
              {
                title: 'Yahoo Finance',
                type: 'Optional extra',
                copy: 'Equity research through yfinance. Install the Python stocks extra to enable the live provider.',
              },
            ].map((provider) => (
              <Panel key={provider.title}>
                <div className="settings-provider-heading">
                  <Network size={19} />
                  <Badge>{provider.type}</Badge>
                </div>
                <h3>{provider.title}</h3>
                <p>{provider.copy}</p>
              </Panel>
            ))}
          </div>
          <p className="footnote">
            Project profiles use CoinPaprika and Wikipedia public endpoints. Blocks and equities use
            their own labeled demo/live sources. Configure publishers and news API credentials in
            the News tab.
          </p>
        </div>
        <div hidden={tab !== 'workspace'}>
          <WorkspaceSettings system={system} />
        </div>
      </SectionPanel>
    </>
  );
}

function SectionIntro({ title, description }: { title: string; description: string }) {
  return (
    <div className="settings-section-intro">
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
    </div>
  );
}

function AccessNote() {
  return (
    <Panel className="full-panel">
      <p className="muted">
        Server configuration is unavailable. Check API connectivity and your access token in{' '}
        <Link className="text-link" to="/settings?tab=workspace">
          Workspace
        </Link>
        .
      </p>
    </Panel>
  );
}

function WorkspaceSettings({ system }: { system?: System }) {
  const [token, setDraftToken] = useState('');
  const [saved, setSaved] = useState(false);
  const toast = useToast();
  return (
    <>
      <SectionIntro
        title="Make yourself at home"
        description="Session access, server configuration, and useful links."
      />
      <div className="settings-grid">
        <Panel>
          <PanelTitle title="Workspace configuration" subtitle="Current server settings" />
          <div className="stat-list settings-list">
            <div>
              <span>Application</span>
              <strong>Sibyl {system?.version ?? '—'}</strong>
            </div>
            <div>
              <span>Active accounts</span>
              <Badge tone={system?.accounts?.mode === 'demo' ? 'demo' : 'neutral'}>
                {system?.accounts?.mode === 'demo'
                  ? 'Demo preview'
                  : system?.accounts?.mode === 'test'
                    ? 'Test accounts'
                    : `${system?.accounts?.active_ids.length ?? 0} exchange accounts`}
              </Badge>
            </div>
            <div>
              <span>Market source</span>
              <strong>{system?.market_source?.name ?? system?.market_exchange ?? '—'}</strong>
            </div>
            <div>
              <span>Order execution</span>
              <Badge>
                {system
                  ? system.allow_live_trading
                    ? 'Manual exchange orders enabled'
                    : 'Exchange execution disabled'
                  : 'Unavailable'}
              </Badge>
            </div>
            <div>
              <span>Agent engine</span>
              <strong>ProtoLink · {system?.agents ?? '—'} specialists</strong>
            </div>
            <div>
              <span>Language model</span>
              <strong>
                {system?.llm_provider === 'none'
                  ? 'Tool mode · no model'
                  : (system?.llm_provider ?? '—')}
              </strong>
            </div>
            {system?.llm_model && (
              <div>
                <span>Model</span>
                <strong>{system.llm_model}</strong>
              </div>
            )}
          </div>
          <p className="footnote padded">
            Server environment settings apply after restarting the API. Paper strategies always use
            isolated virtual accounts.
          </p>
        </Panel>
        <Panel>
          <PanelTitle title="Workspace access" subtitle="For a server protected by an API token" />
          <form
            className="form"
            onSubmit={(event) => {
              event.preventDefault();
              setToken(token.trim());
              setDraftToken('');
              setSaved(true);
              toast('Workspace access token updated for this browser session.');
            }}
          >
            <div className="form-callout">
              <KeyRound size={18} />
              <p>
                Your access token is kept in this tab’s browser session. Manage exchange credentials
                in Exchanges.
              </p>
            </div>
            <label>
              Workspace API token
              <input
                type="password"
                value={token}
                onChange={(event) => {
                  setDraftToken(event.target.value);
                  setSaved(false);
                }}
                autoComplete="off"
                placeholder="Enter the token configured on your server"
              />
            </label>
            <button className="button primary" type="submit">
              {saved ? <Check size={15} /> : <KeyRound size={15} />}Save access token
            </button>
            <button
              className="text-button"
              type="button"
              onClick={() => {
                setToken('');
                setDraftToken('');
                setSaved(false);
                toast('Browser session token cleared.');
              }}
            >
              Clear session token
            </button>
          </form>
        </Panel>
        <Panel className="settings-resources">
          <PanelTitle title="Built to be understood" subtitle="Documentation and developer tools" />
          <div className="settings-links">
            <a href="http://localhost:3000/sibyl/" target="_blank" rel="noreferrer">
              <BookOpen size={19} />
              <span>
                <strong>Read the documentation</strong>
                <small>Setup, modules, agents, and extension guides</small>
              </span>
              <ArrowUpRight size={15} />
            </a>
            <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">
              <Code2 size={19} />
              <span>
                <strong>Explore the API</strong>
                <small>Interactive OpenAPI reference</small>
              </span>
              <ArrowUpRight size={15} />
            </a>
            <a href="https://github.com/nMaroulis/protolink" target="_blank" rel="noreferrer">
              <Sparkles size={19} />
              <span>
                <strong>Meet the engine</strong>
                <small>ProtoLink agent framework</small>
              </span>
              <ArrowUpRight size={15} />
            </a>
            <div className="settings-security">
              <ShieldCheck size={16} />
              <p>
                Local SQLite storage. Encrypted exchange secrets. Read-only agent tools. Your
                workspace belongs to you.
              </p>
            </div>
          </div>
        </Panel>
      </div>
    </>
  );
}
