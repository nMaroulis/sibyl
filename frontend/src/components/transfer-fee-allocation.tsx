import { useEffect, useState } from 'react';
import { Check, Link2, RefreshCw } from 'lucide-react';
import { api } from '../lib/api';
import { Badge } from './ui';

export type FeeAllocationInput = {
  outgoing_amount: 'total_debit' | 'principal';
  incoming_amount: 'net_credit' | 'gross_receipt';
  outgoing_fee_quantity: string | null;
  incoming_fee_quantity: string | null;
  fee_policy: 'separate_inventory_cost';
  distinct_fees_confirmed: boolean;
};
export type FeeAllocationPlan = {
  request: FeeAllocationInput;
  source_debit: string;
  dispatch_quantity: string;
  destination_credit: string;
  outgoing_fee: string;
  incoming_fee: string;
  fee_sources: { outgoing: 'reported' | 'user_asserted'; incoming: 'reported' | 'user_asserted' };
};
export type FeeReview = { enabled: boolean; ready: boolean; allocation: FeeAllocationInput | null };
type Observation = {
  id: string;
  fingerprint: string;
  asset: string;
  quantity: number;
  fee_known: boolean;
  fee: { currency: string | null; cost: number | null };
};

function allocationKey(input: FeeAllocationInput | null) {
  return JSON.stringify(
    input && [
      input.outgoing_amount,
      input.incoming_amount,
      input.outgoing_fee_quantity,
      input.incoming_fee_quantity,
      input.fee_policy,
      input.distinct_fees_confirmed,
    ],
  );
}

