"""Equity research controls and optional market-data setup."""

from typing import Literal

from sibyl.agents.guides import Guide

Topic = Literal["overview", "setup", "statistics", "limitations"]
GUIDES = {
    "overview": Guide(
        "Research an equity",
        "/research?tab=stocks",
        (
            "Open Research → Equities, enter a supported ticker and inspect the quote, adjusted daily history and available company profile fields.",
            "Ask Equity Analyst uses that selected ticker; read the currency, source, dates and any Demo labels.",
        ),
    ),
    "setup": Guide(
        "Enable live equity observations",
        "/research?tab=stocks",
        (
            "Install the optional stocks dependency on the backend with uv sync --extra stocks and run in live data mode for yfinance observations.",
            "Demo provides illustrative AAPL, MSFT, NVDA and COIN observations. Other supported symbols require live data.",
        ),
    ),
    "statistics": Guide(
        "Understand equity statistics",
        "/research?tab=stocks",
        (
            "Inspect observed period return, sample high/low, annualized log-return volatility using 252 sessions and maximum drawdown.",
            "Read company profile fields only when returned; company metadata can fail independently of price history.",
        ),
        (
            "Observed ticker return is not the user's investment return. Historical volatility and drawdown do not predict future outcomes.",
        ),
    ),
    "limitations": Guide(
        "Understand equity research limits",
        "/research?tab=stocks",
        (
            "Use supplied company profile fields and source history; missing earnings or fundamentals must remain unavailable.",
            "Disclosure archives, public-official portfolios and advanced company analytics are Coming soon.",
        ),
    ),
}
