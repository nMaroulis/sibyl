from typing import List
import requests
from frontend.src.library.crypto_dictionary_assistant import get_crypto_name_regex
from streamlit import cache_data
from frontend.config.config import BACKEND_SERVER_ADDRESS
from pandas import DataFrame, to_datetime


def fetch_price_history(exchange: str, pair_symbol: str, time_int: str, time_limit: int, full_name: bool = True) -> DataFrame | None:
    # if full_name:
    #     symbol = get_crypto_name_regex(pair_symbol)  # get_crypto_coin_dict().get(symbol)
    url = f"{BACKEND_SERVER_ADDRESS}/analyst/asset/price_history?exchange={exchange.lower().replace(" ", "_")}&symbol={pair_symbol}&interval={time_int}&limit={str(time_limit)}"
    response = requests.get(url)
    if response.status_code == 200:

        data = response.json()
        df = DataFrame()
        df['DateTime'] = [entry.get('Open Time') for entry in data]
        df['DateTime'] = to_datetime(df['DateTime'], unit='ms')
        df['Open Price'] = [entry.get('Open Price') for entry in data]
        df['High'] = [entry.get('High') for entry in data]
        df['Low'] = [entry.get('Low') for entry in data]
        df['Close Price'] = [entry.get('Close Price') for entry in data]
        df['Close Time'] = [entry.get('Close Time') for entry in data]
        df['Volume'] = [entry.get('Volume') for entry in data]
        df['Number of trades'] = [entry.get('Number of trades') for entry in data]
        return df
    else:
        return None


@cache_data(ttl=3600)
def fetch_available_assets(exchange: str, quote_asset: str):

    url = f"{BACKEND_SERVER_ADDRESS}/analyst/exchange_info/available_assets?exchange={exchange.lower().replace(" ", "_")}&quote_asset={quote_asset}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        return {}
