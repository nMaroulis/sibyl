import requests
import json
from frontend.config.config import BACKEND_SERVER_ADDRESS


def fetch_apis_status(api_name: str = 'all') -> dict:
    url = f"{BACKEND_SERVER_ADDRESS}/technician/status/api/{api_name}"
    response = requests.get(url)
    print(response.json())
    if response.status_code == 200:
        return response.json()
    else:
        return {}

def post_new_api_keys(api_name:str, api_key: str, secret_key: str = None, api_metadata: str = None) -> bool:

    url = f"{BACKEND_SERVER_ADDRESS}/technician/credentials/apis/add"

    data = {
        "api_name": api_name,
        "api_key": api_key,
        "secret_key": secret_key,
        "api_metadata": api_metadata,
    }
    data = {k: v for k, v in data.items() if v is not None}

    response = requests.post(url=url, json=data)
    if response.status_code == 200:
        return True
    else:
        return False

