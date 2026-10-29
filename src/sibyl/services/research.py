"""News, education, blockchain, and optional equities behind explicit data sources."""

import re
from datetime import UTC, datetime

import httpx

from sibyl.blockchain.bitcoin import BitcoinExplorer
from sibyl.config import Settings
from sibyl.news import NewsService
from sibyl.news.fear_greed import FearGreed
from sibyl.services.analytics import performance_metrics
from sibyl.services.crypto_library import CryptoLibrary
from sibyl.services.data_settings import DataSettings

KNOWLEDGE = [
    {
        "term": "Diversification",
        "category": "Portfolio",
        "text": "Spreading exposure across assets can reduce concentration, but crypto assets often become more correlated during market stress.",
        "url": "https://www.investor.gov/introduction-investing/investing-basics/asset-allocation",
    },
    {
        "term": "Relative Strength Index",
        "category": "Indicators",
        "text": "RSI compares smoothed gains and losses over 14 periods. Readings below 30 or above 70 describe recent momentum, not guaranteed reversals.",
        "url": "https://www.tradingview.com/support/solutions/43000502338-relative-strength-index-rsi/",
    },
    {
        "term": "Moving averages",
        "category": "Indicators",
        "text": "EMA weights recent prices more heavily than SMA. Crossovers are lagging trend signals and can whipsaw in sideways markets.",
        "url": "https://www.tradingview.com/support/solutions/43000502249-moving-average/",
    },
    {
        "term": "API key permissions",
        "category": "Security",
        "text": "Create a dedicated read-only key for Sibyl, restrict it by IP where available, and disable withdrawals. Delete the key at the exchange to revoke access.",
        "url": "https://docs.ccxt.com/",
    },
    {
        "term": "Paper trading",
        "category": "Trading",
        "text": "A simulated execution ledger is useful for testing workflows. It does not reproduce real queue priority, liquidity, outages, or market impact.",
        "url": "https://www.investor.gov/introduction-investing",
    },
    {
        "term": "Drawdown",
        "category": "Risk",
        "text": "Drawdown is the fall in equity from a previous peak. Maximum drawdown describes the worst such decline during an observed period.",
        "url": "https://www.investor.gov/introduction-investing",
    },
    {
        "term": "Sharpe ratio",
        "category": "Risk",
        "text": "Sibyl divides mean candle equity return by its standard deviation and annualizes using the selected timeframe, with zero risk-free rate. Short samples are unstable.",
        "url": "https://www.investor.gov/introduction-investing",
    },
    {
        "term": "Backtesting",
        "category": "Strategies",
        "text": "Historical simulations require fees, realistic fill timing, and out-of-sample testing. Selecting a strategy on its backtest can overfit the same history.",
        "url": "https://www.investor.gov/introduction-investing",
    },
    {
        "term": "Bitcoin confirmations",
        "category": "Blockchain",
        "text": "Transaction inclusion supplies its first confirmation; later blocks add confirmations. Reorganizations can change inclusion, and confirmation times vary.",
        "url": "https://bitcoin.org/en/how-it-works",
    },
    {
        "term": "Self custody",
        "category": "Security",
        "text": "A private key controls on-chain funds. Never enter a wallet seed phrase in Sibyl. Exchange API credentials are different from wallet private keys.",
        "url": "https://bitcoin.org/en/secure-your-wallet",
    },
    {
        "term": "Forecast intervals",
        "category": "Forecasting",
        "text": "A model interval depends on its assumptions. Sibyl's log-return baseline assumes constant drift and volatility; its 95% band is not empirically calibrated.",
        "url": "https://otexts.com/fpp3/prediction-intervals.html",
    },
    {
        "term": "Correlation",
        "category": "Analytics",
        "text": "Pearson correlation measures linear association between aligned price levels, changes, or log returns. It changes with the sample window and is not causation.",
        "url": "https://www.investor.gov/introduction-investing/investing-basics/asset-allocation",
    },
]


