from fastapi import APIRouter
from fastapi.exceptions import ResponseValidationError
from typing import Optional, List
import requests
from backend.settings import BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
from backend.config.api_key_handler import get_api_key, get_nlp_api_key
from backend.src.analyst.analyst_functions import get_coin_symbol_name_map, update_coin_symbol_name_map
import json
from backend.src.exchange_client.binance_client import BinanceClient
from backend.src.exchange_client.binance_testnet_client import BinanceTestnetClient
from backend.src.exchange_client.exchange_client_factory import ExchangeClientFactory


# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/analyst",
    tags=["Analyst"],
    responses={404: {"description": "Not found"}},
)


@router.get("/coin/price_history/{exchange_api}")
def get_price_history(exchange_api: str = "binance_testnet", symbol: str = "BTCUSDT", interval: str = '1d', plot_type='line', limit: int = 100) -> List[dict]:
    client = ExchangeClientFactory.get_client(exchange_api)
    res = client.fetch_price_history(symbol, interval, plot_type, limit)
    return res


@router.get("/exchange_info/available_coins/{exchange_api}")
def get_available_coins(exchange_api: str = 'binance_testnet'):
    client = ExchangeClientFactory.get_client(exchange_api)
    res = client.fetch_available_coins()
    return res


@router.put("/available_coins/symbol_name_map/update")
def update_coin_symbol_name_map():
    res = update_coin_symbol_name_map("coinmarketcap")
    if res:
        return {"Success": "Symbol - Name map updated Successfully"}
    else:
        return {"Error": "Symbol - Name map update Failed. Keeping the current symbol-name map."}
