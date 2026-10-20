"""Shared watchlist fixtures and supported application candle intervals."""

ASSETS = {
    "BTC": ("Bitcoin", 67_432.80, "#f6a94d"),
    "ETH": ("Ethereum", 3_521.64, "#99a7ff"),
    "SOL": ("Solana", 172.38, "#ad8cf9"),
    "LINK": ("Chainlink", 17.42, "#7eabfa"),
    "AVAX": ("Avalanche", 36.84, "#ee8e8e"),
    "DOT": ("Polkadot", 7.18, "#e68ab9"),
    "USDT": ("Tether", 1.0, "#71bea5"),
}
STABLES = {"USDT", "USDC", "USD", "DAI"}

TIMEFRAMES = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}

# Seeded once per asset in the persistent paper ledger; never sent from frontend code.
DEMO_BALANCES = {
    "USDT": 24_850.0,
    "BTC": 0.84,
    "ETH": 8.2,
    "SOL": 74.0,
    "LINK": 210.0,
    "ADA": 1200.0,
    "USDC": 1500.0,
    "EUR": 250.0,
}

# Separate from the familiar default watchlist. These routes exercise broader
# holdings, a stablecoin away from parity, fiat conversion and an inverse quote.
DEMO_ASSETS = ASSETS | {
    "ADA": ("Cardano", 0.42, "#6b92d5"),
    "USDC": ("USDC", 0.997, "#6b9bd5"),
    "DAI": ("Dai", 0.998, "#d7ad61"),
    "USD": ("US Dollar", 1 / 1.002, "#83aa96"),
    "EUR": ("Euro", 1.08 / 1.002, "#8b9bc5"),
}
