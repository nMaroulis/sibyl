from typing import Dict, Any
import requests
from streamlit import cache_data
from frontend.config.config import BACKEND_SERVER_ADDRESS


def post_strategy(exchange: str, quote_asset: str, quote_amount: float, base_asset: str, time_interval: str, strategy: str, num_trades: int, params: Dict[str, Any], backtesting: bool = False) -> Dict[str, Any] | None:

    payload = {
        "exchange": exchange,
        "quote_asset": quote_asset,
        "quote_amount": quote_amount,
        "base_asset": base_asset,
        "time_interval": time_interval,
        "strategy": strategy.lower().replace(" ", "_"),
        "num_trades": num_trades,
        "params": params
    }

    url = f"{BACKEND_SERVER_ADDRESS}/broker/strategy/backtesting/start" if backtesting else f"{BACKEND_SERVER_ADDRESS}/broker/strategy/start"

    response = requests.post(url=url, json=payload)

    if response.status_code == 200:
        return response.json()
    else:
        return None