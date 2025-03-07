from typing import Optional

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

class TradeParams(BaseModel):
    exchange_api: str
    from_coin: str = 'USDT'
    to_coin: str
    from_amount: float
    strategy: str
    strategy_params: dict
    order_type: str

@router.post("/trade/order/buy/new") # TODO FIX HERE
def send_new_buy_order(trade_params: TradeParams):

    client = ExchangeClientFactory.get_client(trade_params.exchange_api)
    if trade_params.strategy == 'greedy':
        broker_client = GreedyBroker(client, time.strftime('%Y-%m-%d %H:%M:%S'), trade_params.from_coin, trade_params.to_coin, trade_params.from_amount, trade_params.order_type, trade_params.strategy_params)
    else:
        raise HTTPException(status_code=400, detail="Strategy not found.")

    response = broker_client.init_trading_algorithm()
    print(broker_client.get_db_fields())
    if "success" in response:
        db_fields = broker_client.get_db_fields()
        TradeHistoryDBClient.add_trade_to_db(exchange=db_fields[0], datetime_buy=db_fields[1], orderid_buy=db_fields[2],
                        asset_from=db_fields[3], asset_to=db_fields[4], asset_from_amount=db_fields[5],
                        asset_to_quantity=db_fields[6], asset_to_price=db_fields[7], datetime_sell=db_fields[8],
                        orderid_sell=db_fields[9], asset_to_sell_price=db_fields[10], order_type=db_fields[11],
                        strategy=db_fields[12], status=db_fields[13])
        print('Backend :: Broker :: endpoint :: ', broker_client)
        return response
    else:
        return response


@router.get("/trade/info/minimum_order")
def is_buy_order_possible(exchange: str , symbol: str):

    client = ExchangeClientFactory.get_client(exchange)
    try:
        res = client.get_minimum_buy_order(symbol)
        print(res)
        return res
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail="Fetching minimum buy order failed.")


@router.get("/trade/convert/info")
def send_new_convert_order(exchange: str) -> dict[str, str]:

    client = ExchangeClientFactory.get_client(exchange)
    res = client.check_swap_eligibility('USDT', 'BTC', 10)  # dummy vars

    return {"success": "Binance Convert API is enabled!"} if res else {"error": "Binance Convert API is NOT enabled!"}


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


@router.get("/trade/order/status/single_order")
def get_single_order_status(exchange_api: str, symbol: str, order_id: str):

    client = ExchangeClientFactory.get_client(exchange_api)
    res = client.get_order_status(symbol=symbol, order_id=order_id)
    if res:
        return res
    else:
        return {"error": 'Trade not found!'}



from backend.src.exchange_client_v2.exchange_client_factory import ExchangeClientFactory as abc

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
def post_spot_order(spot_trade_params: SpotTradeParams):

    client = abc.get_client(spot_trade_params.exchange)
    print(spot_trade_params)
    spot_trade_params_dict = spot_trade_params.model_dump(exclude={'exchange'})
    res = client.place_spot_test_order(**spot_trade_params_dict)

    if res:
        return {"success": 'trade is possible!'}
    else:
        return {"error": 'Trade not possible!'}


