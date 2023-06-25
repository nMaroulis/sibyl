import requests
from streamlit import cache_resource


def update_trading_history():
    url = 'http://127.0.0.1:8000/broker/trade/order/status/update'
    res = requests.get(url)
    return res


@cache_resource(ttl=120)
def fetch_trading_history(strat_status='all'):
    url = 'http://127.0.0.1:8000/broker/trade/strategy/history?status=' + strat_status
    res = requests.get(url)
    # st.write(res.text)
    if res.status_code == 200:
        trade_strategies = res.json()
        return trade_strategies
    else:
        return None
