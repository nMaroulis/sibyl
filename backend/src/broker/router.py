from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from database.trade_history_db_client import TradeHistoryDBClient
from backend.src.exchange_client.exchange_client_factory import ExchangeClientFactory
from backend.src.broker.sibyl_trading_engine.strategies.strategy_factory import StrategyFactory
from backend.src.broker.sibyl_trading_engine.tactician.tactician_base import Tactician
from backend.src.broker.sibyl_trading_engine.tactician.exchange_interface import TacticianExchangeInterface
from database.strategy.strategy_db_client import StrategyDBClient
from backend.src.broker.sibyl_trading_engine.evaluator.evaluator import Evaluator
from backend.src.broker.sibyl_trading_engine.tactician.strategy_runtime_manager import StrategyRuntimeHandler
from backend.src.broker.sibyl_trading_engine.backtester.backtester import Backtester
import time
from backend.src.broker.schemas import SpotTradeRequest, SpotTradeResponse, StrategyRequest

router = APIRouter(
    prefix="/broker",
    tags=["Broker"],
    responses={404: {"description": "Not found"}},
)


################
## SPOT TRADING
################

@router.post("/trade/spot/test", response_model=SpotTradeResponse)
def post_spot_order_test(spot_trade_params: SpotTradeRequest):

    client = ExchangeClientFactory.get_client(spot_trade_params.exchange)
    spot_trade_params_dict = spot_trade_params.model_dump(exclude={'exchange'})
    res = client.place_spot_test_order(**spot_trade_params_dict)

    return res


@router.post("/trade/spot/execute", response_model=SpotTradeResponse)
def post_spot_order(spot_trade_params: SpotTradeRequest):

    client = ExchangeClientFactory.get_client(spot_trade_params.exchange)
    spot_trade_params_dict = spot_trade_params.model_dump(exclude={'exchange'})
    res = client.place_spot_order(**spot_trade_params_dict)

    if res["status"] == "success":
        db_res = client.add_spot_order_to_trade_history_db(spot_trade_params.quote_asset,spot_trade_params.base_asset, res["message"])
    # TODO handle failed insertion to DB
    return res


@router.get("/trade/spot/check/symbol_info")
def get_min_trade_value(exchange: str , symbol: str):

    client = ExchangeClientFactory.get_client(exchange)

    res = client.get_symbol_info(symbol)

    if res:
        return res
    else:
        raise HTTPException(status_code=500, detail="Fetching symbol info failed.")


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



########################
## SIBYL STRATEGY ENGINE
########################


strategy_runtime_handler = StrategyRuntimeHandler() # handles Runtime strategies

@router.post("/strategy/start")
def run_strategy(strategy_params: StrategyRequest) -> Dict[str, Any]:
    try:
        client = ExchangeClientFactory.get_client(strategy_params.exchange)

        strategy = StrategyFactory.get_strategy(strategy_params.strategy, strategy_params.params)
        tactician_exchange_api = TacticianExchangeInterface(client)
        # Instantiate the Tactician
        strategy_id = f"strategy_{int(time.time())}"
        symbol = f"{strategy_params.base_asset}{strategy_params.quote_asset}"

        tactician = Tactician(exchange_api=tactician_exchange_api, quote_asset=strategy_params.quote_asset, base_asset=strategy_params.base_asset, capital_allocation=strategy_params.quote_amount)
        # Run the strategy with a n-second interval and stop if capital is less than min_capital
        tactician.run_strategy(strategy_id, strategy, interval=strategy_params.time_interval, min_capital=0.0, trades_limit=strategy_params.num_trades, dataset_size=strategy_params.dataset_size)

        strategy_runtime_handler.add_strategy(strategy_id, tactician)
        return {"status": "success", "strategy_id": strategy_id}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

from fastapi.encoders import jsonable_encoder


@router.post("/strategy/backtest/start")
def run_strategy_backtest(strategy_params: StrategyRequest) -> Dict[str, Any]:

    try:
        client = ExchangeClientFactory.get_client(strategy_params.exchange)
        strategy = StrategyFactory.get_strategy(strategy_params.strategy, strategy_params.params)
        symbol = f"{strategy_params.base_asset}{strategy_params.quote_asset}"
        backtester = Backtester(strategy, client, symbol, strategy_params.time_interval)
        logs, score = backtester.run_backtest()

        if logs and len(logs) > 0:
            evaluator = Evaluator(logs)
            metrics = evaluator.evaluate()
            return {"metrics": metrics, "logs": jsonable_encoder(logs), "score": score}
        else:
            raise HTTPException(status_code=500, detail="Empty Logs")
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategy/metadata")
def get_strategy_metadata(strategy_id: str):
    try:
        db_client = StrategyDBClient()
        if strategy_id == "all":
            res = db_client.get_all_strategies()

            # Add strategy Status
            for strategy in res:
                strategy["status"] = "active" if strategy["strategy_id"] in strategy_runtime_handler.get_active_strategies() else "inactive"
        else:
            res = db_client.get_strategy_metadata(strategy_id)

        if res:
            return res
        else:
            return []
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategy/logs")
def get_strategy_logs(strategy_id: str, from_timestamp: int = None):
    try:
        db_client = StrategyDBClient()
        res = db_client.get_logs(strategy_id, from_timestamp)
        if res:
            return res
        else:
            return {}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategy/status/info")
def get_strategy_status(strategy_id: str):
    return {}


@router.get("/strategy/status/stop")
def stop_strategy(strategy_id: str):
    status = strategy_runtime_handler.stop_strategy(strategy_id)
    if status:
        return {"success": f"strategy {strategy_id} stopped"}
    else:
        raise HTTPException(status_code=500, detail=str(status))


@router.get("/strategy/evaluation")
def strategy_evaluation(strategy_id: str):
    strategy_logs = get_strategy_logs(strategy_id, None)

    if strategy_logs and len(strategy_logs) > 0:

        evaluator = Evaluator(strategy_logs)
        metrics = evaluator.evaluate()
        return {"metrics": metrics}
    else:
        raise HTTPException(status_code=500, detail="Empty Logs")


@router.get("/strategies")
def get_available_strategies():

    STRATEGIES = ["Bollinger Bands", "[Sibyl] Bollinger Surge", "Exponential Moving Average (EMA) crossover", "[Sibyl] Impulse Breakout", "[Sibyl] Quantum Momentum", "RSI"]
    try:
        return {"strategies": STRATEGIES}
    except Exception as e:
        raise HTTPException(status_code=500, detail=e)


