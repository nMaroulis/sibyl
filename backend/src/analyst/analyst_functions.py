import requests
import json
from backend.db.api_keys_db_client import APIEncryptedDatabase

COIN_SYMBOL_NAME_MAP_PATH = 'backend/db/coin_symbol_name_map.json'


def get_coin_symbol_name_map():
    with open(COIN_SYMBOL_NAME_MAP_PATH, "r") as f:
        coins_data = json.load(f)
    return coins_data


def update_coin_symbol_name_map(api: str = "coincap"):
    coin_dict = {}

    if api == "coincap":
        url = "https://api.coincap.io/v2/assets"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            assets = data.get('data', [])
            for asset in assets:
                coin_dict[asset['symbol']] = asset['name']
    elif api == "coinmarketcap":
        api_key =  APIEncryptedDatabase.get_api_key_by_name("coinmarketcap")
        if api_key is None:  # If coinmarketcap key is not set, call function with coincap (free)
            update_coin_symbol_name_map("coincap")
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/map"
        headers = {
            'X-CMC_PRO_API_KEY': api_key,
            'Accept': 'application/json'
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            coin_dict = {coin['symbol']: coin['name'] for coin in data['data']}
        else:
            print("Failed to fetch data from CoinMarketCap API")
    else:  # CoinGecko
        url = "https://api.coingecko.com/api/v3/coins/list"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            coin_dict = {coin['symbol'].upper(): coin['name'] for coin in data}
        else:
            print("Failed to fetch data from CoinGecko API")

    if coin_dict == {}:
        return False
    else:
        with open(COIN_SYMBOL_NAME_MAP_PATH, "w") as f:
            json.dump(coin_dict, f, indent=4)
        return True
