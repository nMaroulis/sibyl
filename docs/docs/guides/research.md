# Research, reporting, and forecasting

## Reporter: news and insights

The News workspace has **Headlines**, **Tone & trends**, and **Sources** tabs. The reader follows your saved **Settings → News** selections; use its **News settings** link to change them. Select public publisher cards to read CoinDesk, Cointelegraph, Decrypt, The Block, and CryptoSlate, even while exchange accounts stay in demo mode. These public collectors need no news API key. **Demo briefings** are explicitly illustrative stories and dates, kept separate from real reporting.

The Python backend collects official RSS/Atom feeds, stores bounded publisher excerpts in a persistent local archive, and removes duplicate article URLs and same-publisher/day identical titles. Open the original source for full reporting. Filter by publisher, one of 20 recognized asset mentions, time window, keyword, and text polarity. Filters apply on the backend; links retain your selections. Use **All retained** to include articles with unavailable publication dates. The archive starts with your own collection; it is not a complete historical dataset.

**Tone & trends** shows daily story counts, mean text polarity and asset-mention groups. [VADER](https://github.com/cjhutto/vaderSentiment) scores the original English headline plus publisher excerpt. Compound polarity ranges from −1 to +1: values ≥0.05 are positive, ≤−0.05 negative, otherwise neutral. Totals and means cover all matching stories before pagination. An empty selection has no mean. UTC charts exclude undated stories. Asset groups describe stories mentioning an asset, not sentiment directed at that asset. These scores measure wording, not investor positioning or price direction.

The summary selector chooses the publisher excerpt or an extractive selection of up to two excerpt sentences. It never claims to summarize the full article. **Read full article** opens the original reporting at its publisher. Each card credits the publisher prominently. Demo stories open a labeled sample reading dialog. One **Ask Reporter** button at the top opens in place with the selected filters. Reporter uses the same backend archive, source links, dates and analysis through its native ProtoLink tool. A missing or expired story fails explicitly.

Without a configured AI model, a small notice links to **Settings → AI models**. Reporter still retrieves source excerpts in tool mode; AI explanations require a model. Mock mode is labeled as simulated. News collection, VADER sentiment, extractive summaries and Fear & Greed work independently of an LLM. Connecting one does not change or calibrate the sentiment scores.

**Fear & Greed** restores the Alternative.me Bitcoin market index, with its publication date, yesterday/week/29-day comparisons and adjacent source credit. It is distinct from article text polarity. Demo mode uses illustrative backend index values. Outages preserve the last observation with a Stale badge, rather than inventing a replacement.

Choose default providers and optional API credentials in **Settings → News**. CryptoSlate supports RSS or a public website collector. NewsAPI adds optional crypto keyword search with your encrypted provider key. A source note at the bottom of News names the enabled collectors and links to the original publishers.

**Sources** shows each publisher's retained story count, last attempt, last successful check, and Fresh/Stale/Unavailable status. Failed publishers keep previous excerpts visibly marked; live news never substitutes demo stories. Refresh normally checks due feeds every 10 minutes, with a one-minute manual refresh cooldown. The browser polls while News is open. To collect continuously while the API runs, set `SIBYL_NEWS_MODE=live`; this does not enable live trading. Retention defaults to 30 days and a 5,000-story cap. Model-based finance sentiment, entity-targeted analysis and licensed full-article summaries are **Coming soon**.

See [News ingestion and sentiment](../developers/news.md) for configuration, API filters, storage, source safety, analysis assumptions and extension points.

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

## Crypto profiles: the wider picture

Open **Research → Crypto profiles** to browse 20 familiar cryptocurrencies. Search by name or symbol and filter by category. The selection includes Bitcoin, Ethereum, Tether, BNB, XRP, Solana, USDC, Dogecoin, Cardano, TRON, Avalanche, Chainlink, Polkadot, Litecoin, Bitcoin Cash, Monero, Stellar, Shiba Inu, Uniswap, and Ethereum Classic. This is an editorial selection for familiarity and variety, not a live top-20 ranking or investment recommendation.

Profiles are fetched by the **Python backend**, not assembled from frontend copy. This public educational research works even when market/trading mode is demo. It never reads exchange credentials or private account data.

- **CoinPaprika** supplies the project description, reported launch date, consensus and organization details, available contributor information, project links, and USD market/supply statistics. All-time highs and price changes are provider observations, not portfolio returns.
- **Wikipedia** supplies the introduction and selected history/background sections, with the article title, revision ID, retrieval date, source link, and CC BY-SA attribution. These are bounded excerpts, not generated summaries or a complete history. BNB uses the Binance article and explicitly notes the broader exchange context.
- **Ask Wiki** opens the normal in-page agent dialog with the selected asset ID. Its native ProtoLink tool reads the same fetched profile and sources. Tool mode quotes a bounded overview; model mode can explain the supplied evidence.

Selections can be bookmarked, for example `/research?tab=crypto&asset=btc-bitcoin`. Switching assets fetches only the selected profile. Metadata and encyclopedia text cache for 24 hours; market observations cache for 15 minutes. Public JSON cache files live in the workspace's `crypto-research/` directory and survive API restarts. Each provider component has its own timestamp and failure state. Unavailable sources retry at most once per minute; other available sections remain readable. A failed refresh may show the last successful observation, explicitly marked **Stale**. The backend never substitutes invented descriptions, history, or prices.

Missing dates, supply fields, team information, and prices remain visibly unavailable. Maximum supply is not inferred when the provider omits it. Market prices may differ from your exchange, and stablecoins can deviate from their target. The profile includes official websites, explorers, code, and whitepapers where CoinPaprika supplies them, plus links to read the full source material.

Sources: [CoinPaprika API](https://coinpaprika.com/api), [Wikipedia text extracts API](https://www.mediawiki.org/wiki/Extension:TextExtracts), and [Wikipedia text license](https://creativecommons.org/licenses/by-sa/4.0/).

## Explorer: Bitcoin blocks

The Block explorer tab reads recent Bitcoin block summaries from mempool.space in live mode. Height, timestamp, transaction count, size, and a block reference are shown. Demo blocks are explicitly marked samples. Choose 10, 25, 50, or 100 recent blocks. Inspect a transaction-count chart, mean transactions, mean size, observed mean block interval, and export CSV. Live pagination requests older batches by height. It does not track addresses, wallet balances, or pending transactions. Additional chains and deeper transaction research are marked **Coming soon**.

## Equities

The Equities tab has AAPL, MSFT, NVDA, and COIN fixtures in demo mode. In live mode, install `uv sync --extra stocks` to retrieve adjusted three-month daily history through yfinance. You may enter other supported tickers.

The view includes observed period return, sample high/low, annualized log-return volatility (252 sessions), and maximum drawdown. Available company profile fields include sector, industry, country, description, market capitalization, and trailing P/E. Fundamentals can fail independently of price history; the UI displays that limitation. Demo profiles are illustrative.

Equity Analyst uses the selected ticker. Senator portfolio archives and disclosure filters are marked **Coming soon**. Document ingestion, hybrid retrieval, embeddings, and web search are also visible as planned additions in the Knowledge tab.