/** Explicit conventions are checked by Python against frozen source fingerprints. */
export function TransferFeeAllocation({
  outgoing,
  incoming,
  saved,
  example,
  disabled,
  onChange,
  reload,
}: {
  outgoing: Observation;
  incoming: Observation;
  saved?: FeeAllocationPlan | null;
  example: boolean;
  disabled: boolean;
  onChange: (value: FeeReview) => void;
  reload: () => void;
}) {
  const [enabled, setEnabled] = useState(!!saved);
  const [outgoingMode, setOutgoingMode] = useState(saved?.request.outgoing_amount || '');
  const [incomingMode, setIncomingMode] = useState(saved?.request.incoming_amount || '');
  const [outgoingFee, setOutgoingFee] = useState(saved?.request.outgoing_fee_quantity ?? '');
  const [incomingFee, setIncomingFee] = useState(saved?.request.incoming_fee_quantity ?? '');
  const [distinctFees, setDistinctFees] = useState(saved?.request.distinct_fees_confirmed ?? false);
  const [checked, setChecked] = useState(saved ? allocationKey(saved.request) : '');
  const [plan, setPlan] = useState<FeeAllocationPlan | null>(saved || null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const input: FeeAllocationInput | null =
    outgoingMode && incomingMode
      ? {
          outgoing_amount: outgoingMode as FeeAllocationInput['outgoing_amount'],
          incoming_amount: incomingMode as FeeAllocationInput['incoming_amount'],
          outgoing_fee_quantity: outgoing.fee_known ? null : outgoingFee || null,
          incoming_fee_quantity: incoming.fee_known ? null : incomingFee || null,
          fee_policy: 'separate_inventory_cost',
          distinct_fees_confirmed: distinctFees,
        }
      : null;
  const key = allocationKey(input);
  const complete =
    !!input &&
    (outgoing.fee_known || outgoingFee !== '') &&
    (incoming.fee_known || incomingFee !== '');
  const ready = enabled && checked === key && !!plan && complete;
  useEffect(() => {
    onChange({ enabled, ready: !enabled || ready, allocation: input });
  }, [enabled, ready, key, onChange]);
  const check = async () => {
    if (!input || !complete) return;
    setBusy(true);
    setError('');
    setChecked('');
    try {
      const result = await api<{ allocation: FeeAllocationPlan }>(
        example ? '/account-ledger/transfers/example/preview' : '/account-ledger/transfers/preview',
        {
          method: 'POST',
          body: JSON.stringify({
            outgoing_id: outgoing.id,
            incoming_id: incoming.id,
            outgoing_fingerprint: outgoing.fingerprint,
            incoming_fingerprint: incoming.fingerprint,
            allocation: input,
          }),
        },
      );
      setPlan(result.allocation);
      setChecked(key);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const quantity = (value: string) => `${value} ${outgoing.asset}`;
  return (
    <section className="transfer-fee-review">
      <button
        type="button"
        className={`transfer-fee-toggle ${enabled ? 'selected' : ''}`}
        aria-pressed={enabled}
        disabled={disabled || busy}
        onClick={() => setEnabled(!enabled)}
      >
        <Link2 size={17} />
        <span>
          <strong>Review amount &amp; fee allocation</strong>
          <small>Choose how the reported amounts relate to distinct fee charges.</small>
        </span>
        {enabled && <Check size={17} />}
      </button>
      {enabled && (
        <div className="transfer-fee-fields">
          <p>
            Both fees must be distinct charges. A repeated display of the same fee must not be
            counted twice. Reported source facts stay unchanged.
          </p>
          <div className="transfer-fee-grid">
            <label>
              Outgoing amount convention
              <select
                aria-label="Outgoing amount convention"
                value={outgoingMode}
                disabled={disabled || busy}
                onChange={(event) => setOutgoingMode(event.target.value)}
              >
                <option value="">Choose a convention</option>
                <option value="total_debit">Total account debit · fee included</option>
                <option value="principal">Sent principal · fee charged on top</option>
              </select>
            </label>
            <label>
              Incoming amount convention
              <select
                aria-label="Incoming amount convention"
                value={incomingMode}
                disabled={disabled || busy}
                onChange={(event) => setIncomingMode(event.target.value)}
              >
                <option value="">Choose a convention</option>
                <option value="net_credit">Net balance credit · fee already deducted</option>
                <option value="gross_receipt">Gross receipt · fee deducted afterward</option>
              </select>
            </label>
            {(
              [
                { side: 'Outgoing', event: outgoing, value: outgoingFee, set: setOutgoingFee },
                { side: 'Incoming', event: incoming, value: incomingFee, set: setIncomingFee },
              ] as const
            ).map(({ side, event, value, set }) => (
              <label key={side}>
                {side} fee · {outgoing.asset}
                {event.fee_known ? (
                  <span className="transfer-reported-fee">
                    {String(event.fee.cost)} {event.fee.currency} <Badge>Reported</Badge>
                  </span>
                ) : (
                  <>
                    <input
                      aria-label={`${side} missing fee quantity`}
                      type="number"
                      min="0"
                      max="1e30"
                      step="any"
                      value={value}
                      disabled={disabled || busy}
                      onChange={(change) => set(change.target.value)}
                      placeholder="Enter a verified fee; 0 is an assertion"
                    />
                    <small>
                      Missing from the source. Your value is saved as an explicit assertion in{' '}
                      {outgoing.asset}.
                    </small>
                  </>
                )}
              </label>
            ))}
          </div>
          <p>
            FIFO policy: principal units first, outgoing fee units last. Incoming fee units come
            from the tail of the arriving lots. Fee inventory cost stays separate from trading
            P&amp;L; historical fee valuation and tax treatment are not calculated.
          </p>
          {Number(outgoing.fee_known ? outgoing.fee.cost : outgoingFee) > 0 &&
            Number(incoming.fee_known ? incoming.fee.cost : incomingFee) > 0 && (
              <button
                type="button"
                className={`transfer-fee-toggle ${distinctFees ? 'selected' : ''}`}
                aria-pressed={distinctFees}
                disabled={disabled || busy}
                onClick={() => setDistinctFees(!distinctFees)}
              >
                <span>
                  <strong>I verified these are two distinct fee charges</strong>
                  <small>They are not the same fee displayed by both records.</small>
                </span>
                {distinctFees && <Check size={17} />}
              </button>
            )}
          <button
            className="button secondary tiny"
            type="button"
            disabled={disabled || busy || !complete}
            onClick={check}
          >
            {ready ? <Check size={13} /> : <RefreshCw size={13} className={busy ? 'spin' : ''} />}
            {busy ? 'Checking…' : ready ? 'Allocation checked' : 'Check allocation'}
          </button>
          {!!error && (
            <div className="transfer-review-alert" role="alert">
              <p>{error}</p>
              <button type="button" className="button secondary tiny" onClick={reload}>
                Reload source records
              </button>
            </div>
          )}
          {ready && plan && (
            <div className="transfer-allocation-result" role="status">
              <Badge tone="lime">Balanced allocation</Badge>
              <dl>
                <div>
                  <dt>Source debit</dt>
                  <dd>{quantity(plan.source_debit)}</dd>
                </div>
                <div>
                  <dt>Destination credit</dt>
                  <dd>{quantity(plan.destination_credit)}</dd>
                </div>
                <div>
                  <dt>Outgoing fee</dt>
                  <dd>
                    {quantity(plan.outgoing_fee)} ·{' '}
                    {plan.fee_sources.outgoing === 'reported' ? 'reported' : 'user asserted'}
                  </dd>
                </div>
                <div>
                  <dt>Incoming fee</dt>
                  <dd>
                    {quantity(plan.incoming_fee)} ·{' '}
                    {plan.fee_sources.incoming === 'reported' ? 'reported' : 'user asserted'}
                  </dd>
                </div>
              </dl>
              <p>
                Debit = credit + both distinct fees. Confirming saves this allocation and its source
                versions with your review note.
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
