import requests


def fetch_trade_info_minimum_order(pair_symbol='BTCUSDT'):
    url = 'http://127.0.0.1:8000/broker/trade/info/minimum_order?symbol=' + pair_symbol
    response = requests.get(url)
    return response.json()['min_notional']


def send_strategy(from_coin='USDT', to_coin='BTC', from_amount=1.0, strategy='greedy'):

    url = f"http://127.0.0.1:8000/broker/trade/order/buy/new?from_coin={from_coin}&to_coin={to_coin}&from_amount={from_amount}&strategy={strategy}"
    response = requests.get(url)
    return response.json()