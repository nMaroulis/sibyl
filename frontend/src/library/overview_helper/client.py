import requests


def fetch_account_spot():
    url = "http://127.0.0.1:8000/accountant/account/spot/overview"
    response = requests.get(url)
    return response.json(), response.status_code
