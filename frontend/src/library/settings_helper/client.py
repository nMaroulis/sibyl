import requests
import json
from frontend.config.config import BACKEND_SERVER_ADDRESS


def fetch_apis_status(api_name: str = 'all'):
    url = f"{BACKEND_SERVER_ADDRESS}/technician/status/api/{api_name}"
    response = requests.get(url)
    print(response.json())
    if response.status_code == 200:
        return response.json()
    else:
        return {}

def post_exchange_api_keys(exchange_name:str, api_key: str, secret_key: str) -> bool:

    url = f"{BACKEND_SERVER_ADDRESS}/technician/credentials/apis/exchange"

    data = {
        "exchange_name": exchange_name,
        "api_key": api_key,
        "secret_key": secret_key,
    }

    response = requests.post(url=url, json=data)
    if response.status_code == 200:
        return True
    else:
        return False

