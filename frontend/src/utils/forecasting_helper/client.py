import requests
from frontend.config.config import BACKEND_SERVER_ADDRESS


def fetch_chronos_forecast(coin: str, interval: str, forecast_samples: int):
    url = f'{BACKEND_SERVER_ADDRESS}/chronos/forecast/btc?interval=1d'
    res = requests.get(url)
    try:
        data = res.json()["data"]
    except KeyError:
        data = None
    return data
