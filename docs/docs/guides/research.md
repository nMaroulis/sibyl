# Research, reporting, and forecasting

## Reporter: news and insights

The News screen groups a bounded feed by category. In demo mode it shows clearly labeled sample editorial, not fabricated current news. In live mode it reads the CoinDesk RSS feed, displays publisher excerpts, and links to the original articles. The feed response is limited to 2 MB and 15 stories.

Reporter reads the same feed through a native ProtoLink tool. Tool mode lists available headlines and excerpts; model mode can summarize and explain supplied reporting. The summary selector chooses the publisher excerpt or an extractive summary of up to two sentences from that excerpt. Extraction ranks sentences by repeated-word frequency and preserves their original order; it never claims to summarize the full article.

[VADER](https://github.com/cjhutto/vaderSentiment) uses a bundled lexicon and rules to score each headline plus its original excerpt. Compound polarity ranges from −1 to +1; values ≥0.05 are positive, ≤−0.05 negative, otherwise neutral. The feed panel shows counts and mean compound polarity for all displayed feed stories, independently of the category filter. These scores describe text, not market sentiment or price direction. More publishers and full-article NLP are marked **Coming soon**.

## Chronos: forecast baseline

Chronos estimates drift and sample volatility from up to 90 daily log returns. For horizon `h`, last close `P`, mean log return `μ`, and volatility `σ`:

```text
baseline(h) = P × exp(μ × h)
lower(h)    = P × exp(μ × h − 1.96 × σ × sqrt(h))
upper(h)    = P × exp(μ × h + 1.96 × σ × sqrt(h))
```

The interface shows 7, 14, or 30 days; the API accepts 1–30. The band is a theoretical approximate 95% model interval under constant drift/volatility assumptions. It has not been empirically calibrated. The central curve is a log-return baseline, not an arithmetic expected-price estimate or a trained ML forecast.

The current runtime does not load the earlier TensorFlow models, macroeconomic training pipeline, Nixtla, CryptoMamba, or ARIMA. Add a trained implementation behind a separate service and publish its assumptions and calibration before using it in the forecast screen.

## Wiki: curated education

The Crypto knowledge tab searches a small built-in glossary by keyword. Each entry includes a reference link. Concepts include RSI, moving averages, diversification, custody, key permissions, drawdown, Sharpe, correlations, and forecast intervals.

This is not an embedding database or a web-search fallback pipeline. Model-backed Wiki uses the same curated tool and can explain the retrieved entries.

## Explorer: Bitcoin blocks

The Block explorer tab reads recent Bitcoin block summaries from mempool.space in live mode. Height, timestamp, transaction count, size, and a block reference are shown. Demo blocks are explicitly marked samples. Choose 10, 25, 50, or 100 recent blocks. Inspect a transaction-count chart, mean transactions, mean size, observed mean block interval, and export CSV. Live pagination requests older batches by height. It does not track addresses, wallet balances, or pending transactions. Additional chains and deeper transaction research are marked **Coming soon**.

## Equities

The Equities tab has AAPL, MSFT, NVDA, and COIN fixtures in demo mode. In live mode, install `uv sync --extra stocks` to retrieve adjusted three-month daily history through yfinance. You may enter other supported tickers.

The view includes observed period return, sample high/low, annualized log-return volatility (252 sessions), and maximum drawdown. Available company profile fields include sector, industry, country, description, market capitalization, and trailing P/E. Fundamentals can fail independently of price history; the UI displays that limitation. Demo profiles are illustrative.

Equity Analyst uses the selected ticker. Senator portfolio archives and disclosure filters are marked **Coming soon**. Document ingestion, hybrid retrieval, embeddings, and web search are also visible as planned additions in the Knowledge tab.
