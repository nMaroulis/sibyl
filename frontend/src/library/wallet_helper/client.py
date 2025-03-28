import requests
from streamlit import cache_resource
from frontend.config.config import BACKEND_SERVER_ADDRESS
from typing import List, Dict


@cache_resource(ttl=7200, show_spinner=False)
def fetch_account_spot(exchange: str, quote_asset_pair: str = None) -> Dict | None:

    url = f"{BACKEND_SERVER_ADDRESS}/accountant/account/spot/balance?exchange={exchange.lower().replace(' ', '_')}"
    if quote_asset_pair:
        url += f"&quote_asset_pair={quote_asset_pair}"
    response = requests.get(url)

    if response.status_code == 200:
        return response.json()
    else:
        return None


@cache_resource(ttl=7200, show_spinner=False)
def fetch_account_information(exchange: str) -> Dict | None:

    url = f"{BACKEND_SERVER_ADDRESS}/accountant/account/information?exchange={exchange.lower().replace(' ', '_')}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        return None