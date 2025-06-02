from typing import Optional, Dict, Any
import requests
from streamlit import cache_data
from frontend.config.config import BACKEND_SERVER_ADDRESS
import re



@cache_data(show_spinner="Fetching asset minimum trade value...")
def fetch_symbol_info(exchange: str, quote_asset: str, base_asset: str) -> Dict[str, Any] | None:


    if exchange == "Coinbase" or exchange == "Coinbase Sandbox":
        trading_pair = f"{base_asset}-{quote_asset}"
    else:
        trading_pair = base_asset + quote_asset

    url = f'{BACKEND_SERVER_ADDRESS}/broker/trade/spot/check/symbol_info?exchange={exchange.lower().replace(" ","_")}&symbol={trading_pair}'
    response = requests.get(url)
    if response.status_code == 200:
        try:
            return response.json()
        except KeyError as e:
            print(e)
            return None
    else:
        return None


@cache_data(show_spinner="Fetching asset current Price...")
def fetch_asset_market_price(exchange: str, trading_pair: str):

    url = f'{BACKEND_SERVER_ADDRESS}/broker/trade/spot/asset/market_price?exchange={exchange.lower().replace(" ","_")}&pair_symbol={trading_pair}'
    response = requests.get(url)
    if response.status_code == 200:
        try:
            return response.json()['price']
        except KeyError as e:
            print(e)
            return None
    else:
        return None


def post_spot_trade(test_order: bool, exchange: str, order_type: str, quote_asset: str, base_asset: str, side: str, quantity: float, price: Optional[float] = None, stop_price: Optional[float] = None, take_profit_price: Optional[float] = None, time_in_force: Optional[str] = None) -> Dict[str, str] | None:

    url = f"{BACKEND_SERVER_ADDRESS}/broker/trade/spot/test" if test_order else f"{BACKEND_SERVER_ADDRESS}/broker/trade/spot/execute"

    data = {
        "exchange": exchange.lower().replace(" ", "_"),
        "order_type": order_type.lower(),
        "quote_asset": quote_asset,
        "base_asset": base_asset,
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


def fetch_orderbook(exchange: str, quote_asset: str, base_asset: str, limit: int) -> Dict[str, Any] | None:

    url = f'{BACKEND_SERVER_ADDRESS}/broker/trade/spot/orderbook?exchange={exchange.lower().replace(" ","_")}&quote_asset={quote_asset}&base_asset={base_asset}&limit={limit}'
    response = requests.get(url)
    if response.status_code == 200:
        try:
            return response.json()['orderbook']
        except KeyError as e:
            print(e)
            return None
    else:
        return None
