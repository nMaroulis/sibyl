from typing import Optional
import requests
from streamlit import cache_data
from frontend.config.config import BACKEND_SERVER_ADDRESS
import re


@cache_data(show_spinner="Checking Asset Options Validity...")
def fetch_minimum_trade_value(exchange: str, trading_pair: str):

    url = f'{BACKEND_SERVER_ADDRESS}/broker/trade/check/minimum_value?exchange={exchange.lower().replace(" ","_")}&symbol={trading_pair}'
    response = requests.get(url)
    if response.status_code == 200:
        try:
            return response.json()['min_trade_value']
        except KeyError as e:
            print(e)
            return None
    else:
        return None


def post_spot_trade_test(exchange: str, order_type: str, trading_pair: str, side: str, quantity: float, price: Optional[float] = None, stop_price: Optional[float] = None, take_profit_price: Optional[float] = None, time_in_force: Optional[str] = None):
    url = f"{BACKEND_SERVER_ADDRESS}/broker/trade/spot/test"

    data = {
        "exchange": exchange.lower().replace(" ", "_"),
        "order_type": order_type.lower(),
        "trading_pair": trading_pair,
        "side": side.upper(),
        "quantity": quantity,
        "price": price,
        "stop_price": stop_price,
        "take_profit_price": take_profit_price,
        "time_in_force": time_in_force,
    }
    data = {k: v for k, v in data.items() if v is not None}

    response = requests.post(url=url, json=data)

    if response.status_code == 200 and response:
        return response.json()
    else:
        return None