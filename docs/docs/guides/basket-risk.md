# Historical basket risk

In **Account**, expand **Historical basket risk** to study a basket with today's selected holding weights over past daily prices. This is separate from measured cash-flow-adjusted account returns and from concentration-only HHI metrics.

1. Choose your Account scope: all eligible accounts, one exchange or one account. Production and test funds retain the normal Account boundaries; Demo remains explicit.
2. Select one to eight **currently held, priced assets** and a 30/60/90/180/365-day maximum history window. The initial selection contains up to six largest priced holdings; excluded holdings are not silently added later.
3. Select **Calculate & save risk study**. Sibyl reads the current holdings and the configured reference feed, fetches each distinct historical conversion leg once, and saves the input evidence and results. Simply opening a saved study makes no new provider read.
4. Inspect dates, actual observations, source and coverage before interpreting volatility or tail metrics. A subset is renormalized within its selected assets; it is not whole-account risk. Unpriced holdings or failed account reads remain disclosed.
5. Expand weights/correlations/variance contributions, the hypothetical basket path, or method assumptions. **Export full study** includes the frozen values, routes, exact closes and fingerprint. Up to 100 studies can be retained; removing one requires the explicit confirmation control.

## What the numbers mean

- **Annualized volatility** is the sample standard deviation of daily basket returns times √365. It describes this sample; it is not a future volatility forecast.
- **Historical daily 95% VaR** is minus the empirical fifth-percentile daily return, using linear interpolation. **Tail mean loss** is minus the average of observed returns at or below that percentile, including ties. A negative loss means a gain in that historical tail; neither number guarantees a maximum loss or a future probability. The actual tail sample size is shown.
- **Correlation** compares contemporaneous daily simple returns. Constant series have undefined correlations, including their diagonal. No significance or causal claim is made.
- **Share of variance** measures each weighted asset's contribution to sample basket variance. An offsetting asset may contribute negatively. Zero-risk variance shares and diversification ratios remain undefined.
- **Hypothetical return and maximum drawdown** come from reapplying today's normalized weights every day, without fees or slippage. They are not the account's actual historical holdings, cash flows or execution performance.

## History and coverage

Every selected asset uses the exact conversion route observed in its current reference valuation. Inverse and bridge legs require their own historical closes. Stablecoins and fiat are not assumed equal; only USDT itself is the denomination identity. An all-USDT basket has constant value in USDT by definition.

Only the most recent common **consecutive** daily suffix is scored. At least 31 common closes are needed for 30 returns; missing days are not bridged, filled or replaced with another source. Earlier shared closes discarded after a gap and lag from the latest completed day are disclosed. Providers may return less than the requested maximum. Eight assets, sixteen distinct history legs and one running study bound work.

Ask Accountant about a selected study to inspect saved evidence through native ProtoLink tools. It cannot calculate a new study, alter weights, optimize an allocation or change execution policy. Correlation-based alerts/enforcement and broader wallet coverage remain pending.
