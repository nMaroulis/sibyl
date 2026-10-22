import { lazy, Suspense, useEffect, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowDownUp,
  ArrowUpRight,
  BookOpen,
  Bell,
  Compass,
  Eye,
  EyeOff,
  Globe2,
  History,
  PieChart,
  Search,
  Settings2,
  Sparkles,
  Waves,
} from 'lucide-react';
import { Badge, Loading, Modal } from './components/ui';
import { NotificationBell } from './components/notifications';
import { NavigationDock, PageView } from './components/navigation';
import { useResource } from './lib/hooks';
import type { Run, System } from './lib/types';

const PortfolioPage = lazy(() =>
  import('./pages/Portfolio').then((module) => ({ default: module.PortfolioPage })),
);
const Markets = lazy(() =>
  import('./pages/Markets').then((module) => ({ default: module.Markets })),
);
const StrategiesPage = lazy(() =>
  import('./pages/Strategies').then((module) => ({ default: module.StrategiesPage })),
);
const Trading = lazy(() =>
  import('./pages/Trading').then((module) => ({ default: module.Trading })),
);
const Sibyl = lazy(() => import('./pages/Sibyl').then((module) => ({ default: module.Sibyl })));
const Oracle = lazy(() => import('./pages/Oracle').then((module) => ({ default: module.Oracle })));
const ForecastPage = lazy(() =>
  import('./pages/Research').then((module) => ({ default: module.ForecastPage })),
);
const News = lazy(() => import('./pages/Research').then((module) => ({ default: module.News })));
const ResearchPage = lazy(() =>
  import('./pages/Research').then((module) => ({ default: module.ResearchPage })),
);
const SettingsPage = lazy(() =>
  import('./pages/Settings').then((module) => ({ default: module.SettingsPage })),
);
const Alerts = lazy(() => import('./pages/Alerts').then((module) => ({ default: module.Alerts })));
const Roadmap = lazy(() =>
  import('./components/coming-soon').then((module) => ({ default: module.Roadmap })),
);
const destinations = [
  { path: '/sibyl', name: 'Sibyl', icon: Sparkles },
  { path: '/portfolio', name: 'Portfolio', icon: PieChart },
  { path: '/markets', name: 'Markets', icon: Activity },
  { path: '/trade', name: 'Trade', icon: ArrowDownUp },
  { path: '/strategies', name: 'Strategies', icon: Waves },
  { path: '/forecast', name: 'Forecasting', icon: Compass },
  { path: '/news', name: 'News', icon: Globe2 },
  { path: '/oracle', name: 'Agents', icon: Sparkles },
  { path: '/alerts', name: 'Alerts', icon: Bell },
  { path: '/research', name: 'Research', icon: BookOpen },
  { path: '/settings', name: 'Settings', icon: Settings2 },
  { path: '/roadmap', name: 'Coming soon', icon: Compass },
];
const secondary = destinations.filter((item) =>
  ['/oracle', '/alerts', '/research', '/roadmap'].includes(item.path),
);
const primary = destinations.filter((item) => !secondary.includes(item));

/** Keep bookmarked report/account filters while their home moves into Trade. */
function LegacyReportsRedirect() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  params.set('tab', params.get('tab') === 'history' ? 'history' : 'executions');
  return (
    <Navigate to={{ pathname: '/trade', search: `?${params}`, hash: location.hash }} replace />
  );
}

