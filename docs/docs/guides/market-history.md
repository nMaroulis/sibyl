# Market history and saved datasets

Open **Markets → History & datasets**. This workspace reads retained candles locally, including after a source becomes unavailable. It does not fetch new exchange prices just to display coverage.

## Retain and import candles

Successful closed-candle reads are saved automatically by exact **source, environment, pair and timeframe**. BTC/USD and BTC/USDT remain separate. Public exchange data and connected-account data also keep distinct identities.

Select a feed or a retained series. Enter the exact pair, choose a timeframe and set a UTC range. **Until** is exclusive. Inspection uses whole intervals inside those boundaries; displayed dates outside the input fields use your local timezone.

**Import this range** queues a bounded background job. It checks up to 200 intervals per page, with smaller pages where provider aggregation requires it. You can pause, resume, or rescan its saved range. A different range requires pausing an active job first. Restarting the API resumes the last committed checkpoint; a partially received page cannot advance it.

Reviewed pagination covers Demo, Binance, Binance.US, Binance Testnet, Coinbase Advanced Trade, Coinbase Exchange Sandbox, Kraken and CryptoCompare. Saved account feeds use the corresponding reviewed adapter. Availability still depends on geography, provider history and API plan. Other candle-capable feeds retain their successful chart samples but do not yet support background historical imports. CoinGecko is quotes-only.

- **Kraken:** only its recent 720 intervals are available, including the forming candle. Old history cannot be recovered with pagination.
- **Demo:** 730 synthetic intervals per timeframe. It is explicitly labeled and never substitutes for an unavailable live feed.
- **CryptoCompare:** requires its configured API key; minute history and other coverage depend on the provider plan. Weekly seven-day aggregates are omitted until their calendar alignment is reviewed.

## Understand coverage

Coverage compares stored timestamps against the expected closed UTC interval grid. Weekly candles open on Monday. Missing intervals stay missing: Sibyl does not interpolate prices or invent volume.

**Complete** means every expected candle in the inspected range is retained. A finished import can instead end with **gaps**. No trades, listing dates, unavailable older history or an interrupted provider response can all explain missing periods. These observations alone do not identify the cause.

The workspace reports retained extent, the latest closed interval boundary, missing counts and gap ranges. Up to 100 gap ranges are listed. A query covers at most 50,000 intervals and previews the latest 2,000 stored candles; the interface discloses when the preview is truncated. Narrow the dates to inspect an older portion.

## Save a research input

Choose a complete interval of **60–20,000 consecutive candles**, name it and click **Save dataset**. The snapshot copies every candle, records source/environment/pair/timeframe and receives a SHA-256 content fingerprint. Identical inputs are deduplicated.

Later provider corrections or archive pruning cannot change this copied input. **Saved datasets** lists the snapshots, offers full JSON exports and opens **Backtest** with that input selected. The pair, timeframe and sample count are fixed; strategy settings remain editable. Saved-dataset backtests do not contact a provider or require an active exchange account.

Current-feed backtests also save their exact input automatically. Results show the dataset fingerprint, recorded engine version, **Reuse input** and **Export input**. Repeatability requires the same input, parameters and engine code; the recorded version is provenance, not a bundled historical Python runtime. Existing older results without snapshots do not gain reconstructed inputs.

Dataset selection does not start a running strategy. Choose current-feed input to launch a separate paper strategy. Agents still inspect their existing contextual tools; the broker overlay does not automatically analyze the saved snapshot.

## Navigate a chart

Both line and candlestick views have zoom buttons, range presets, a draggable chart, a full-sample navigator, volume controls and a visible-candle CSV export. Hover or use the inspection slider for OHLCV details.

Focus the chart and use **arrows** to inspect, **Shift+arrows** to pan, **+ / −** to zoom, **Home / End** to inspect the edges and **Shift+Home / End** to move the window. Double-click or use Reset to return to the latest bars. Price lines break at missing intervals; amber markers identify gaps. Bars are spaced by observation rather than elapsed time.

Rendering is bounded to **600 visible candles** and a 160-point overview. Pointer updates are scheduled with animation frames and candle marks are memoized. Zoom and inspection use the already loaded data; they make no provider requests and add no charting dependency.

## Storage and retention

Mutable history is bounded to **100,000 candles per series** and **1,000,000 per workspace**. Up to **12 imports** can be active and **1,000 immutable datasets** can be retained. Storage-budget failures are explicit; no old rows are silently discarded.

**Manage retention** removes mutable observations before a UTC cutoff after you type the displayed confirmation. Pause the series import first. Saved datasets remain retained, so pruning the archive does not reclaim their copied inputs. Back up the complete workspace database and vault key using the existing local backup procedure.

Imports now share provider read budgets and cooldowns with interactive requests. Source diagnostics are available in Settings → Market data. WebSockets, exact endpoint-weight quotas, durable health history and coordinated multi-worker imports remain pending. See the [updated implementation checklist](../developers/backend-roadmap.md).
