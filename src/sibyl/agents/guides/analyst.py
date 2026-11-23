"""Markets navigation and analysis controls, distinct from computed market evidence."""

from typing import Literal

from sibyl.agents.guides import Guide

Topic = Literal[
    "live", "overview", "sources", "pairs", "watchlist", "chart", "statistics", "correlation", "history"
]
GUIDES = {
    "live": Guide(
        "Understand live market updates",
        "/markets",
        (
            "Choose Binance, a saved Binance Testnet source, Coinbase production or Kraken production, a supported pair and interval.",
            "The Live indicator confirms actual stream messages; Connecting, REST fallback or Paused explain interruptions and background-tab behavior.",
            "The chart includes a forming candle preview. Statistics, technical bias and Analyst analysis continue to use closed REST candles.",
        ),
        (
            "Sockets are shared while viewed, reconnect after interruptions and close when their last viewer leaves. Kraken supports native intervals; OHLC and untimestamped tickers carry local receipt timing, which does not prove last-trade freshness. Other feeds use REST; account/order streams are not implemented.",
        ),
    ),
    "overview": Guide(
        "Analyze a market",
        "/markets",
        (
            "Choose a data source, exact spot pair, timeframe and observation count in Markets.",
            "Inspect source/time labels and coverage, then use the chart, technical-bias breakdown and statistical sections together.",
        ),
    ),
    "sources": Guide(
        "Choose a market-data source",
        "/settings?tab=market",
        (
            "Configure public exchanges, saved exchange accounts or data API profiles in Settings → Market data.",
            "Choose the source in Markets; public exchange feeds need no account key. Demo is a separate explicit choice.",
            "Use a candle-capable source for technical analysis; quotes-only adapters cannot supply chart history or correlations.",
        ),
    ),
    "pairs": Guide(
        "Choose any supported coin or pair",
        "/markets",
        (
            "Open the searchable spot-pair picker and search by coin or exact pair on the selected source.",
            "Refine the query if needed; only up to 80 matches show at once. Arrow keys move, Enter selects and Escape closes.",
            "Quick look cards reflect watchlist entries; they do not restrict the chart's full market catalog.",
        ),
    ),
    "watchlist": Guide(
        "Edit your watchlist",
        "/markets",
        (
            "Use the star beside Quick look to watch or unwatch the selected pair.",
            "Manage watchlist opens the editable list. Add market opens the full picker; choose a pair and Add to watchlist, or remove a row.",
        ),
        (
            "The list supports up to 30 markets. Removing a pair does not remove a holding or alter Account valuation.",
        ),
    ),
    "chart": Guide(
        "Zoom and inspect the chart",
        "/markets",
        (
            "Choose line or candlestick view, then drag across a time region to zoom. Use pan mode or Shift+drag to move the visible interval.",
            "Use range presets, +/− controls and the history navigator to change the viewport; pointer inspection or its keyboard slider shows OHLCV.",
            "Toggle volume/indicators or export the supplied OHLCV sample.",
        ),
        (
            "Zoom changes the viewport only. Change timeframe or Observations to change the statistics/Analyst sample; zoom does not fetch more candles.",
        ),
    ),
    "statistics": Guide(
        "Interpret indicators and the technical-bias score",
        "/markets",
        (
            "Expand the technical-bias card for its weighted votes and read return, trend, momentum, volatility, risk, volume/flow and price-reference statistics.",
            "Read the displayed definitions and methodology for formulas, warm-up requirements and the score's method; inspect sample coverage and stale/missing inputs.",
        ),
        (
            "The score is a directional heuristic, not investment quality, a buy/sell recommendation or a probability of profit. Indicators use the latest consecutive candle segment.",
        ),
    ),
    "correlation": Guide(
        "Compare markets",
        "/markets",
        (
            "Choose exact provider pairs from the same feed in the correlation section.",
            "Expand Lag predictability for a one-to-five lag Granger comparison against the first pair, in both directions. Run explicitly, inspect training-only adjusted p-values and later-target errors, then export evidence. Gaps, model assumptions and repeated experiments limit interpretation; lag predictability is not causation or profit.",
            "Expand Return regression and select Compare with Theil–Sen to compare robust and ordinary beta on the same returns.",
            "Select Pearson, Spearman ranks or unsigned distance dependence and log returns, prices or changes. Distance uses at most the latest 360 aligned observations; undefined constant-series results show a dash.",
        ),
        (
            "Expand Return regression to compare contemporaneous log returns against the first selected market. Inspect beta, per-candle intercept, R², residual error and the pair plot; export the evidence. The intercept is not CAPM alpha and these are in-sample descriptions.",
            "Correlation describes the observed sample, not causation. Price-level correlation can be misleading; log-return comparisons are usually easier to interpret.",
        ),
    ),
    "history": Guide(
        "Import history and save research datasets",
        "/markets",
        (
            "Open History & datasets to inspect exact-source coverage, import older supported candles and review gaps.",
            "Pause/resume keeps checkpoints; rescan revisits available history. Inspect provider limits before assuming older data exist.",
            "Save a complete interval as an immutable dataset for offline backtests or JSON export.",
        ),
        (
            "Provider retention and supported pagination limit history. Saved immutable datasets are distinct from the mutable candle cache.",
        ),
    ),
}
