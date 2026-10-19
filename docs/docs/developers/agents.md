# ProtoLink integration

The supported engine range is `protolink>=0.8.2,<0.9`. Sibyl imports the public `Agent`, `RunBudget`, and `create_llm` APIs. There is no local imitation of ProtoLink and no parallel LangChain execution path.

## Module tools

| Agent          | Native tool                                                                           |
| -------------- | ------------------------------------------------------------------------------------- |
| Oracle         | `portfolio_snapshot`                                                                  |
| Accountant     | `portfolio_snapshot`                                                                  |
| Analyst        | `market_analysis(symbol="BTC/USDT")`                                                  |
| Broker         | `strategy_context(symbol, strategy, capital, candles, fee_bps, slippage_bps, window)` |
| Chronos        | `price_forecast(symbol="BTC/USDT", horizon=14)`                                       |
| Reporter       | `news_briefing(article_id="")`                                                        |
| Technician     | `connection_status`                                                                   |
| Wiki           | `search_knowledge(query="")`                                                          |
| Explorer       | `bitcoin_blocks`                                                                      |
| Equity Analyst | `equity_quote(symbol="AAPL")`                                                         |

Each native function has typed arguments and a docstring. ProtoLink derives its tool schema and validates calls. Tools call the same domain services as the HTTP API. They do not call HTTP back into Sibyl.

## Execution path

1. Validate the requested module, message length, optional session ID, and typed `AgentContext`. Reject unknown context fields.
2. Acquire the two-request concurrency semaphore.
3. Map the validated page selection to that module's explicit tool arguments, then execute its initial native tool through `agent.sync.call_tool` in a worker thread.
4. In tool mode, format that factual result directly.
5. In model mode, create a fresh Agent with `create_llm`, module instructions, and only that module's tool. Supply initial evidence and up to six matching prior session turns with the same module and context.
6. Invoke with `RunBudget(max_steps=6)` and a 90-second HTTP wait limit.
7. Persist the answer, question, validated context, initial evidence, engine/provider labels, session, and tool name.

A provider thread can finish after its HTTP request times out. It has read-only capabilities. The agent UI's evidence panel shows the initial server observation, not every subsequent model-selected call. A future richer trace view should consume ProtoLink run reports explicitly.

## Add an agent

Add its module ID to `ModuleId`, a role to `ROLES`, a typed read-only native function, and its mapping in `_tools`. The registry catalog and Agents directory then expose it automatically. Add an `AgentButton` with the module ID and typed selection to its frontend page. Keep the explicit dictionary mapping between each role and its tool easy to inspect.

For stronger isolation, move network-heavy tools to their own processes and configure ProtoLink transport separately. The current implementation intentionally embeds name-only agents without starting agent HTTP servers, registries, or A2A listeners.

## Tests

The API integration test runs all ten modules through the actual installed ProtoLink tool runtime. Model-provider behavior is tested using ProtoLink's mock LLM under controlled injection; no hosted inference or exchange funds are required. Add provider-specific integration tests separately with credentials supplied by an operator.

## Frontend integration

`AgentProvider` owns conversations above the router content so closing the dialog or switching pages does not discard them. `AgentButton` opens the selected module without navigating. Session keys combine the module ID and a canonical serialization of the page context. The shared dialog handles focus, Escape, scroll locking, retained drafts, pending requests, saved-history restoration, and native-tool evidence. Pending read-only requests may finish after the dialog closes.

Page context contains selections, not client-supplied observations or credentials. `AgentContext` allows a canonical market symbol, chart timeframe and sample limit, equity ticker, 1–30 day forecast horizon, validated backtest parameters, bounded glossary query, and news article ID. Native tools fetch the actual evidence from server services. Broker context reads simulation parameters without executing the strategy.
