from fastapi import APIRouter
from fastapi.exceptions import ResponseValidationError
from typing import Optional, List
import requests
from backend.settings import SERVER_IP, SERVER_PORT, BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
from backend.config.api_key_handler import get_api_key, get_nlp_api_key
import json


# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/analyst",
    tags=["Analyst"],
    responses={404: {"description": "Not found"}},
)


@router.get("/coin/price_history/{symbol}")
def get_price_history(symbol: str, interval: str = '1d', plot_type='line', limit: int = 100) -> List[dict]:

    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    url = f"{BINANCE_API_URL}/api/v3/klines?symbol={symbol.upper()}&interval={interval}&limit={limit}"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        try:
            data = response.json()
        except json.JSONDecodeError as error:
            return []  # {"error": "Unable to parse response JSON."}

        if plot_type == 'line':  # requested line plot
            price_history = [{"Open Time": entry[0], "Open Price": entry[1]} for entry in data]
        else:  # candle plot
            price_history = [{"Open Time": entry[0],
                              "Open Price": entry[1],
                              "Highs": entry[2],
                              "Lows": entry[3],
                              "Closing Price": entry[4],
                              } for entry in data]

        return price_history
    else:
        return []  # {"error": "Failed to fetch price history"}


def get_coin_full_name(coin_symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_symbol}"
    response = requests.get(url)
    try:
        data = response.json()
        if 'name' in data:
            return data['name']
        else:
            return None
    except Exception as e:
        return None


@router.get("/exchange_info/available_coins")
def get_price_history():

    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    url = f"{BINANCE_API_URL}/api/v1/exchangeInfo"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        try:
            data = response.json()
            if 'symbols' in data:
                # Function to return all Coins
                # available_coins = set()
                # for symbol in data['symbols']:
                #     base_asset = symbol['baseAsset']
                #     quote_asset = symbol['quoteAsset']
                #     if base_asset not in available_coins:
                #         available_coins.add(base_asset)
                #     if quote_asset not in available_coins:
                #         available_coins.add(quote_asset)
                # return list(available_coins)
                available_coins = []  # = [symbol['symbol'] for symbol in data['symbols']]
                for symbol in data['symbols']:
                    if 'USDT' in symbol['symbol']:
                        s = symbol['symbol'].replace('USDT', '')
                        if len(s) > 1:
                            available_coins.append(s)
                return available_coins
            else:
                print("Error: Unable to fetch data from Binance API")
                return []
        except json.JSONDecodeError:
            return {"error": "Unable to parse response JSON."}
    else:
        return {"error": "Failed to fetch available coins"}
