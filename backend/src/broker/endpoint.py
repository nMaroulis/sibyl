from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from database.trade_history_db_client import TradeHistoryDBClient
from datetime import datetime
from pydantic import BaseModel
from backend.src.exchange_client.exchange_client_factory import ExchangeClientFactory


router = APIRouter(
    prefix="/broker",
    tags=["Broker"],
    responses={404: {"description": "Not found"}},
)

class SpotTradeParams(BaseModel):
    exchange: str
    order_type: str
    quote_asset: str
    base_asset: str
    side: str
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    time_in_force: Optional[str] = None


@router.post("/trade/spot/test")
def post_spot_order_test(spot_trade_params: SpotTradeParams) -> Dict[str, str]:

    client = ExchangeClientFactory.get_client(spot_trade_params.exchange)
    spot_trade_params_dict = spot_trade_params.model_dump(exclude={'exchange'})
    res = client.place_spot_test_order(**spot_trade_params_dict)

    return res


@router.post("/trade/spot/new")
def post_spot_order(spot_trade_params: SpotTradeParams) -> Dict[str, Any]:

    client = ExchangeClientFactory.get_client(spot_trade_params.exchange)
    spot_trade_params_dict = spot_trade_params.model_dump(exclude={'exchange'})
    res = client.place_spot_order(**spot_trade_params_dict)

    if res["status"] == "success":
        db_res = client.add_spot_order_to_trade_history_db(spot_trade_params.quote_asset,spot_trade_params.base_asset, res["message"])
    # TODO handle failed insertion to DB
    return res


@router.get("/trade/check/minimum_value")
def get_min_trade_value(exchange: str , symbol: str):

    client = ExchangeClientFactory.get_client(exchange)

    res = client.get_minimum_trade_value(symbol)

    if res:
        return res
    else:
        raise HTTPException(status_code=500, detail="Fetching minimum trade value failed.")


@router.get("/trade/asset/market_price")
def get_current_asset_price(exchange: str , pair_symbol: str) -> dict[str, float]:

    client = ExchangeClientFactory.get_client(exchange)
    res = client.get_pair_market_price(pair_symbol)
    if res:
        return {"price": res}
    else:
        raise HTTPException(status_code=500, detail="Fetching asset price failed.")



@router.get("/trade/spot/history")
def get_spot_trade_history():
    spot_trades = TradeHistoryDBClient.fetch_trading_history()
    return spot_trades


@router.get("/trade/spot/orderbook")
def get_spot_trade_orderbook(exchange: str, quote_asset: str, base_asset: str, limit: int) -> dict[str, Any]:
    client = ExchangeClientFactory.get_client(exchange)
    res = client.get_orderbook(quote_asset, base_asset, limit)

    if res:
        return {"orderbook": res}
    else:
        raise HTTPException(status_code=500, detail="Fetching orderbook failed.")


### TODO IMPLEMENT THE FUNCTIONS

#
# @router.get("/trade/spot/order/status") # TODO - create function in exchange client, fix here
# def get_spot_order_status():
#
#     return {"status": "..."}
