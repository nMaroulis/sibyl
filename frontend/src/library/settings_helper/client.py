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
