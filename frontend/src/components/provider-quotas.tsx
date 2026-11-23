import { ArrowUpRight, Gauge, ShieldCheck } from 'lucide-react';
import { Badge } from './ui';
import { number } from '../lib/api';
import type { ProviderQuotas } from '../lib/provider-health';
import '../styles/provider-quotas.css';

const scopes: Record<string, string> = {
  provider_environment: 'Shared provider / environment',
  credential: 'Identical API keys · local app',
  all_local_profiles: 'All local profiles · conservative',
};
const date = (value: string) => new Date(value).toLocaleString();

/** Allowances and provider observations stay distinct; viewing this card makes no provider call. */
export function ProviderQuotaDetails({ value }: { value: ProviderQuotas }) {
  if (value.status === 'demo')
    return <p className="footnote">Offline Demo has no external request quota.</p>;
  return (
    <section className="provider-quotas" aria-label="Read allowances and quota evidence">
      <div className="provider-quota-title">
        <span>
          <Gauge size={15} />
          <strong>Read allowances & quota evidence</strong>
        </span>
        <Badge>
          {value.status === 'not_observed'
            ? 'No session observations'
            : `${value.attempts} observed attempts`}
        </Badge>
      </div>
      <p className="footnote">
        {value.policy.name}. {value.policy.coverage}
      </p>
      {!!value.retry_after && (
        <p className="provider-quota-wait" role="status">
          Read allowance exhausted · retry in about {value.retry_after}s. No request was sent by the
          deferred attempt.
        </p>
      )}
      {!!value.budgets.length && (
        <div className="provider-quota-grid">
          {value.budgets.map((b) => {
            const percent = Math.min(100, Math.max(0, (b.used / b.capacity) * 100));
            return (
              <div className="provider-quota-budget" key={b.id}>
                <div>
                  <strong>{b.name}</strong>
                  <Badge tone={percent >= 100 ? 'sand' : 'neutral'}>
                    {b.provider_limit ? 'Observed provider ceiling' : 'App allowance'}
                  </Badge>
                </div>
                <p>
                  <b>{number(b.used, 2)}</b>
                  <span>
                    {' '}
                    / {number(b.capacity, 2)}{' '}
                    {b.period_seconds
                      ? `per ${b.period_seconds}s`
                      : `· refills ${number(b.refill_per_second ?? 0, 2)}/s`}
                  </span>
                </p>
                <div
                  className={`provider-quota-meter ${percent >= 80 ? 'busy' : ''}`}
                  role="meter"
                  aria-label={b.name}
                  aria-valuemin={0}
                  aria-valuemax={b.capacity}
                  aria-valuenow={Math.min(b.capacity, b.used)}
                  aria-valuetext={`${number(b.used, 2)} used of ${number(b.capacity, 2)}`}
                >
                  <span style={{ width: `${percent}%` }} />
                </div>
                <small>
                  {scopes[b.scope] ?? b.scope}.{' '}
                  {b.provider_limit != null && b.reported_used == null
                    ? 'Current provider headroom is unknown; this is a local estimate.'
                    : `${number(b.remaining, 2)} estimated headroom.`}
                </small>
                {b.provider_limit != null && (
                  <small>
                    Reported provider limit {number(b.provider_limit, 0)}; reads reserve 20%.{' '}
                    {b.limit_observed_at && `Declaration observed ${date(b.limit_observed_at)}.`}
                  </small>
                )}
                {b.reported_used != null && (
                  <small>
                    Latest reported usage in this minute: {number(b.reported_used, 0)}
                    {b.observed_at ? ` · ${date(b.observed_at)}` : ''}. The estimate also includes
                    local/in-flight charges.
                  </small>
                )}
                {b.reset_at && (
                  <small>Window resets {new Date(b.reset_at).toLocaleTimeString()}.</small>
                )}
              </div>
            );
          })}
        </div>
      )}
      {value.unpaired_ip_weight && (
        <p className="footnote">
          Reported IP weight {number(value.unpaired_ip_weight.used, 0)} at{' '}
          {date(value.unpaired_ip_weight.at)}. Its provider limit has not been observed; provider
          headroom is unknown.
        </p>
      )}
      <details className="provider-quota-notes">
        <summary>Coverage, identity & mutation boundaries</summary>
        <p className="footnote">
          {value.policy.identity} {value.policy.headroom}
        </p>
        <p className="footnote">
          Reviewed read costs: {value.reviewed_attempts} attempts · unreviewed or outside read
          policy: {value.unreviewed_attempts} · bypassed read admission: {value.bypassed_attempts}.
          Bypasses include native mutations and their preflight reads; these counters are separate
          from read-success diagnostics.
        </p>
        {value.last_request && (
          <p className="footnote">
            Last observed: {value.last_request.operation} · {date(value.last_request.at)}
            {value.last_request.costs.length
              ? ` · ${value.last_request.costs.map((c) => `${c.budget.replaceAll('_', ' ')} ${c.cost}`).join(', ')}`
              : ' · no reviewed read cost'}
            .
          </p>
        )}
        {value.last_deferral && (
          <p className="footnote">
            Last deferral: {date(value.last_deferral.at)} · {value.last_deferral.operation}.{' '}
            {value.last_deferral.reason}
          </p>
        )}
        {value.reported_order_counts.map((c) => (
          <p className="footnote" key={c.period_seconds}>
            Reported order counter: {c.used}
            {c.provider_limit == null ? ' · limit unknown' : ` / ${c.provider_limit}`} over{' '}
            {c.period_seconds}s · {date(c.observed_at)}. Observation only; this does not approve or
            enforce order submission.
          </p>
        ))}
        {!!value.coverage_gaps && (
          <p className="footnote">
            Quota observation gaps in this process: {value.coverage_gaps}. Telemetry may be
            incomplete.
          </p>
        )}
        <p className="footnote">
          <ShieldCheck size={12} /> Existing provider throttles stay enabled. These estimates cover
          one Sibyl process; other programs, IP routing, account tiers and WebSocket traffic can
          change actual availability. Orders and cancellations are never queued or retried by this
          read policy. Refresh is passive. Budgets reset on backend restart; provider limits do not.
        </p>
        {value.policy.reference && (
          <a className="text-link" href={value.policy.reference} target="_blank" rel="noreferrer">
            Provider reference <ArrowUpRight size={12} />
          </a>
        )}
      </details>
    </section>
  );
}
