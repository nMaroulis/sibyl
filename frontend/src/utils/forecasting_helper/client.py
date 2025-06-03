import requests
from frontend.config.config import BACKEND_SERVER_ADDRESS


def fetch_chronos_forecast(coin: str, interval: str, forecast_samples: int):
    url = f'{BACKEND_SERVER_ADDRESS}/chronos/forecast/crypto/price?asset=btc&interval=1d'
    res = requests.get(url)
    try:
        if res.status_code == 200:
            data = res.json()["data"]
        else:
            data = None
    except KeyError:
        data = None
    return data
