# Markets and analytics

Your watchlist starts with supported pairs for BTC, ETH, SOL, LINK, AVAX, and DOT, and can contain up to 30 markets. Each row shows its actual quote currency, observation time and missing/stale values. The chart's searchable spot catalog is broader: exchange feeds list active provider spot markets; demo supports those six bases against USDT, USDC, USD, BTC, and ETH, excluding identical pairs, plus ADA/BTC, USDC/USDT, DAI/USDT, USDT/USD and EUR/USD valuation fixtures.

## Choose a feed

Use the searchable **Market feed** picker for a temporary page selection. Exchanges and APIs have separate sections and icons; offline **Demo** is last. A **Default** badge sits beside the source saved in [Settings → Market data](settings.md#market-data), without a duplicate default option. New workspaces use **Binance**, independently of account mode. Explicit saved choices remain effective. Public exchanges need no API key. Saved account feeds retain their production/test environment. CryptoCompare and CoinGecko Demo/Pro require their respective provider keys. The source appears in every response and follows your Analyst conversation.

The override is bookmarkable as `?source=kraken`; it does not change the default used by Portfolio, Trade or paper strategies. Changing the source resets the analysis window and retains the selected coin when the new feed offers it, using a supported quote pair. Provider failures stay visible; Demo is never substituted automatically.

CoinGecko is quotes-only in this adapter. Its watchlist works, while the page explains how to select a candle-capable feed for charts and correlations. Missing changes and volumes display **—**. Quote-only feeds never show fabricated history.

## Explore any supported coin

**Explore a coin or pair** sits at the top of Markets beside the feed picker. Open it and type a ticker, coin name or full pair: for example `ADA`, `Cardano` or `ADA/USDT`. Names come from provider currency metadata, with editorial names for the research library's familiar coins. Less familiar assets remain searchable by ticker and pair.

The picker searches the complete active spot catalog returned by the selected backend client. It displays up to 80 matching rows at a time; refine the search to reach any pair. The visible coin/pair count describes the selected source. Arrow keys move through results, Enter selects, and Escape closes. The **Quick look** cards show the first four available quotes in your saved watchlist order; they do not restrict your chart selection. Selecting a pair updates the chart, indicators, export and Analyst context.

Available coins depend on the feed: exchanges expose their full active spot catalog, while Demo and the current aggregator adapters expose their six supported bases. No unsupported pair or derivative is presented as a spot market.

## Your watchlist

Use the star beside **Quick look** to watch or unwatch the pair you are viewing. **Manage watchlist** jumps to the editable list below the chart. **Add market** opens the full spot picker; choose a pair and click **Add to watchlist**. Already watched pairs are excluded from that picker. The remove button beside a row removes it immediately.

Use **Reorder**, then the up/down arrows, to move markets. Changes save automatically in the Python backend and survive page reloads and API restarts. The first four available entries become your Quick look cards. Duplicate entries are ignored, while different quote pairs such as BTC/USDT and BTC/USD can both be watched.

Each source keeps its own list, including connected exchange/test environments. Switching feeds restores that feed's saved list. An empty list stays empty until you add a pair. Unavailable or delisted pairs remain visible with **Unavailable** and can still be removed; fixtures are never substituted. Quote failures do not erase saved preferences.

Editing a watchlist changes what you follow on Markets. Portfolio valuation uses its independent reference prices, so removing a watched asset does not remove or revalue a holding. Chart and Analyst selections also remain independent from list membership.

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

Watchlist quotes can choose USD or USDC when USDT is unavailable, with the actual pair labeled. Analysis and correlations require exact provider pairs. Portfolio uses observed conversion routes without stablecoin parity; the separate paper reference-price helper still permits USD/USDC substitution. Actual exchange orders require the exact supported market. See [Market data sources](../developers/market-data.md) for caching, provider limits and backend contracts.
