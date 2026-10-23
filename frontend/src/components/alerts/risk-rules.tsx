import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Archive,
  ArrowUpRight,
  Eye,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  ShieldAlert,
  Undo2,
} from 'lucide-react';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from '../ui';
import { NotificationText } from '../notifications';
import { RiskForm } from './risk-form';
import { RiskEvidence } from './risk-evidence';
import { post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { date } from '../../lib/strategy-monitor';
import {
  riskLabel,
  riskValue,
  type RiskRule,
  type RiskRulesData,
  type RiskExample,
} from '../../lib/risk-alerts';
import type { AccountSelection, MarketSettings } from '../../lib/types';

/** User-defined notification limits for a fixed account set; no trading controls. */
export function RiskRules({
  example,
  initialRuleId,
  initialSampleId,
  initialScope,
}: {
  example: boolean;
  initialRuleId: string;
  initialSampleId?: number;
  initialScope: string;
}) {
  const [archived, setArchived] = useState(false),
    [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false),
    [editing, setEditing] = useState<RiskRule>();
  const [evidence, setEvidence] = useState<{ id: string; sampleId?: number } | undefined>(
    initialRuleId && !example ? { id: initialRuleId, sampleId: initialSampleId } : undefined,
  );
  const [busy, setBusy] = useState('');
  const [, setParams] = useSearchParams();
  const toast = useToast();
  const rules = useResource<RiskRulesData>(
    `/risk-alerts?include_archived=${archived}&offset=${offset}`,
    10000,
    !example,
  );
  const sample = useResource<RiskExample>('/risk-alerts/example', 0, example);
  const accounts = useResource<AccountSelection>('/accounts', 0, creating || !!editing);
  const settings = useResource<MarketSettings>('/settings/market', 0, creating || !!editing);
  const data = example ? sample.data?.rules : rules.data;
  const error = example ? sample.error : rules.error;
  const act = async (rule: RiskRule, action: string) => {
    setBusy(rule.id);
    try {
      await post(
        `/risk-alerts/${rule.id}/${action === 'check' ? 'check' : 'action'}`,
        action === 'check' ? {} : { action, revision: rule.revision },
      );
      refresh();
    } catch (reason) {
      toast((reason as Error).message, true);
      refresh();
    } finally {
      setBusy('');
    }
  };
  return (
    <>
      <Panel className="full-panel">
        <PanelTitle
          title="Account risk"
          subtitle={`${data?.count ?? 0} of ${data?.limit ?? 25} non-archived rules · complete spot valuation required`}
          action={
            <button
              className="button primary small"
              disabled={example || !data || data.count >= data.limit}
              onClick={() => setCreating(true)}
            >
              <Plus size={14} /> New risk alert
            </button>
          }
        />
        <div className="strategy-alert-intro">
          <ShieldAlert size={19} />
          <p>
            Keep your own limits in view. Watch a value floor, an asset’s allocation or a decline
            from an observed account-value peak. Choose one account or a fixed group. Only complete,
            fresh valuations can produce notices.
          </p>
        </div>
        <div className="strategy-alert-filters">
          <label className="alert-archive-toggle">
            <input
              type="checkbox"
              checked={archived}
              disabled={example}
              onChange={(e) => {
                setArchived(e.target.checked);
                setOffset(0);
              }}
            />{' '}
            Include archived
          </label>
          <Link className="text-button" to="/account">
            Open Account <ArrowUpRight size={12} />
          </Link>
        </div>
        {error ? (
          <ErrorState message={error} retry={example ? sample.retry : rules.retry} />
        ) : !data ? (
          <Loading />
        ) : data.items.length ? (
          <div className="price-rule-list">
            {data.items.map((rule) => (
              <article className="price-rule-card strategy-alert-card risk-rule-card" key={rule.id}>
                <div className="price-rule-heading">
                  <span className="activity-icon">
                    <ShieldAlert size={19} />
                  </span>
                  <div>
                    <h3>{rule.label || riskLabel(rule.metric, rule.asset)}</h3>
                    <p>
                      {rule.accounts.map((a) => a.label).join(' + ')} · {rule.accounts.length}{' '}
                      pinned account{rule.accounts.length === 1 ? '' : 's'}
                    </p>
                    <div className="strategy-alert-tags">
                      <Badge tone={rule.status === 'armed' ? 'lime' : 'neutral'}>
                        {rule.status === 'armed' ? 'Watching' : rule.status}
                      </Badge>
                      {rule.environment === 'demo' ? (
                        <Badge tone="demo">Demo balances & prices</Badge>
                      ) : rule.environment === 'test' ? (
                        <Badge tone="peach">Test funds</Badge>
                      ) : (
                        <Badge>Production funds</Badge>
                      )}
                      {rule.in_breach && (
                        <Badge tone="peach">Last valid check: limit reached</Badge>
                      )}
                      {rule.error && <Badge tone="peach">Assessment unavailable</Badge>}
                    </div>
                  </div>
                </div>
                <div className="risk-rule-reading">
                  <div>
                    <span>{riskLabel(rule.metric, rule.asset)}</span>
                    <strong className="monetary">
                      {riskValue(rule.last_observation?.metric_value, rule.metric)}
                    </strong>
                  </div>
                  <div>
                    <span>
                      Notify {rule.metric === 'value_floor' ? 'at or below' : 'at or above'}
                    </span>
                    <strong className="monetary">{riskValue(rule.threshold, rule.metric)}</strong>
                  </div>
                  <div>
                    <span>Recovery level</span>
                    <strong className="monetary">
                      {riskValue(rule.reset_threshold, rule.metric)}
                    </strong>
                  </div>
                </div>
                {rule.error && (
                  <p className="risk-rule-error" role="status">
                    {rule.error}{' '}
                    {rule.last_observation &&
                      'The displayed values are retained observations, not a current assessment.'}
                  </p>
                )}
                {rule.evaluation_note && (
                  <p className="footnote connection-alert-note">{rule.evaluation_note}</p>
                )}
                <div className="price-rule-evidence">
                  <span>Last complete valuation {date(rule.last_observation?.as_of)}</span>
                  <span>Last attempt {date(rule.last_checked_at)}</span>
                  <span>{rule.source_info.source_label} · reference feed</span>
                  <span>
                    {rule.notifications} notification{rule.notifications === 1 ? '' : 's'} retained
                  </span>
                </div>
                <div className="price-rule-footer">
                  <span className="muted">Window started {date(rule.armed_at)}</span>
                  <div className="price-rule-actions">
                    <button
                      className="text-button"
                      disabled={!rule.last_sample_id}
                      onClick={() => setEvidence({ id: rule.id })}
                    >
                      <Eye size={13} /> View evidence
                    </button>
                    {rule.status === 'archived' ? (
                      <button
                        className="button secondary tiny"
                        disabled={!!busy || example}
                        onClick={() => act(rule, 'restore')}
                      >
                        <Undo2 size={13} /> Restore paused
                      </button>
                    ) : (
                      <>
                        <button
                          className="icon-button"
                          aria-label={`Edit ${rule.label || riskLabel(rule.metric, rule.asset)} risk alert`}
                          title="Edit; saves paused"
                          disabled={!!busy || example}
                          onClick={() => setEditing(rule)}
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          className="button secondary tiny"
                          disabled={!!busy || example}
                          onClick={() => act(rule, rule.status === 'armed' ? 'pause' : 'arm')}
                        >
                          {rule.status === 'armed' ? <Pause size={13} /> : <Play size={13} />}{' '}
                          {rule.status === 'armed' ? 'Pause alert' : 'Resume alert'}
                        </button>
                        {rule.status === 'armed' && (
                          <button
                            className="icon-button"
                            aria-label={`Check ${rule.label || riskLabel(rule.metric, rule.asset)} risk alert`}
                            title="Check when due; respects read schedule"
                            disabled={!!busy || example}
                            onClick={() => act(rule, 'check')}
                          >
                            <RefreshCw size={13} />
                          </button>
                        )}
                        <button
                          className="icon-button"
                          aria-label={`Archive ${rule.label || riskLabel(rule.metric, rule.asset)} risk alert`}
                          title="Archive alert; retain notifications"
                          disabled={!!busy || example}
                          onClick={() => act(rule, 'archive')}
                        >
                          <Archive size={14} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <Empty title="Your accounts. Your limits.">
            Create an opt-in watch for a fixed set of active exchange accounts. Checks can notify
            you about value and allocation changes.{' '}
            <Link to="/settings?tab=exchanges">Connect accounts ↗</Link> or use View example to
            explore without setup.
          </Empty>
        )}
        {data && !example && (offset > 0 || data.total > 50) && (
          <div className="alert-pagination">
            <button
              className="button secondary tiny"
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              Previous rules
            </button>
            <span>
              {offset + 1}–{Math.min(offset + 50, data.total)} of {data.total}
            </span>
            <button
              className="button secondary tiny"
              disabled={offset + 50 >= data.total}
              onClick={() => setOffset(offset + 50)}
            >
              Next rules
            </button>
          </div>
        )}
        <p className="footnote padded">
          Checks read spot balances and the pinned feed roughly once a minute, subject to provider
          budgets and backoff. Inactive accounts or incomplete/undated/stale prices prevent
          assessment. Drawdown includes deposits/withdrawals and is not investment return. Resume
          starts a new peak window. Alerts do not place orders, close positions or enforce strategy
          risk limits.
        </p>
      </Panel>
      {example && sample.data && (
        <Panel className="strategy-alert-example">
          <PanelTitle
            title="Example notification"
            subtitle="Illustrative only · no account has been read"
          />
          <div className="notification-copy">
            <NotificationText item={sample.data.inbox.items[0]} />
          </div>
        </Panel>
      )}
      {(creating || editing) && (
        <Modal
          className="risk-alert-dialog"
          title={editing ? 'Edit risk alert' : 'New account risk alert'}
          onClose={() => {
            setCreating(false);
            setEditing(undefined);
          }}
        >
          {accounts.error || settings.error ? (
            <ErrorState
              message={accounts.error || settings.error}
              retry={() => {
                accounts.retry();
                settings.retry();
              }}
            />
          ) : accounts.data && settings.data ? (
            <RiskForm
              key={editing?.id || 'new'}
              rule={editing}
              accounts={accounts.data}
              settings={settings.data}
              initialScope={initialScope}
              onSaved={() => {
                setCreating(false);
                setEditing(undefined);
                setOffset(0);
                refresh();
                toast(
                  editing
                    ? 'Changes saved paused. Resume starts a new peak window.'
                    : 'Account risk watch saved.',
                );
              }}
            />
          ) : (
            <Loading />
          )}
        </Modal>
      )}
      {evidence && (
        <Modal
          className="risk-evidence-dialog"
          title="Valuation evidence"
          onClose={() => {
            setEvidence(undefined);
            setParams(
              (previous) => {
                const next = new URLSearchParams(previous);
                next.delete('rule_id');
                next.delete('sample_id');
                return next;
              },
              { replace: true },
            );
          }}
        >
          <RiskEvidence
            key={`${evidence.id}-${evidence.sampleId || ''}`}
            ruleId={evidence.id}
            sampleId={evidence.sampleId}
            example={example ? sample.data?.evidence : undefined}
          />
        </Modal>
      )}
    </>
  );
}
