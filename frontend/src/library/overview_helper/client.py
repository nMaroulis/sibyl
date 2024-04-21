import requests
from streamlit import cache_resource
from frontend.config.config import BACKEND_SERVER_ADDRESS


@cache_resource(ttl=7200, show_spinner=False)
def fetch_account_spot(exchange_api='Binance'):
    exchange_api = exchange_api.replace(' ', '_').lower()
    url = f"{BACKEND_SERVER_ADDRESS}/accountant/account/spot/overview/{exchange_api}"
    response = requests.get(url)
    # print(response.json())
    return response.json(), response.status_code
