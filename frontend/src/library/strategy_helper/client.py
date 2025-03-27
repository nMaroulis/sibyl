from typing import Dict, Any, List
import requests
from frontend.config.config import BACKEND_SERVER_ADDRESS
from streamlit import cache_data


def post_strategy(exchange: str, quote_asset: str, quote_amount: float, base_asset: str, time_interval: str, strategy: str, num_trades: int, dataset_size: int, params: Dict[str, Any], backtesting: bool = False) -> Dict[str, Any] | None:

    if strategy.startswith("[Sibyl] "):
        strategy = strategy.replace("[Sibyl] ", "")
    strategy = strategy.lower().replace(" ", "_")

    payload = {
        "exchange": exchange.lower().replace(" ", "_"),
        "quote_asset": quote_asset,
        "quote_amount": quote_amount,
        "base_asset": base_asset,
        "time_interval": time_interval,
        "strategy": strategy,
        "num_trades": num_trades,
        "dataset_size": dataset_size,
        "params": params
    }
    url = f"{BACKEND_SERVER_ADDRESS}/broker/strategy/backtest/start" if backtesting else f"{BACKEND_SERVER_ADDRESS}/broker/strategy/start"

    response = requests.post(url=url, json=payload)

    if response.status_code == 200:
        return response.json()
    else:
        return None


def stop_strategy(strategy_id: str):

    url = f"{BACKEND_SERVER_ADDRESS}/broker/strategy/status/stop?strategy_id={strategy_id}"

    response = requests.get(url=url)

    if response.status_code == 200:
        return response.json()
    else:
        return None


def get_strategy_metadata(strategy_id: str):

    url = f"{BACKEND_SERVER_ADDRESS}/broker/strategy/metadata?strategy_id={strategy_id}"

    response = requests.get(url=url)

    if response.status_code == 200:
        return response.json()
    else:
        return None


def get_strategy_logs(strategy_id: str, from_timestamp: int = None):

    url = f"{BACKEND_SERVER_ADDRESS}/broker/strategy/logs?strategy_id={strategy_id}"
    if from_timestamp:
        url += f"&from_timestamp={from_timestamp}"

    response = requests.get(url=url)

    if response.status_code == 200:
        return response.json()
    else:
        return None


def get_strategy_evaluation(strategy_id: str) -> Dict[str, Any] | None:

    url = f"{BACKEND_SERVER_ADDRESS}/broker/strategy/evaluation?strategy_id={strategy_id}"

    response = requests.get(url=url)
    if response.status_code == 200:
        return response.json()
    else:
        return None


@cache_data(ttl=100000)
def get_available_strategies() -> List[str]:

    url = f"{BACKEND_SERVER_ADDRESS}/broker/strategies"

    response = requests.get(url=url)
    if response.status_code == 200:
        res = response.json()
        return res["strategies"]
    else:
        return []
