import requests
from typing import Optional
from streamlit import cache_data
from frontend.config.config import BACKEND_SERVER_ADDRESS


def fetch_stock_details(stock_symbol: str):
    url = f"{BACKEND_SERVER_ADDRESS}/stock_analyst/yf/stock_details?stock_symbol={stock_symbol}"
    response = requests.get(url)
    if response.status_code == 200:
        res = response.json()
        return res['data']
    else:
        return None

@cache_data(ttl=3600)
def fetch_portfolio_senates():
    url = f"{BACKEND_SERVER_ADDRESS}/stock_analyst/portfolio/senates"
    response = requests.get(url)
    if response.status_code == 200:
        res = response.json()
        return res['data']
    else:
        return None


def fetch_stock_advice(model_source: str, model_type: str, model_name: Optional[str], stock_symbol: str):

    url = f"{BACKEND_SERVER_ADDRESS}/stock_analyst/advisor/llm?model_source={model_source}&model_type={model_type}&stock_symbol={stock_symbol}"
    if model_name:
        url += f"&model_name={model_name}"

    response = requests.get(url)
    if response.status_code == 200:
        res = response.json()
        return res['data']
    else:
        return None