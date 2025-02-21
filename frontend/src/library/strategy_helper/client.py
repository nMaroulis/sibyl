import requests
from streamlit import cache_data
from frontend.config.config import BACKEND_SERVER_ADDRESS
import re

@cache_data(show_spinner="Checking Asset Options Validity...")
def fetch_trade_info_minimum_order(exchange: str, pair_symbol: str):

    url = f'{BACKEND_SERVER_ADDRESS}/broker/trade/info/minimum_order?symbol={pair_symbol}'
    response = requests.get(url)
    return response.json()['min_notional']


def extract_coin_symbol(text):
    match = re.search(r'\[([^\]]+)\]$', text)
    return match.group(1) if match else text


def post_strategy(exchange_api: str, from_coin: str, to_coin: str, from_amount: str, strategy: str, strategy_params: dict, order_type: str):

    data = {
        "exchange_api": exchange_api,
        "from_coin": extract_coin_symbol(from_coin),
        "to_coin": extract_coin_symbol(to_coin),
        "from_amount": from_amount,
        "strategy": strategy,
        "strategy_params": strategy_params,
        "order_type": order_type
    }

    url = f"{BACKEND_SERVER_ADDRESS}/broker/trade/order/buy/new"
    response = requests.post(url=url, json=data)
    if response.status_code == 200:
        return response.json()
    else:
        return response.json()


@cache_data
def check_swap_status(exchange: str):
    url = f"{BACKEND_SERVER_ADDRESS}/broker/trade/convert/info?exchange={exchange}"
    response = requests.get(url)
    return response.json()
