import requests
from streamlit import sidebar, error, warning, success, spinner, rerun, toast
import time
from frontend.config.config import BACKEND_SERVER_ADDRESS
"""A General purpose Client"""


def check_exchange_api_connection(exchange: str = 'binance'):  # TODO reexamine here, make general purpose function
    url = f"{BACKEND_SERVER_ADDRESS}/technician/status/api/{exchange}"
    response = requests.get(url)
    if response.status_code == 200:
        if response.json().get('backend_server_status') == 'success':
            # sidebar.success('📶 Exchange API Active')
            toast('✅ Exchange API Connection Successful')
            return 1
        if response.json().get('backend_server_status') == 'no_api_key':
            # warning('Connection to the Exchange API failed. **Valid Exchange API Key Missing**, Please visit the Settings Tab to set an Exchange API Key.')
            toast('⛔ Exchange API Connection Failed')
            return 0
        # if response.json().get('backend_server_status') == 'false_api_key':
        #     error(
        #         'Connection to the Exchange API failed. The **current** Exchange API Key seems to be ***Invalid***, Please visit the Settings Tab to set a **Valid Exchange API Key**.')
        #     return 0
        if response.json().get('backend_server_status') == 'api_conn_error':
            #error('Error connecting to Exchange API. The **current** Exchange API URL seems to be ***Unresponsive***, Please visit the Settings Tab to set another **Exchange API URL**.')
            toast('⛔ Exchange API Connection Failed')

            return 0
    else:
        error(
            "Connection to Backend Server failed. Please visit the Settings Tab to set a **IP** and **PORT**, or check start application manually via the **main.py** script")
        toast('⛔ Backend Server Connection Failed')

        return 0


def check_backend_connection():
    url = f"{BACKEND_SERVER_ADDRESS}/"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            # sidebar.success('📶 Server Connection Active')
            toast('Backend Server Connection Successful!', icon=":material/task_alt:")
            return 'Active'  # True
        else:
            sidebar.error('📶 Server Connection Failed')
            toast('Backend Server Connection Failed!', icon=":material/warning:")
            return 'Offline'
    except requests.exceptions.ConnectionError:
        with spinner('Failed to establish a new connection to Backend Server, refreshing in 5 seconds'):
            time.sleep(5)
            rerun()


def check_api_status(api_name: str) -> bool: # TODO reexamine here
    url = f"{BACKEND_SERVER_ADDRESS}/technician/status/api/{api_name}"
    response = requests.get(url)
    try:
        if response.status_code == 200 and response.json().get(api_name) == "Active":
            return True
    except Exception as e:
        print(e)
        return False
    return False