from fastapi import APIRouter
from fastapi.exceptions import ResponseValidationError
from typing import Optional, List
import requests
from backend.settings import BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
from backend.config.api_key_handler import get_api_key, get_nlp_api_key
from backend.src.analyst.analyst_functions import get_coin_symbol_name_map, update_coin_symbol_name_map
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
                #     base_asset = symbol['baseAsset']
                #     quote_asset = symbol['quoteAsset']
                #     if base_asset not in available_coins:
                #         available_coins.add(base_asset)
                #     if quote_asset not in available_coins:
                #         available_coins.add(quote_asset)
                coin_name_dict = get_coin_symbol_name_map()
                available_coins = []  # = [symbol['symbol'] for symbol in data['symbols']]
                for symbol in data['symbols']:
                    if 'USDT' in symbol['symbol']:
                        s = symbol['symbol'].replace('USDT', '')
                        if len(s) > 1:
                            if s in coin_name_dict.keys():  # if symbol exists in dict
                                if coin_name_dict[s] != s:  # if name and symbol are the same, keep one
                                    available_coins.append(f"{coin_name_dict[s]} [{s}]")
                                else:
                                    available_coins.append(s)
                            else:
                                available_coins.append(s)
                return available_coins
            else:
                print("Error: Unable to fetch data from Binance API")
                return []
        except json.JSONDecodeError:
            return {"Error": "Unable to parse response JSON."}
    else:
        return {"Error": "Failed to fetch available coins"}


@router.put("/available_coins/symbol_name_map/update")
def update_coin_symbol_name_map():
    res = update_coin_symbol_name_map("coinmarketcap")
    if res:
        return {"Success": "Symbol - Name map updated Successfully"}
    else:
        return {"Error": "Symbol - Name map update Failed. Keeping the current symbol-name map."}
