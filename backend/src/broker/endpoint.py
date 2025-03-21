from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from database.trade_history_db_client import TradeHistoryDBClient
from datetime import datetime
from pydantic import BaseModel
from backend.src.exchange_client.exchange_client_factory import ExchangeClientFactory
from backend.src.broker.strategies.strategy_factory import StrategyFactory
from backend.src.broker.tactician.tactician_base import Tactician


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


@router.post("/trade/spot/execute")
def post_spot_order(spot_trade_params: SpotTradeParams) -> Dict[str, Any]:

    client = ExchangeClientFactory.get_client(spot_trade_params.exchange)
    spot_trade_params_dict = spot_trade_params.model_dump(exclude={'exchange'})
    res = client.place_spot_order(**spot_trade_params_dict)

    if res["status"] == "success":
        db_res = client.add_spot_order_to_trade_history_db(spot_trade_params.quote_asset,spot_trade_params.base_asset, res["message"])
    # TODO handle failed insertion to DB
    return res


@router.get("/trade/spot/check/minimum_value")
def get_min_trade_value(exchange: str , symbol: str):

    client = ExchangeClientFactory.get_client(exchange)

    res = client.get_minimum_trade_value(symbol)

    if res:
        return res
    else:
        raise HTTPException(status_code=500, detail="Fetching minimum trade value failed.")


@router.get("/trade/spot/asset/market_price")
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



### STRATEGIES


class StrategyParams(BaseModel):
    exchange: str
    quote_asset: str
    quote_amount: float
    base_asset: str
    time_interval: str
    strategy: str
    num_trades: int
    params: Dict[str, Any]  # Holds strategy-specific parameters


@router.post("/strategy/backtesting/start")
def run_strategy_backtesting(strategy_params: StrategyParams) -> Dict[str, Any]: # TODO Implement
    return {}


@router.post("/strategy/start")
def run_strategy(strategy_params: StrategyParams) -> Dict[str, Any]:
    try:
        client = ExchangeClientFactory.get_client("binance_testnet")# strategy_params.exchange)

        strategy = StrategyFactory.get_strategy(strategy_params.strategy, strategy_params.params)

        # Instantiate the Tactician
        symbol = f"{strategy_params.base_asset}{strategy_params.quote_asset}"
        tactician = Tactician(exchange=client, symbol=symbol, capital_allocation=strategy_params.quote_amount)

        # Run the strategy with a n-second interval and stop if capital is less than min_capital
        tactician.run_strategy(strategy, interval=strategy_params.time_interval, min_capital=0.0, trades_limit=strategy_params.num_trades)
        return {}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/strategy/status/info")
def get_strategy_status(strategy_id: int):
    return {}


@router.get("/strategy/status/stop")
def stop_strategy(strategy_id: int):
    return {}