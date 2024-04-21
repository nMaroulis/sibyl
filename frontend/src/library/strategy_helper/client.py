import requests
from streamlit import cache_data
from frontend.config.config import BACKEND_SERVER_ADDRESS

@cache_data(show_spinner="Checking Asset Options Validity...")
def fetch_trade_info_minimum_order(pair_symbol='BTCUSDT'):

    url = f'{BACKEND_SERVER_ADDRESS}/broker/trade/info/minimum_order?symbol={pair_symbol}'
    response = requests.get(url)
    return response.json()['min_notional']


def send_strategy(from_coin='USDT', to_coin='BTC', from_amount=1.0, strategy='greedy', order_type='swap'):

    url = f"{BACKEND_SERVER_ADDRESS}/broker/trade/order/buy/new?from_coin={from_coin}&to_coin={to_coin}&from_amount={from_amount}&strategy={strategy}&order_type={order_type}"
    response = requests.get(url)
    return response.json()


@cache_data
def check_swap_status(exchange='binance'):
    url = f"{BACKEND_SERVER_ADDRESS}/broker/trade/convert/info"
    response = requests.get(url)
    return response.json()
