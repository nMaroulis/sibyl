---
title: Saved investigations
description: Reusable research questions, versioned reports and inspectable specialist evidence.
---

# Saved investigations

Open **Sibyl → Investigations** to connect account, market, news or strategy evidence in a report you can revisit.

:::tip[A question worth returning to]

“Compare the selected market’s trend and volatility with the available news. Explain what agrees, what contradicts it, and what we still don’t know.”

:::

## Save your question

Choose **New investigation**, enter a title and question, or use a template. Expand **Starting context** to choose a pair, timeframe, account view, market feed and news selection. These are defaults, not restrictions: your question can request other comparisons. Recorded evidence identifies what was actually used.

Saving does not contact a model. You can save questions before configuring an LLM, then connect one in [AI model settings](settings.md). **Save & investigate** saves the question and explicitly starts its first run.

Demo is optional. Select Demo sources explicitly for synthetic observations; Demo market/news inputs and simulated models receive separate labels. Market and news research do not require active exchange accounts. Missing account data stays missing.

## Follow the investigation

Sibyl uses the existing ProtoLink registry and chooses the specialists to consult. The page shows actual consultation progress. You can navigate away and reopen it without starting another model request.

**Stop** cancels the selected pending run. Completed tool observations remain inspectable, and previous completed reports stay unchanged. Stopped, failed and interrupted attempts do not become successful reports. Restart marks unfinished work interrupted; it never automatically replays inference.

## Read the report

| Section | What it contains |
| --- | --- |
| The bigger picture | Sibyl’s summary |
| Findings | Interpretations and references to completed specialist tools |
| What remains uncertain | Limitations and missing evidence |
| Questions worth exploring | Follow-up research ideas |
| Recorded evidence | Source links, native tool attribution, retrieval times and bounded observation previews |

A citation must match a completed tool receipt. This checks provenance, not whether every sentence follows correctly from its source. Uncited findings remain explicitly uncited. A report without receipts displays a warning. An invalid answer schema or invented tool reference leaves the attempt failed instead of publishing a fabricated report.

Retrieval time is when a tool returned. Prices, articles and account observations can be older: inspect their own dates and warnings. Reports are model interpretations, not independently verified facts or trading instructions. Older saved reports provide historical context, not fresh market observations.

## Rerun, compare and export

**Rerun investigation** creates a new version and fresh conversation. It uses the saved question and starting selections, current model settings and evidence then available. Workspace-default feeds resolve again on each run. It is not an exact replay of an earlier data snapshot.

The entire team’s model configuration is frozen when a run is accepted, including time spent waiting for a slot. Later settings edits affect later runs. Each version records provider/model choices without credentials.

Use **Report** to reopen a version and **Compare versions** for a side-by-side view. Comparison reads saved reports without another model answer. **Export** downloads the selected report, original selections and bounded source previews as JSON. Previews beyond 16,000 characters are marked truncated; fingerprints identify redacted observations, not independently verified facts.

## Privacy and retention

Reports and conversations stay in the local backend workspace. Exports can contain private account research: share them deliberately. Exchange credentials are not agent tool inputs. Model credentials remain in the encrypted provider vault and private execution context.

The workspace retains up to 100 investigations and 50 runs per investigation, with one pending run per investigation and four pending investigations overall. Scheduled versions have their own configurable retention policy; manual versions are preserved by that policy. Deleting an investigation removes its reports/previews but keeps its separate Chat conversations. Deleting a conversation leaves completed report text/previews intact; native run details can then be unavailable.

Choose **Schedule** to authorize [daily/weekly briefings](briefings.md) and optional Telegram delivery. Archive an active or paused calendar before deleting its investigation. Resumable multi-stage work remains pending; interrupted inference is never automatically replayed.
