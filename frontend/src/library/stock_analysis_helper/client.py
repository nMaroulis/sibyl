import requests
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


def fetch_stock_advice(stock_symbol: str, llm_api_name: str):
    url = f"{BACKEND_SERVER_ADDRESS}/stock_analyst/advisor/llm?stock_symbol={stock_symbol}&llm_api={llm_api_name}"
    response = requests.get(url)
    if response.status_code == 200:
        res = response.json()
        return res['data']
    else:
        return None