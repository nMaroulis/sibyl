from typing import Optional, Dict
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
    trading_pair: str
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
def post_spot_order(spot_trade_params: SpotTradeParams) -> Dict[str, str]:

    client = ExchangeClientFactory.get_client(spot_trade_params.exchange)
    spot_trade_params_dict = spot_trade_params.model_dump(exclude={'exchange'})
    res = client.place_spot_order(**spot_trade_params_dict)

    return res


@router.get("/trade/check/minimum_value")
def get_min_trade_value(exchange: str , symbol: str):

    client = ExchangeClientFactory.get_client(exchange)

    res = client.get_minimum_trade_value(symbol)

    if res:
        return res
    else:
        raise HTTPException(status_code=500, detail="Fetching minimum trade value failed.")


@router.get("/trade/asset/current_price")
def get_current_asset_price(exchange: str , pair_symbol: str) -> dict[str, float]:

    client = ExchangeClientFactory.get_client(exchange)
    res = client.get_current_asset_price(pair_symbol)
    if res:
        return {"price": res}
    else:
        raise HTTPException(status_code=500, detail="Fetching asset price failed.")


### TODO IMPLEMENT THE FUNCTIONS

@router.get("/trade/spot/history")
def get_active_trade_orders(status: str = 'all'):
    active_trade_strategies = TradeHistoryDBClient.fetch_trading_history(status=status)
    return active_trade_strategies


@router.get("/trade/spot/order/status") # TODO - create function in exchange client, fix here
def get_spot_order_status():

    return {"status": "..."}
