# News ingestion and sentiment

`Research.news()` delegates to `news/NewsService`. Every route and Reporter's native ProtoLink tool reads that service. React does not fetch publisher URLs or maintain its own article fixtures.

## Components

| Module                          | Responsibility                                                                                                        |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `news/feeds.py`                 | Reviewed publisher catalog, `NewsProvider` interface, `RSSProvider`, RSS/Atom parsing and URL/text/date normalization |
| `news/repository.py`            | SQLite archive, deduplication, retained collection state and pruning                                                  |
| `news/sentiment.py`             | Bundled VADER analysis, rule-based asset mentions, extractive summaries and filtered aggregates                       |
| `news/demo.py`                  | Clearly illustrative offline stories, isolated from publisher persistence                                             |
| `news/service.py`               | Source refresh, single-flight collection, query filters, source health and story lookup                               |
| `components/news-workspace.tsx` | Backend-filtered reader, sentiment chart and publisher health UI                                                      |

## Collection and persistence

Five public English-language publisher feeds are available: [CoinDesk](https://www.coindesk.com/arc/outboundfeeds/rss), [Cointelegraph](https://cointelegraph.com/rss), [Decrypt](https://decrypt.co/feed), [The Block](https://www.theblock.co/rss.xml), and [CryptoSlate](https://cryptoslate.com/feed/). Availability and feed formats can change. The Sources tab reports each publisher separately; success does not imply that the feed covers all of that publisher's articles.

Saved News settings take precedence over the environment default. Until a profile is saved, `SIBYL_NEWS_MODE=auto` follows the workspace market mode. `demo` or `live` overrides news independently. When the resolved default is live, a separate lifespan task checks every 30 seconds and collects feeds due under `SIBYL_NEWS_REFRESH_SECONDS` (default 600). A live News request also refreshes due feeds, allowing public news in a demo trading workspace without changing the default. The UI polls every minute while mounted. On-demand requests may wait for initial collection; subsequent requests read the archive until a feed is due. The strategy worker has its own loop.

An instance lock prevents overlapping collection rounds in the single-process application. Up to five publisher requests run concurrently. Each uses a 12-second HTTP timeout, disables redirects, limits the decoded response to 2 MB while reading, and considers at most 60 entries. ETag and Last-Modified persist across restarts and are sent on later requests. HTTP 304 counts as a successful check and retains previous excerpts. Bumping an adapter's `cache_version` invalidates its HTTP validators on the next collection, so parser changes can refresh unchanged feeds. Manual refresh bypasses the normal interval but still has a 60-second per-source cooldown.

Public excerpts live in `SIBYL_DATA_DIR/news.sqlite3`, separate from credentials. Rows retain a stable article ID, source/publisher, canonical URL, title, bounded excerpt, category, publication date, first-seen time, latest collection time, asset tags and VADER scores. Feed state retains the last attempt/success, conditional validators and a sanitized error. Unknown publication dates remain null; first-seen time is used for archive retention and sorting, not presented as the publication date.

The ID is a hash of the canonical publisher URL. Canonicalization strips fragments and known tracking parameters, preserving meaningful query parameters. The repository also merges identical normalized titles from the **same publisher on the same UTC publication day**, preserving the first ID. When NewsAPI returns an already archived publisher URL, one article retains all collector IDs; original publisher attribution stays intact and direct publisher excerpts take precedence. Provider filters and source counts use those collector IDs, so a story can appear in more than one provider count without duplicating the overall article. Disabled collectors are excluded from the active feed without deleting the archive. Different publishers' reporting stays separate: there is no semantic story clustering claim. Successful later collection updates wording and scores without losing the original first-seen timestamp.

Retention defaults to 30 days (`SIBYL_NEWS_RETENTION_DAYS`, 1–365), with a hard cap of 5,000 articles. Pruning happens during collection; reads also exclude expired records. The archive begins when Sibyl collects it and is not a historical backfill service. New connections and accounts do not alter news data.

## Failure behavior

- **Fresh:** a recent successful feed check, including HTTP 304.
- **Stale:** a previously successful source has a failed check or has not succeeded for twice the configured interval. Existing excerpts remain readable.
- **Unavailable:** an attempted source has never succeeded.
- **Not fetched:** no attempt has been recorded.

Live mode never falls back to samples. Total publisher failure returns an empty live archive, explicit source errors and a null mean polarity. Successful sources remain useful when another publisher fails. Redirects require a reviewed catalog update. The parser rejects DTD/entity declarations, removes markup and script/style content, accepts only publisher-owned HTTPS article links, and rejects implausibly future dates. Feed content remains untrusted evidence for agents; it never supplies system instructions.

## Query contracts

`GET /api/v1/news` accepts:

| Parameter          | Meaning                                                                                                          |
| ------------------ | ---------------------------------------------------------------------------------------------------------------- |
| `mode`             | Optional `demo` / `live`; otherwise use the resolved news setting                                                |
| `summary`          | `excerpt` (default), or `extractive` (up to two excerpt sentences)                                               |
| `publisher`        | Catalog ID, e.g. `coindesk`                                                                                      |
| `asset`            | One of the 20 uppercase symbols returned in `facets.assets`                                                      |
| `sentiment`        | Empty, `positive`, `neutral`, or `negative`                                                                      |
| `q`                | Up to 200 characters; every whitespace-delimited term must match the title/excerpt literally, case-insensitively |
| `days`             | Rolling publication-date window, default 7; 0 includes all retained and undated stories                          |
| `limit` / `offset` | 1–100 (default 24) / 0–5,000; newest first with a stable ID tiebreaker                                           |

The response's `total` and `sentiment` describe the complete matching set **before** pagination. `items` is the requested page. `archive_count` describes the retained pool before query filters. `sources` reports all configured publishers, independently of filters. `facets` supplies the publisher and asset choices. Empty samples have a null mean rather than a neutral-looking zero. Daily groups use UTC publication dates and omit undated stories, which are counted separately. Asset groups may overlap because an article can mention multiple assets.

The News UI omits the API's optional `mode` override so the reader always follows workspace News settings. It removes legacy `mode` URL parameters without changing other filters. The reader checks the resolved provider from `/system` for its tools-only or mock-model notice; unknown/loading/error states do not imply a missing model. Model changes trigger the same `sibyl-refresh` event used by other workspace resources.

Other routes:

- `GET /api/v1/news/sources`: source status without initiating network calls.
- `POST /api/v1/news/refresh`: public collection with cooldown; returns `attempted` and `in_progress`.
- `GET /api/v1/news/{id}?mode=live`: retained story lookup independent of current filters/page; missing or expired IDs return 404.

Reporter receives validated page selections through `news_mode`, `news_publisher`, `news_asset`, `news_sentiment`, `news_days`, `query`, and optional `article_id`. Its read-only tool supplies at most eight matching articles plus aggregate evidence. A selected article is resolved against the whole retained archive. Missing IDs fail explicitly, rather than selecting another headline. In tool mode Reporter formats actual excerpts, publisher/date/URL and scope; the configured ProtoLink model can explain that same evidence.

## Analysis boundaries and extension

[VADER](https://github.com/cjhutto/vaderSentiment) 3.3.2 is the current English lexicon/rule baseline. Input is the original headline plus publisher excerpt, even when an extractive summary is selected. Labels use the standard compound thresholds: ≥0.05 positive, ≤−0.05 negative, otherwise neutral. The mean gives each article equal weight. No confidence probability, finance-specific accuracy claim, social positioning index, or price forecast is inferred.

Asset tags match names and uppercase tickers. They describe mentions, with inevitable ambiguity and missed mentions. An article's score is not targeted to each mentioned asset. Publisher selection, repetition, sample size, English wording and changing archive coverage affect all aggregates. Extraction ranks excerpt sentences by repeated-word frequency, then preserves source order; it does not read the linked full article. No language model or model weights are downloaded for this pipeline.

To add a publisher, implement `NewsProvider.fetch(state, now) -> FeedResult`, or add a reviewed RSS `FeedSource`. Keep transport, ingestion, analysis and UI separate. Add fixture-based parser/transport/health tests and verify the publisher's actual endpoint. The reader opens full reporting at its original publisher, with no paywall bypass. Full-article processing should use an appropriately licensed source. Finance-trained and entity-targeted models remain future work and should expose model version, input scope and evaluation evidence.

Run `uv run pytest tests/test_news.py` for parser, conditional transport, deduplication, persistence, cooldown, concurrency, outage, filtering, sentiment scope, API and Reporter contracts. Tests use mocked HTTP and isolated temporary archives.

## Saved collectors, API access, and web collection

`services/data_settings.py` owns News settings and saved public market choices. Profiles are encrypted with the workspace vault key using `Store.data_profile` / `save_data_profile`. API responses expose key presence only. News selections apply to subsequent reads; public market changes are saved for restart so a request cannot combine an old quote with a new source label.

- `GET /settings/news`: mode, enabled source IDs, collector choices, NewsAPI query, `has_api_key`, and the provider catalog.
- `POST /settings/news`: save `mode` (`auto`, `demo`, `live`), `sources`, `cryptoslate_method` (`rss`, `web`), `query`, optional `api_key`, and optional `clear_api_key`. Omitted keys are preserved; enabling NewsAPI requires a key. Live/default configurations require at least one public source. Explicit Demo selections normalize the source list to empty, including older saved profiles; saved API credentials remain encrypted and unused. The UI chooses sources through selectable logo cards and saves explicit demo/live mode. Demo is exclusive; public choices can be combined.
- `GET /settings/market`: distinguish `active` and `saved` mode/exchange choices and `restart_required`.
- `POST /settings/market`: save a supported production exchange ID and demo/live market mode for startup. Execution permission remains separately configured.

`news/providers.py` implements two additional collectors. **CryptoSlateWebProvider** fetches the fixed publisher robots.txt first, honors disallow rules, and reads semantic homepage article cards: title, link, excerpt and publication timestamp where supplied. It does not crawl linked article bodies. The response is capped at 2 MB, redirects are not followed, and an unsupported layout becomes an explicit source failure. No RSS fallback is silently substituted when Website collector is selected.

**NewsAPIProvider** calls the fixed [Everything endpoint](https://newsapi.org/docs/endpoints/everything) with English crypto search, newest-first ordering and at most 50 articles. The saved credential travels only in the [X-Api-Key header](https://newsapi.org/docs/authentication). The backend retains the original publisher name, URL, date and description, with `newsapi` as a collector ID. Publisher links are displayed, not fetched by the adapter. It does not treat the API's truncated content field as a full article. Plan access and quotas are provider-controlled; local tests mock authenticated calls and do not verify an actual account.

Changing collector version or search query triggers a new collection without reusing incompatible HTTP validators. Failed attempts record their attempted version too, preserving cooldown even when a new adapter fails. All request failures are sanitized before being returned to clients or agent tools.

## Fear & Greed index

`news/fear_greed.py` reads the public [Alternative.me API](https://alternative.me/crypto/fear-and-greed-index/#api) at `https://api.alternative.me/fng/?limit=30`. `GET /news/fear-greed` uses the resolved news mode unless a demo/live override is supplied. Public responses include dated values, provider classifications, 30 observations where available, exact-date comparisons, attribution, and freshness metadata. Demo responses contain explicitly illustrative backend values and dates.

The raw value must be an integer from 0 to 100. Unrecognized classifications, future dates, repeated dates and malformed or empty responses are rejected. Comparisons look up yesterday, seven days ago and 29 days ago by date; missing days remain unavailable. Public observations persist in the news database's `observations` table. The client caches for one hour, retains previous observations on failure and marks them stale. A response more than two days behind, or a cached check more than two hours old, is also marked stale. Total failure produces unavailable values, never a sample fallback.

Alternative.me attribution and its link appear immediately beside the displayed index, including the provider's observation date. The index is Bitcoin-focused market mood, separate from VADER's article language polarity. Reporter can inspect the cached index through its briefing evidence without initiating another index fetch. No weights, classifications or prices are invented from the headlines.
