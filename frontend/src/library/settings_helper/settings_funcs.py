from streamlit import error, warning, success, write, markdown, info
import requests


def check_api_connection(exchange='binance'):
    url = f"http://127.0.0.1:8000/status/api/?exchange={exchange}/"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()[0]
        if data == 'Connection to Binance API successful':
            success("📶 " + data)
        else:
            error(data)
    else:
        error("📶 Connection to Server failed")
    return 0
