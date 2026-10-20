# Markets and analytics

The six-asset reference watchlist covers BTC, ETH, SOL, LINK, AVAX, and DOT. Each row shows its actual quote currency, observation time and missing/stale values. The chart's searchable spot catalog is broader: exchange feeds list active provider spot markets; demo supports those six bases against USDT, USDC, USD, BTC, and ETH, excluding identical pairs.

## Choose a feed

Use the **Market feed** switcher for a temporary page selection. **Workspace default** follows the feed saved in [Settings → Market data](settings.md#market-data). Public exchanges need no API key. Saved account feeds retain their production/test environment. CryptoCompare and CoinGecko Demo/Pro require their respective provider keys. The source appears in every response and follows your Analyst conversation.

The override is bookmarkable as `?source=kraken`; it does not change the default used by Portfolio, Trade or paper strategies. Changing the source resets the analysis workspace and chooses a supported pair, timeframe and sample count. Provider failures stay visible; Demo is never substituted automatically.

CoinGecko is quotes-only in this adapter. Its watchlist works, while the page explains how to select a candle-capable feed for charts and correlations. Missing changes and volumes display **—**. Quote-only feeds never show fabricated history.

## Chart controls

Choose a supported exact market, a timeframe, and a sample size of up to 720 observations. Provider aggregation limits can reduce the choices. The API accepts 60–720 observations. Supported intervals are `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `12h`, `1d`, and `1w`, restricted to the live provider's available intervals. The currently forming candle is excluded. A provider may return fewer observations than requested.

Switch between a line chart and OHLC candlesticks. Pointer movement and the keyboard-accessible inspection slider show each candle's timestamp, open, high, low, close, and volume. The indicator toggle adds Bollinger bands and EMA 9. Export saves the supplied OHLCV sample, market, and timeframe.

Demo history is deterministic and synthetic; cross quotes are ratios of aligned demo histories, with conservative OHLC ranges. Live data uses the selected exchange or API adapter. Quotes cache for 30 seconds, candles for 60 seconds, and the spot catalog for ten minutes.

| Indicator       | Definition                                                                        |
| --------------- | --------------------------------------------------------------------------------- |
| SMA             | Rolling arithmetic close mean, default 20                                         |
| Bollinger bands | SMA ± two sample standard deviations                                              |
| EMA             | Spans 9 and 21, `adjust=False`                                                    |
| RSI             | Wilder-style smoothing over 14 periods; flat series is 50                         |
| MACD            | EMA 12 minus EMA 26, with EMA 9 signal                                            |
| ATR / ADX       | Smoothed true range / directional-movement strength over 14 periods               |
| CMF             | Rolling money-flow volume / rolling volume                                        |
| TSI             | Double-smoothed price difference / absolute difference, spans 13 and 25           |
| Volatility      | Sample deviation of candle simple returns × square root of periods per year × 100 |

Annualization uses `365 × 86400 / interval_seconds`. This assumes continuous crypto trading; an intraday annualized statistic can be unstable. Warm-up values serialize as `null`. EMA alignment describes the sample, not a forecast.

## Correlations

Enter 2–8 comma-separated canonical symbols. Choose Pearson or Spearman ranks and price levels, absolute price changes, or log returns. Candles align by timestamp before calculation. The selected chart timeframe and sample size also govern the matrix. The view shows the actual aligned observation count. Undefined constant-series coefficients display zero.

Spearman ranks each aligned series and computes Pearson on those ranks. No causal interpretation is implied. Distance correlation, MIC, Granger, regression, and SHAP remain planned.

## Analyst agent

**Ask Analyst** opens the same-page overlay and passes the selected source, symbol, timeframe, and sample limit to its ProtoLink tool. Observations come from the server. Separate selections have separate conversations.

Watchlist quotes can choose USD or USDC when USDT is unavailable, with the actual pair labeled. Analysis and correlations require exact provider pairs. Portfolio and paper reference valuation still approximate USD stablecoins at parity. Actual exchange orders require the exact supported market. See [Market data sources](../developers/market-data.md) for caching, provider limits and backend contracts.
