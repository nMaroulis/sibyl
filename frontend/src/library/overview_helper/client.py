import requests
from streamlit import cache_resource


@cache_resource(ttl=7200, show_spinner=False)
def fetch_account_spot():
    url = "http://127.0.0.1:8000/accountant/account/spot/overview"
    response = requests.get(url)
    # print(response.json())
    return response.json(), response.status_code
