---
title: Know when search should abstain
description: Fit and independently check an optional semantic cutoff using your own relevance judgments.
---

# Know when search should abstain

Nearest-neighbor search always has a nearest passage, even when none answers your question. Open **Research → My research → Know when search should abstain** to fit an optional cutoff with your own labeled questions. Once explicitly enabled, semantic search releases **one leading passage or none**. The same policy applies to Wiki and Reporter's search tool.

This is an empirical retrieval cutoff, **not a probability that an answer is correct**. Source truth and the quality of an agent's answer still require review.

## Prepare representative questions

1. Configure an embedding model and completely index the source scope you want to use. Choose **My documents**, **Retained news** or **All sources**. Documents are usually more stable; new or expired news can invalidate a saved cutoff.
2. Expand **Create a calibration experiment** and give it a title.
3. Under **Fit questions**, enter at least two questions with relevant passage IDs and at least two questions for which **No relevant source exists in this scope**. Open a source below and use **Copy passage ID**. Supply every relevant leading passage you would accept; incomplete labels can reject useful matches.
4. Under **Held-out validation**, provide another two relevant-source and two no-source questions. Use different questions across both partitions. Hard negatives and realistic paraphrases are more informative than obviously unrelated topics.
5. Choose **Embed … questions & fit cutoff**. There are 8–32 questions per experiment. Each query uses your selected embedding provider; hosted queries are sent under saved permission and may incur charges. No chat LLM is required.

Do not revise labels or tune questions after reading validation and still treat that validation as independent. Use fresh validation questions for a new experiment. Sibyl rejects duplicate normalized query strings, but cannot establish that your questions are representative or semantically independent.

## Review, then enable

The cutoff is fitted using **fit questions only**. It sits immediately above the highest-scoring incorrect fit match, including no-source questions and positive questions whose leading passage was not labeled relevant. Ties reject both matches rather than accepting a known incorrect one. Validation never chooses or adjusts the cutoff.

The report shows actual question counts, correct/incorrect accepts, relevant-question coverage, source/model fingerprints and each leading passage/score. Exact floating-point scores and the cutoff are retained in **Export evidence**. Ask Wiki to explain the saved evidence.

**Use this cutoff for semantic search** becomes available only when both fit and validation contain at least one correctly accepted relevant question, with **zero observed incorrect validation accepts**. Fitting never enables the cutoff automatically. A small validation set with no observed errors does not prove future reliability; inspect its size and missed relevant questions too.

If a high-scoring incorrect fit match forces the cutoff above every possible cosine score, the report explicitly rejects everything and cannot be enabled. If validation fails, review evidence or choose a better model/corpus; do not optimize repeatedly against the same validation questions.

## Understand the scope

- A policy applies only to **Semantic** search in its **exact selected source scope**. A policy for My documents does not also protect All sources or Retained news.
- **Keyword and Hybrid are uncalibrated.** They remain available for explicit inspection; agents are instructed not to silently switch method/scope to bypass an abstention.
- An enabled policy returns at most the leading semantic passage if its cosine meets the cutoff. It withholds other neighbors because they were not independently checked by this top-one decision rule.
- This is a retrieval filter, not an access-control rule. Source readers, exact citations and previously saved excerpts remain available.

If search abstains, it explains that the cutoff was not met. That does not make the user's claim false or prove no relevant source exists.

## Changes, stopping and retention

The corpus, source attribution, model configuration and vector contents are pinned. Adding, removing or reindexing a source, changing the model or clearing/rebuilding vectors makes an enabled cutoff **stale**. The conservative fingerprint covers the whole library, even for a narrower scope. Search then withholds evidence before sending a query to the provider. **Recheck index** refreshes status. Run and review a new experiment, or explicitly **Disable cutoff** to restore raw semantic rankings.

Concurrent policy/corpus changes also withhold late results. There is no automatic fallback to another method or Demo source. Existing ranking comparisons evaluate raw rankings so they are not biased by an active cutoff.

**Stop experiment** prevents future queries and discards a late result; it cannot undo a provider query already sent. Restart marks unfinished work interrupted without replaying it. Completed reports and enabled policies survive restart, subject to the same fingerprint checks. One calibration job runs at a time, one query per worker turn.

Keep up to 100 reports. Disable a report's active cutoff before deleting it. Removing a source does not erase excerpts already retained in calibration reports, exports or backups. Queries, judgments and report excerpts are private workspace data with local file protections, not separately encrypted credentials. Hosted model aliases cannot attest unchanged remote weights; broader real-model and forward-quality acceptance remains pending.