function WorkspaceSearch({ close }: { close: () => void }) {
  const [query, setQuery] = useState('');
  const navigate = useNavigate();
  const pages = [
    ...destinations,
    { path: '/trade?tab=executions', name: 'Trade · Executions', icon: ArrowDownUp },
    { path: '/trade?tab=history', name: 'Trade · Account history', icon: History },
  ].filter((item) =>
    `${item.name} ${item.path === '/settings' ? 'exchanges connections llm models apis workspace messaging whatsapp telegram signal email' : item.path === '/trade?tab=executions' ? 'trading report fills fees activity records' : ''}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const assets = ['BTC', 'ETH', 'SOL', 'LINK', 'AVAX', 'DOT'].filter(
    (asset) => query && asset.toLowerCase().includes(query.toLowerCase()),
  );
  const go = (path: string) => {
    navigate(path);
    close();
  };
  return (
    <Modal title="Your tools" onClose={close}>
      <div className="search-field">
        <Search size={17} />
        <input
          aria-label="Search workspace"
          placeholder="Search pages or assets"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <kbd>ESC</kbd>
      </div>
      <div className="tool-grid">
        {pages.map((item) => (
          <button key={item.path} onClick={() => go(item.path)}>
            <span>
              <item.icon size={21} />
            </span>
            <strong>{item.name}</strong>
          </button>
        ))}
        {assets.map((asset) => (
          <button key={asset} onClick={() => go(`/markets?asset=${asset}`)}>
            <span>
              <Activity size={21} />
            </span>
            <strong>{asset}/USDT</strong>
          </button>
        ))}
        {!pages.length && !assets.length && <p className="muted">No matching pages or assets.</p>}
      </div>
    </Modal>
  );
}

export function App() {
  const location = useLocation();
  const { data: system, error: systemError } = useResource<System>('/system', 30000);
  const { data: runs } = useResource<Run[]>('/runs', 30000);
  const [searchOpen, setSearchOpen] = useState(false);
  const [privateMode, setPrivateMode] = useState(false);
  useEffect(() => {
    document.documentElement.dataset.theme = 'standard';
  }, []);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
        event.preventDefault();
        setSearchOpen((value) => !value);
      }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, []);
  useEffect(() => {
    document.title = `Sibyl — ${destinations.find((item) => item.path === location.pathname)?.name ?? 'Workspace'}`;
  }, [location.pathname]);
  return (
    <div className={`app ${privateMode ? 'private-mode' : ''}`}>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="topbar">
        <Link to="/portfolio" className="app-brand" aria-label="Sibyl home">
          <img src="/brand/logo_transparent.png" alt="Sibyl" width="112" height="40" />
        </Link>
        <div className="topbar-context">
          <span>Personal workspace</span>
          <Link to="/settings?tab=exchanges" className="workspace-account-status">
            <Badge
              tone={
                system?.accounts?.mode === 'demo'
                  ? 'demo'
                  : system?.accounts?.mode === 'test'
                    ? 'purple'
                    : system?.accounts?.active_ids.length
                      ? 'lime'
                      : 'neutral'
              }
            >
              {system?.accounts?.mode === 'demo'
                ? 'Demo preview'
                : system?.accounts?.mode === 'test'
                  ? 'Test accounts'
                  : system?.accounts?.active_ids.length
                    ? `${system.accounts.active_ids.length} active ${system.accounts.active_ids.length === 1 ? 'account' : 'accounts'}`
                    : 'No active accounts'}
            </Badge>
          </Link>
        </div>
        <div className="topbar-actions">
          <button
            className="global-search"
            aria-label="Search workspace"
            onClick={() => setSearchOpen(true)}
          >
            <Search size={16} />
            <span>Search workspace</span>
            <kbd>⌘ K</kbd>
          </button>
          <button
            className="icon-button"
            aria-label={privateMode ? 'Show balances' : 'Hide balances'}
            title={privateMode ? 'Show balances' : 'Hide balances'}
            onClick={() => setPrivateMode((value) => !value)}
          >
            {privateMode ? <EyeOff size={18} /> : <Eye size={18} />}
          </button>
          <NotificationBell runs={runs} />
          <Link className="avatar" to="/settings" aria-label="Workspace settings">
            N
          </Link>
        </div>
      </header>
      <div className="workspace-layout">
        <NavigationDock items={primary} moreItems={secondary} />
        <div className="workspace-surface">
          <main id="main-content" className="main-content" tabIndex={-1}>
            {systemError && location.pathname !== '/settings' && (
              <div className="inline-alert">
                {systemError}
                <Link to="/settings?tab=workspace">
                  Settings <ArrowUpRight size={13} />
                </Link>
              </div>
            )}
            <Suspense fallback={<Loading />}>
              <PageView>
                <Routes>
                  <Route path="/" element={<Navigate to="/portfolio" replace />} />
                  <Route path="/portfolio" element={<PortfolioPage />} />
                  <Route path="/markets" element={<Markets />} />
                  <Route path="/strategies" element={<StrategiesPage />} />
                  <Route path="/trade" element={<Trading />} />
                  <Route
                    path="/connections"
                    element={<Navigate to="/settings?tab=exchanges" replace />}
                  />
                  <Route path="/sibyl" element={<Sibyl />} />
                  <Route path="/oracle" element={<Oracle />} />
                  <Route path="/alerts" element={<Alerts />} />
                  <Route path="/forecast" element={<ForecastPage />} />
                  <Route path="/news" element={<News />} />
                  <Route path="/research" element={<ResearchPage />} />
                  <Route path="/settings" element={<SettingsPage system={system} />} />
                  <Route path="/reports" element={<LegacyReportsRedirect />} />
                  <Route path="/roadmap" element={<Roadmap />} />
                  <Route
                    path="*"
                    element={
                      <div className="empty-state">
                        <h1>Page not found</h1>
                        <Link className="button primary" to="/portfolio">
                          Return to portfolio
                        </Link>
                      </div>
                    }
                  />
                </Routes>
              </PageView>
            </Suspense>
          </main>
          <footer className="workspace-footer">
            <span>
              <span className="status-dot" />
              Local workspace · Sibyl {system?.version ?? '0.2.0'}
            </span>
            <a href="http://localhost:3000/sibyl/" target="_blank" rel="noreferrer">
              Documentation <ArrowUpRight size={12} />
            </a>
          </footer>
        </div>
      </div>
      {searchOpen && <WorkspaceSearch close={() => setSearchOpen(false)} />}
    </div>
  );
}
