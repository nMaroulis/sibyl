"""Timestamp-weighted Modified Dietz estimates, never inferred cash-flow completeness."""

import math
from decimal import Decimal, localcontext


def dietz(opening, closing, start_ms, end_ms, flows):
    """Use signed contributions and elapsed-second weights; return no ratio on invalid capital.

    Positive cash flows enter the measured scope; withdrawals are negative.
    Fee costs and investment income remain in the valuation change. This is an
    approximate period return, not exact time-weighting, an IRR or tax accounting.
    """
    if end_ms <= start_ms:
        raise ValueError("The closing valuation must follow the opening valuation.")
    with localcontext() as context:
        context.prec = 50
        beginning, ending = Decimal(str(opening)), Decimal(str(closing))
        net, weighted = Decimal(0), Decimal(0)
        for flow in flows:
            timestamp = flow["timestamp_ms"]
            if not start_ms < timestamp <= end_ms:
                raise ValueError("A cash flow falls outside the measurement boundaries.")
            value = Decimal(str(flow["value"]))
            net += value
            weighted += value * Decimal(end_ms - timestamp) / Decimal(end_ms - start_ms)
        gain = ending - beginning - net
        capital = beginning + weighted
        ratio = float(gain / capital * 100) if capital > 0 else None
        reason = (
            None
            if capital > 0
            else "Weighted capital is zero or negative; no meaningful Modified Dietz ratio is reported."
        )
        if ratio is not None and not math.isfinite(ratio):
            ratio, reason = (
                None,
                "The return exceeds the supported numerical range; no percentage is reported.",
            )
        return dict(
            opening=float(beginning),
            closing=float(ending),
            net_external_flow=float(net),
            gain=float(gain),
            weighted_capital=float(capital),
            return_pct=ratio,
            return_note=reason,
        )
