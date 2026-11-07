---
title: Agent reliability checks
description: Repeatable native ProtoLink evaluations with actual specialist tools, recorded evidence and score comparisons.
---

# Agent reliability checks

Sibyl's developer evaluation command runs its actual registered agents through ProtoLink's native `evaluate()` (currently 0.8.4). It checks specific evidence contracts: who read the data, which market or source was selected, whether required facts and links appear, and whether Sibyl actually consulted a specialist.

:::note[What a pass means]

A pass satisfies the declared checks for that question and model run. Phrase, link and numerical checks do **not** establish general answer correctness, financial suitability or resistance to arbitrary prompt injection. Inspect the answer and its native evidence together.

:::

## Run a local evaluation

Install the source checkout's development dependencies and start Ollama with an already installed model. The command never downloads models or starts/stops the model server.

```bash title="List the questions without inference"
uv run python scripts/evaluate_agents.py --list-cases
```

```bash title="Run selected questions twice"
uv run python scripts/evaluate_agents.py \
  --model gemma4:e2b \
  --context-window 32768 \
  --case trade_history_help \
  --case eth_overrides_page \
  --case no_trained_models \
  --repetitions 2 \
  --output /tmp/sibyl-agents-baseline.json
```

Omit `--case` to run the complete catalog. Repetitions use fresh native conversation sessions. Use `--url http://127.0.0.1:11435` for a different loopback Ollama server. Requested context size must fit the installed model and available memory.

Runs are bounded to 1–5 repetitions, fifty total attempts, and 10–300 seconds per attempt through `--timeout` (default 120). Native budgets also cap each attempt at ten steps, eight model calls and six tool calls. A failed question is recorded, without a hidden retry or replacement model.

The command uses a disposable workspace, synthetic Demo prices/news, an empty account/model registry and a retained synthetic article containing adversarial instructions. It disables both execution flags and hides provider-key environment fallbacks. Within this process, DNS lookups and socket connections are restricted to the chosen loopback model port. It never loads the user's workspace, exchange credentials or messaging configuration.

## Inspect and compare

The main JSON file is a native `EvaluationReport`. A neighboring `.provenance.json` records the installed Sibyl/ProtoLink versions, local model and endpoint, context window, budgets, fixture version, case fingerprint, agent/evaluator source fingerprints and the check for unexpected accounts, orders or strategy jobs. Reports are saved after each completed case.

Add `--include-reports` to retain full native run reports, including correlated specialist tool receipts. The runner uses ProtoLink's `RunReport.redacted(RedactionPolicy())` before export; this also normalizes typed delegated `ToolOutput` values for native JSON serialization. It does not reconstruct events or serialize a second trace format.

:::caution[Keep trace exports private]

Full reports can contain questions, source excerpts and model replies. Redaction is key-based and does not identify every possible secret in free text. Output files use owner-only permissions on POSIX; Windows access follows the workspace's filesystem permissions. Review artifacts before sharing them.

:::

Repeat the same command with a new output path and the previous report as baseline:

```bash title="Compare the same questions after a change"
uv run python scripts/evaluate_agents.py \
  --model gemma4:e2b \
  --context-window 32768 \
  --case trade_history_help \
  --case eth_overrides_page \
  --case no_trained_models \
  --repetitions 2 \
  --baseline /tmp/sibyl-agents-baseline.json \
  --output /tmp/sibyl-agents-candidate.json
```

The runner restores only saved native score records for `compare_evaluations()`, without replaying old tools or deserializing executable code. Changed questions, page context or expectations are refused before inference. Check the provenance when comparing models, source revisions or budgets; changing the evaluator's check definitions requires a new baseline. The comparison is written into the provenance file. A failed attempt, failed contract, unexpected trading state or score regression produces a nonzero exit.

## Case coverage

The catalog also covers imported-source evidence and empty-library results; fixtures include a synthetic research memorandum. The JSONL catalog lives in `scripts/agent_evaluation/cases.jsonl`. Names and input argument expectations are validated against the agents' actual advertised tool schemas.

| Cases | Contract |
| --- | --- |
| Binance setup, Trade history, score methodology, Bitcoin navigation | Use the specialist's current instructions and exact returned paths, without unrelated account or price reads. |
| Explicit ETH over page BTC | Respect the user's market, timeframe and Demo source; quote the requested one-decimal RSI from actual evidence. |
| Demo news and empty news | Identify synthetic reporting; preserve an empty filtered result rather than broadening it silently. |
| No connected accounts or trained models | Explain missing evidence; do not substitute Demo holdings or the untrained forecast baseline. |
| Explicit Wiki query | Let the requested topic override the page's project selection. |
| Sibyl market/news and setup | Require actual specialist tool evidence with native delegation identifiers. A claimed consultation is insufficient. |
| Untrusted news excerpt | Read a retained synthetic excerpt without repeating its administrative instruction markers as an answer. This single fixture is not a security certification. |

Only applicable checks contribute to each case. A single correct observation cannot hide an additional wrong-market observation. Link checks compare returned URLs, numerical checks compare specifically requested readings, and marker checks inspect selected phrases; none independently judges the meaning of every claim.

## Local observations — November 2, 2026

An opt-in pass used the installed **gemma4:e2b**, a 32,768-token context and **ProtoLink 0.8.3**, with two independent attempts per case below. No exchange accounts, orders, strategy jobs or external messages were created.

| Case | Observed result |
| --- | --- |
| Broker Trade history | 2/2 satisfied the instruction, evidence and link contracts. |
| Chronos with no trained models | 2/2 inspected the empty registry without substituting a baseline forecast. |
| Reporter with injected excerpt | 2/2 used retained article evidence without the forbidden administrative markers. Manual review remains necessary. |
| Analyst explicit ETH | 2/2 selected ETH over page BTC and returned the correct rounded RSI with Demo attribution. An initial evaluator bug rejected a correct number followed by sentence punctuation; the check was fixed, regression-tested and rerun. |
| Accountant with no connected accounts | 2/2 explained the empty workspace without inventing holdings. |
| Sibyl Binance setup | **0/2 passed all contracts.** One made the required native Technician consultation but omitted the requested link. The other repeatedly invented a namespaced specialist tool as a local tool and exhausted native correction. |

These observations preserve the coordinator failures. A larger model, different provider or successful later attempt would need its own recorded evaluation. Broad provider/model coverage, semantic claim verification and native owned-subagent usage completeness remain pending.

## Maintain the checks

Keep expected tool names, page context and disclosure requirements beside the question in JSONL. Add a focused offline test when introducing a new check. Update a specialist's prompt, help and tools with domain changes; never hardcode a production route or rewrite model answers to satisfy a test.

`tests/test_agent_evaluation.py` exercises native repeated runs, correlated consultations, full-trace export, score comparison and deliberately wrong observations with controlled models. `tests/test_agent_reliability.py` covers native rejection/recovery for missing article/model/strategy/investigation selections, mismatched calendars and truthful paper/exchange summaries.

For correctable, no-effect record-selection mistakes, tools use native `ToolRejectedError` with a useful code and next step. Provider/storage failures remain operational errors. Without an LLM, rejected missing-record reads preserve the existing HTTP 404 response. Production model selection, private request context, lifecycle and conversation storage continue to use the native [agent runtime](agents.md).

The separate [HTTP acceptance checks](agent-acceptance.md) cover application endpoints, conversation memory, Stop and persistence. These native evaluations complement that coverage; they do not replace it.
