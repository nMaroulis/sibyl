import requests
from streamlit import sidebar, spinner, rerun, toast
import time
from frontend.config.config import BACKEND_SERVER_ADDRESS

"""A General purpose Client"""



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


def check_api_status(api_name: str) -> bool:
    api_name = api_name.lower().replace(' ', '_')
    url = f"{BACKEND_SERVER_ADDRESS}/technician/status/api/{api_name}"
    response = requests.get(url)
    try:
        if response.status_code == 200 and response.json().get(api_name) == "Active":
            return True
    except Exception as e:
        print(e)
        return False
    return False
