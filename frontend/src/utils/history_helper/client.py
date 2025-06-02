import requests
from streamlit import cache_resource
from frontend.config.config import BACKEND_SERVER_ADDRESS


def update_trading_history():
    url = f'{BACKEND_SERVER_ADDRESS}/broker/trade_history/order/status/update'
    res = requests.get(url)
    return res


@cache_resource(ttl=120)
def fetch_trading_history():
    url = f'{BACKEND_SERVER_ADDRESS}/broker/trade/spot/history'
    res = requests.get(url)
    if res.status_code == 200:
        orders = res.json()
        return orders
    else:
        return None
