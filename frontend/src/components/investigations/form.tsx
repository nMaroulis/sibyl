import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, BookOpen, Layers3, ScanLine } from 'lucide-react';
import { Modal } from '../ui';
import { MarketSourcePicker } from '../market-source-picker';
import { useResource } from '../../lib/hooks';
import { post } from '../../lib/api';
import type { AccountSelection, MarketSettings } from '../../lib/types';
import type { Investigation, ResearchContext } from './types';

const templates = [
  {
    title: 'Market & news',
    icon: ScanLine,
    question:
      'Compare the selected market’s trend, volatility and technical indicators with the available news. Explain agreement, contradictions and missing evidence.',
  },
  {
    title: 'Account perspective',
    icon: Layers3,
    question:
      'Review my selected account allocation, concentration and valuation coverage. Explain the main risks and limitations of the available accounting evidence.',
  },
  {
    title: 'Strategy review',
    icon: BookOpen,
    question:
      'Review my running strategies, their recent journal events and any saved backtest evidence. Distinguish paper and exchange execution, and explain what needs attention.',
  },
];

export function InvestigationForm({
  ready,
  onClose,
  onCreated,
}: {
  ready: boolean;
  onClose: () => void;
  onCreated: (definition: Investigation, run: boolean) => Promise<void>;
}) {
  const [title, setTitle] = useState('');
  const [question, setQuestion] = useState('');
  const [context, setContext] = useState<ResearchContext>({
    symbol: 'BTC/USDT',
    timeframe: '1d',
    market_source: '',
    portfolio_scope: 'all',
    news_mode: '',
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const accounts = useResource<AccountSelection>('/accounts');
  const markets = useResource<MarketSettings>('/settings/market');
  const save = async (run: boolean) => {
    if (busy || !title.trim() || !question.trim()) return;
    setBusy(true);
    setError('');
    try {
      const definition = await post<Investigation>('/investigations', { title, question, context });
      await onCreated(definition, run);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title="New investigation"
      onClose={() => !busy && onClose()}
      className="investigation-form-dialog"
    >
      <p className="muted">
        Save a question. Sibyl brings the relevant specialists and their sources together.
      </p>
      <div className="investigation-templates">
        {templates.map((item) => (
          <button
            key={item.title}
            onClick={() => {
              setTitle(item.title);
              setQuestion(item.question);
            }}
            disabled={busy}
          >
            <item.icon size={16} />
            <span>{item.title}</span>
            <ArrowUpRight size={13} />
          </button>
        ))}
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save(ready);
        }}
      >
        <label>
          Title
          <input
            required
            maxLength={100}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="My weekly market perspective"
            disabled={busy}
          />
        </label>
        <label>
          What would you like to understand?
          <textarea
            required
            rows={4}
            maxLength={2400}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask a focused research question…"
            disabled={busy}
          />
        </label>
        <details className="investigation-context-form">
          <summary>
            Starting context <span>Market, accounts & sources</span>
          </summary>
          <p className="footnote">
            Defaults for the specialists. Your question can ask for other comparisons; recorded
            evidence identifies the sources actually used.
          </p>
          <div className="form-grid">
            <label>
              Market pair
              <input
                value={context.symbol}
                onChange={(event) =>
                  setContext({ ...context, symbol: event.target.value.toUpperCase() })
                }
                placeholder="ETH/USDT"
                required
              />
            </label>
            <label>
              Timeframe
              <select
                value={context.timeframe}
                onChange={(event) => setContext({ ...context, timeframe: event.target.value })}
              >
                {['1h', '4h', '1d', '1w'].map((frame) => (
                  <option key={frame}>{frame}</option>
                ))}
              </select>
            </label>
            <label>
              Account view
              <select
                value={context.portfolio_scope}
                onChange={(event) =>
                  setContext({ ...context, portfolio_scope: event.target.value })
                }
              >
                <option value="all">Combined active accounts</option>
                {accounts.data?.scopes
                  .filter((scope) => scope.id !== 'all')
                  .map((scope) => (
                    <option key={scope.id} value={scope.id}>
                      {scope.label}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              News
              <select
                value={context.news_mode}
                onChange={(event) =>
                  setContext({
                    ...context,
                    news_mode: event.target.value as ResearchContext['news_mode'],
                  })
                }
              >
                <option value="">Workspace selection</option>
                <option value="live">Retained publisher news</option>
                <option value="demo">Demo · synthetic news</option>
              </select>
            </label>
          </div>
          {markets.data && (
            <MarketSourcePicker
              settings={markets.data}
              value={context.market_source || markets.data.active.id}
              onChange={(market_source) => setContext({ ...context, market_source })}
            />
          )}
          {markets.error && (
            <p role="alert">Market choices could not load. The workspace feed will be used.</p>
          )}
          {accounts.data?.mode === 'none' && (
            <p className="footnote">
              No active exchange accounts. Market and news research remain available.{' '}
              <Link to="/settings?tab=exchanges">Connect an account ↗</Link>
            </p>
          )}
        </details>
        {error && (
          <p className="inline-alert" role="alert">
            {error}
          </p>
        )}
        {!ready && (
          <p className="footnote">
            You can save this question now.{' '}
            <Link to="/settings?tab=models">Connect an AI model</Link> to run it.
          </p>
        )}
        <div className="form-actions">
          {ready && (
            <button
              type="button"
              className="button"
              disabled={busy || !title.trim() || !question.trim()}
              onClick={() => void save(false)}
            >
              Save for later
            </button>
          )}
          <button className="button primary" disabled={busy || !title.trim() || !question.trim()}>
            {busy ? 'Saving…' : ready ? 'Save & investigate' : 'Save investigation'}
            <ArrowUpRight size={14} />
          </button>
        </div>
      </form>
    </Modal>
  );
}