class Research:
    """Provide bounded, source-labeled research reads without hidden model downloads."""

    def __init__(self, settings: Settings, data_settings: DataSettings | None = None):
        self.settings = settings
        self.bitcoin = BitcoinExplorer()
        self.crypto = CryptoLibrary(settings.data_dir)
        self.news_service = NewsService(settings, data_settings=data_settings)
        self.fear_greed = FearGreed(self.news_service.repository)

    def knowledge(self, query: str = "") -> list[dict]:
        """Rank a small curated glossary by matching query terms; no embedding claim."""
        words = set(re.findall(r"[a-z]{3,}", query.lower()))
        scored = [
            (
                sum(word in f"{entry['term']} {entry['text']} {entry['category']}".lower() for word in words),
                entry,
            )
            for entry in KNOWLEDGE
        ]
        return [
            entry
            for score, entry in sorted(scored, key=lambda pair: pair[0], reverse=True)
            if not words or score > 0
        ]

    def news(self, summary: str = "excerpt", **filters) -> dict:
        """Read cached publisher excerpts or isolated samples with filtered sentiment evidence."""
        return self.news_service.query(summary, **filters)

    def blocks(self, count: int = 10) -> dict:
        """Read Bitcoin's recent blocks from mempool.space or return sample blocks."""
        if self.settings.mode == "demo":
            return {
                "source": "demo",
                "items": [
                    {
                        "height": 870_420 - i,
                        "id": f"sample-{i}",
                        "timestamp": int(datetime.now(UTC).timestamp()) - i * 607,
                        "tx_count": 2800 + i * 173,
                        "size": 1_500_000 + i * 1200,
                    }
                    for i in range(count)
                ],
            }
        blocks = []
        with httpx.Client(timeout=12) as client:
            while len(blocks) < count:
                suffix = f"/{blocks[-1]['height'] - 1}" if blocks else ""
                response = client.get("https://mempool.space/api/v1/blocks" + suffix)
                response.raise_for_status()
                batch = response.json()
                if not batch:
                    break
                normalized = [
                    {key: block[key] for key in ("height", "id", "timestamp", "tx_count", "size")}
                    for block in batch
                ]
                if blocks and normalized[-1]["height"] >= blocks[-1]["height"]:
                    break
                blocks.extend(normalized)
        return {"source": "mempool.space", "items": blocks[:count]}

    def stock(self, symbol: str) -> dict:
        """Return a quote and daily history; install ``sibyl[stocks]`` for live equities."""
        symbol = symbol.upper().strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", symbol):
            raise ValueError("Use an equity ticker such as AAPL.")
        if self.settings.mode == "demo":
            import numpy as np
            import pandas as pd

            fixtures = {
                "AAPL": ("Apple Inc.", 224.50),
                "MSFT": ("Microsoft Corporation", 428.76),
                "NVDA": ("NVIDIA Corporation", 132.48),
                "COIN": ("Coinbase Global", 215.32),
            }
            if symbol not in fixtures:
                raise ValueError("Demo equities: AAPL, MSFT, NVDA, COIN.")
            name, price = fixtures[symbol]
            rng = np.random.default_rng(sum(map(ord, symbol)))
            values = np.exp(np.cumsum(rng.normal(0.001, 0.015, 90)))
            values *= price / values[-1]
            dates = pd.bdate_range(end=datetime.now(UTC).date(), periods=90)
            return self._stock_details(
                {
                    "symbol": symbol,
                    "name": name,
                    "price": price,
                    "currency": "USD",
                    "source": "demo",
                    "history": [
                        {"timestamp": day.isoformat(), "value": float(value)}
                        for day, value in zip(dates, values, strict=True)
                    ],
                    "profile": {
                        "sector": "Financial services" if symbol == "COIN" else "Technology",
                        "country": "United States",
                        "description": "Illustrative company profile in the demo workspace.",
                    },
                }
            )
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ValueError("Install the stocks extra: uv sync --extra stocks") from exc
        ticker = yf.Ticker(symbol)
        history = ticker.history(period="3mo", auto_adjust=True)
        if history.empty:
            raise ValueError("No equity data was found for this ticker.")
        profile, profile_warning = {}, None
        try:
            info = ticker.get_info()
            keys = {
                "sector": "sector",
                "industry": "industry",
                "country": "country",
                "website": "website",
                "description": "longBusinessSummary",
                "market_cap": "marketCap",
                "trailing_pe": "trailingPE",
                "dividend_yield": "dividendYield",
            }
            import math

            profile = {
                target: (value[:1200] if isinstance(value, str) else value)
                for target, source in keys.items()
                if (value := info.get(source)) is not None
                and (not isinstance(value, float) or math.isfinite(value))
            }
        except Exception:
            profile_warning = "Company fundamentals were unavailable; the price history is still shown."
        return self._stock_details(
            {
                "symbol": symbol,
                "name": info.get("shortName", symbol) if profile else symbol,
                "price": float(history.iloc[-1]["Close"]),
                "currency": ticker.fast_info.get("currency", "USD"),
                "source": "Yahoo Finance via yfinance",
                "profile": profile,
                "profile_warning": profile_warning,
                "history": [
                    {"timestamp": day.isoformat(), "value": float(row["Close"])}
                    for day, row in history.iterrows()
                ],
            }
        )

    @staticmethod
    def _stock_details(result: dict) -> dict:
        """Derive observed price statistics using 252 equity sessions per year."""
        import numpy as np

        values = [point["value"] for point in result["history"]]
        metrics = performance_metrics(values, [], 252)
        returns = np.diff(np.log(values))
        result["statistics"] = {
            "period_return": (values[-1] / values[0] - 1) * 100,
            "high": max(values),
            "low": min(values),
            "volatility": float(np.std(returns, ddof=1) * np.sqrt(252) * 100) if len(returns) > 1 else 0,
            "max_drawdown": metrics["max_drawdown"],
            "observations": len(values),
        }
        return result
