"""Implemented, transparent strategy definitions for the workspace."""

CATALOG = [
    {
        "id": "ema",
        "name": "EMA Crossover",
        "tag": "Trend following",
        "description": "Follow the direction of configurable fast and slow exponential moving averages.",
        "risk": "Moderate",
    },
    {
        "id": "rsi",
        "name": "RSI Reversion",
        "tag": "Mean reversion",
        "description": "Buy lower RSI readings and exit higher readings, with configurable Wilder RSI thresholds.",
        "risk": "Moderate",
    },
    {
        "id": "bollinger",
        "name": "Bollinger Bands",
        "tag": "Volatility",
        "description": "Enter below the lower band and exit above the upper band.",
        "risk": "Moderate",
    },
    {
        "id": "bollinger-surge",
        "name": "Bollinger Surge",
        "tag": "Multi factor",
        "description": "Combine band extremes, RSI, an EMA trend filter, and a configurable volume surge.",
        "risk": "Elevated",
    },
    {
        "id": "impulse-breakout",
        "name": "Impulse Breakout",
        "tag": "Momentum",
        "description": "Confirm band and RSI reversals with EMA, MACD, ADX above 25, and volume.",
        "risk": "Elevated",
    },
    {
        "id": "quantum-momentum",
        "name": "Quantum Momentum",
        "tag": "Multi factor",
        "description": "Confirm MACD direction with money flow, TSI momentum, and expanding ATR.",
        "risk": "Elevated",
    },
]
