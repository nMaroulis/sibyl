from typing import Optional, Dict
from fastapi import APIRouter, HTTPException
import time
from database.trade_history_db_client import TradeHistoryDBClient
from backend.src.broker.greedy import GreedyBroker
from datetime import datetime
from pydantic import BaseModel
from backend.src.exchange_client.exchange_client_factory import ExchangeClientFactory


router = APIRouter(
    prefix="/broker",
    tags=["Broker"],
    responses={404: {"description": "Not found"}},
)


@router.get("/trade/strategy/history")
def get_active_trade_orders(status: str = 'all'):
    active_trade_strategies = TradeHistoryDBClient.fetch_trading_history(status=status)
    return active_trade_strategies


@router.get("/trade_history/order/status/update")
def get_order_status():

    active_orders = TradeHistoryDBClient.fetch_trading_history(status='all')  # (active, partially completed)

    for i in active_orders:
        exchange_api = i[0]
        symbol_from = i[3]
        symbol_to = i[4]
        symbol_pair = symbol_to + symbol_from
        order_id = i[9]

        client = ExchangeClientFactory.get_client(exchange_api)
        res = client.get_order_status_detailed(symbol_pair, order_id)
        if res:
            TradeHistoryDBClient.update_strategy_status(sell_id=order_id, asset_from=symbol_from, asset_to=symbol_to, new_status=res.status, time_sold=res.time_sold)
        else:
            pass
            # print(f"Error occurred. Status code: {response.status_code}, Response: {response.text}")
    return {"success": "Trading History DB Updated"}


from backend.src.exchange_client_v2.exchange_client_factory import ExchangeClientFactory as v2_exchange_client

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

    client = v2_exchange_client.get_client(spot_trade_params.exchange)
    spot_trade_params_dict = spot_trade_params.model_dump(exclude={'exchange'})
    res = client.place_spot_test_order(**spot_trade_params_dict)

    return res


@router.post("/trade/spot/new")
def post_spot_order(spot_trade_params: SpotTradeParams) -> Dict[str, str]:

    client = v2_exchange_client.get_client(spot_trade_params.exchange)
    spot_trade_params_dict = spot_trade_params.model_dump(exclude={'exchange'})
    res = client.place_spot_order(**spot_trade_params_dict)

    return res


@router.get("/trade/check/minimum_value")
def get_min_trade_value(exchange: str , symbol: str):

    client = v2_exchange_client.get_client(exchange)

    res = client.get_minimum_trade_value(symbol)

    if res:
        return res
    else:
        raise HTTPException(status_code=500, detail="Fetching minimum trade value failed.")


@router.get("/trade/asset/current_price")
def get_current_asset_price(exchange: str , pair_symbol: str) -> dict[str, float]:

    client = v2_exchange_client.get_client(exchange)
    res = client.get_current_asset_price(pair_symbol)
    if res:
        return {"price": res}
    else:
        raise HTTPException(status_code=500, detail="Fetching asset price failed.")
