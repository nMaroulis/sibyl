import requests
from frontend.src.library.crypto_dictionary_assistant import get_crypto_name_regex
from streamlit import cache_data
from frontend.config.config import BACKEND_SERVER_ADDRESS


def fetch_price_history(exchange: str, symbol: str, time_int: str, time_limit: int, plot_type: str = 'line', full_name=True):
    if full_name:
        symbol = get_crypto_name_regex(symbol)  # get_crypto_coin_dict().get(symbol)
    symbol += 'USDT'  # USDT is the default
    url = f"{BACKEND_SERVER_ADDRESS}/analyst/coin/price_history?exchange={exchange.lower().replace(" ", "_")}&symbol={symbol}&interval={time_int}&limit={str(time_limit)}&plot_type={plot_type}"
    response = requests.get(url)
    return response.json()


@cache_data(ttl=1000)
def fetch_available_coins(exchange: str = "binance", quote_asset: str = "all"):

    url = f"{BACKEND_SERVER_ADDRESS}/analyst/exchange_info/available_assets?exchange={exchange.lower().replace(" ", "_")}&quote_asset={quote_asset}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        return []
