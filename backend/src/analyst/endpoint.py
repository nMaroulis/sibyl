from fastapi import APIRouter, HTTPException
from typing import List, Dict, Optional, Any
from backend.src.analyst.analyst_functions import update_coin_symbol_name_map
from backend.src.exchange_client.exchange_client_factory import ExchangeClientFactory
from backend.src.analyst.analyst import Analyst


# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/analyst",
    tags=["Analyst"],
    responses={404: {"description": "Not found"}},
)


@router.get("/symbol/klines/analysis")
def get_symbol_analysis(exchange: str, symbol: str, interval: str, limit: int) -> Optional[Dict[str, Any]]:
    client = ExchangeClientFactory.get_client(exchange)
    klines = client.get_klines(symbol, interval, limit)
    analyst = Analyst(klines)
    analytics = analyst.get_analytics()

    if analytics:
        return analytics
    else:
        raise HTTPException(status_code=500, detail="Failed to calculate analyst's klines")


@router.get("/asset/klines")
def get_price_history(exchange: str, symbol: str, interval: str = '1d', limit: int = 100) -> List[dict]:
    client = ExchangeClientFactory.get_client(exchange)
    res = client.get_klines(symbol, interval, limit)
    if res:
        return res
    else:
        raise HTTPException(status_code=500, detail="Failed to get price history")


@router.get("/exchange_info/available_assets")
def get_available_assets(exchange: str = 'binance', quote_asset: str = "all"):
    client = ExchangeClientFactory.get_client(exchange)
    res = client.get_available_assets(quote_asset)
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
