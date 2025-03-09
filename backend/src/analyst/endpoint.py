from fastapi import APIRouter, HTTPException
from typing import Optional, List
from backend.src.analyst.analyst_functions import update_coin_symbol_name_map
from backend.src.exchange_client_v2.exchange_client_factory import ExchangeClientFactory


# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/analyst",
    tags=["Analyst"],
    responses={404: {"description": "Not found"}},
)


@router.get("/coin/price_history")
def get_price_history(exchange: str, symbol: str, interval: str = '1d', plot_type='line', limit: int = 100) -> List[dict]:
    client = ExchangeClientFactory.get_client(exchange)
    res = client.get_price_history(symbol, interval, plot_type, limit)
    if res:
        return res
    else:
        raise HTTPException(status_code=500, detail="Failed to get price history")


@router.get("/exchange_info/available_coins")
def get_available_coins(exchange: str = 'binance_testnet', quote_asset: str = "all"):
    client = ExchangeClientFactory.get_client(exchange)
    res = client.get_available_coins(quote_asset)
    if res:
        return res
    else:
        raise HTTPException(status_code=500, detail="Failed to get available coins")

@router.put("/available_coins/symbol_name_map/update")
def update_coin_symbol_name_map():
    res = update_coin_symbol_name_map("coinmarketcap")
    if res:
        return {"Success": "Symbol - Name map updated Successfully"}
    else:
        return {"Error": "Symbol - Name map update Failed. Keeping the current symbol-name map."}
