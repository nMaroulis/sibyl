# Local momentum example

A real causal momentum plugin using Sibyl's research-only Python contract. Review the source, then install it into Sibyl's environment with `uv pip install --no-deps ./examples/strategy-plugin`. Set `SIBYL_STRATEGY_PLUGINS=["local-momentum"]` and restart. Open Strategies → Custom Python strategies.

It buys when the configurable trailing close return exceeds the positive threshold and exits below its negative threshold. Both the lookback and threshold are bounded controls. It has no I/O, training, random state or exchange access. Historical results do not establish profitability. See [the complete plugin contract](https://nmaroulis.github.io/sibyl/developers/strategy-plugins/).
