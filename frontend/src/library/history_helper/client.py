import requests
from streamlit import cache_resource
from frontend.config.config import BACKEND_SERVER_ADDRESS


def update_trading_history():
    url = f'{BACKEND_SERVER_ADDRESS}/broker/trade/order/status/update'
    res = requests.get(url)
    return res


@cache_resource(ttl=120)
def fetch_trading_history(strat_status='all'):
    url = f'{BACKEND_SERVER_ADDRESS}/broker/trade/strategy/history?status={strat_status}'
    res = requests.get(url)
    # st.write(res.text)
    if res.status_code == 200:
        trade_strategies = res.json()
        return trade_strategies
    else:
        return None
