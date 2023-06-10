import requests
from streamlit import sidebar, error, warning, success

"""A General purpose Client"""


def check_exchange_api_connection(exchange='binance'):
    url = "http://127.0.0.1:8000/technician/status/api/?exchange={exchange}/"
    response = requests.get(url)
    if response.status_code == 200:
        if response.json().get('backend_server_status') == 'success':
            sidebar.success('📶 Exchange API Active')
            return 1
        if response.json().get('backend_server_status') == 'no_api_key':
            warning('Connection to the Exchange API failed. **Valid Exchange API Key Missing**, Please visit the Settings Tab to set an Exchange API Key.')
            return 0
        # if response.json().get('backend_server_status') == 'false_api_key':
        #     error(
        #         'Connection to the Exchange API failed. The **current** Exchange API Key seems to be ***Invalid***, Please visit the Settings Tab to set a **Valid Exchange API Key**.')
        #     return 0
        if response.json().get('backend_server_status') == 'api_conn_error':
            error(
                'Error connecting to Exchange API. The **current** Exchange API URL seems to be ***Unresponsive***, Please visit the Settings Tab to set another **Exchange API URL**.')
            return 0
    else:
        error(
            "Connection to Backend Server failed. Please visit the Settings Tab to set a **IP** and **PORT**, or check start application manually via the **main.py** script")
        return 0


def check_backend_connection():
    url = f"http://127.0.0.1:8000/"
    response = requests.get(url)
    if response.status_code == 200:
        sidebar.success('📶 Server Connection Active')
        return 1  # True
    else:
        sidebar.error('📶 Server Connection Failed')
        return 0


def check_nlp_connection(model="hugging_face"):
    url = f"http://127.0.0.1:8000/nlp/{model}"
    response = requests.get(url)
    if response.status_code == 200:
        sidebar.success('📶 NLP API Connection Active')
        return 1  # True
    else:
        sidebar.error('📶 NLP API Connection Failed')
        return 0