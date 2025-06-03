from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict
from backend.src.analyst.utils import update_coin_symbol_name_map
from backend.src.exchange_client.exchange_client_factory import ExchangeClientFactory
from backend.src.analyst.analyst import Analyst
from backend.src.analyst.schemas import AnalyticsResponse, Kline, AssetPairsResponse

# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/analyst",
    tags=["Analyst"],
    responses={404: {"description": "Not found"}},
)


@router.get("/symbol/klines/analysis", response_model=AnalyticsResponse)
def get_symbol_analysis(exchange: str = Query(), symbol: str = Query(), interval: str = Query(), limit: int = Query()) -> AnalyticsResponse:
    client = ExchangeClientFactory.get_client(exchange)
    klines = client.get_klines(symbol, interval, limit)
    analyst = Analyst(klines)
    analytics = analyst.get_analytics()

    if analytics:
        return analytics
    else:
        raise HTTPException(status_code=500, detail="Failed to calculate analyst's klines")


@router.get("/asset/klines", response_model=List[Kline])
def get_price_history(exchange: str = Query(), symbol: str = Query(), interval: str = Query(default="1d"), limit: int = Query(default=200)) -> List[Kline]:
    client = ExchangeClientFactory.get_client(exchange)
    res = client.get_klines(symbol, interval, limit)
    if res:
        return res
    else:
        raise HTTPException(status_code=500, detail="Failed to get price history")


@router.get("/exchange_info/available_assets", response_model=AssetPairsResponse)
def get_available_assets(exchange: str = Query(), quote_asset: str = Query(default="all")) -> AssetPairsResponse:
    client = ExchangeClientFactory.get_client(exchange)
    res = client.get_available_assets(quote_asset)
    if res:
        return res
    else:
        raise HTTPException(status_code=500, detail="Failed to get available coins")


@router.put("/available_coins/symbol_name_map/update", response_model=Dict[str, str])
def update_coin_symbol_name_map() -> Dict[str, str]:
    res = update_coin_symbol_name_map("coinmarketcap")
    if res:
        return {"Success": "Symbol - Name map updated Successfully"}
    else:
        return {"Error": "Symbol - Name map update Failed. Keeping the current symbol-name map."}
