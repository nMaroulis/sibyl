import requests
from frontend.src.library.crypto_dictionary_assistant import get_crypto_coin_dict


def fetch_price_history(coin='BTC', time_int='1d', time_limit=500, plot_type='line'):

    url = f"http://127.0.0.1:8000/analyst/coin/price_history/" + get_crypto_coin_dict().get(
        coin) + "?interval=" + time_int + "&limit=" + str(time_limit) + "&plot_type=" + plot_type
    response = requests.get(url)
    return response.json()
