import requests
import json
from frontend.config.config import BACKEND_SERVER_ADDRESS


def fetch_stock_details(stock_symbol: str):
    url = f"{BACKEND_SERVER_ADDRESS}/stock_analyst/yf/stock_details?stock_symbol={stock_symbol}"
    response = requests.get(url)
    if response.status_code == 200:
        res = response.json()
        return res['data']
    else:
        return {}
