from fastapi import APIRouter
from fastapi import Query
from typing import Optional, List
from backend.settings import SERVER_IP, SERVER_PORT, BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
import json
import requests
import hmac, hashlib
import time
from backend.db.query_handler import add_trade_to_db, fetch_trading_history
from backend.src.broker.greedy import GreedyBroker


# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/broker",
    tags=["Broker"],
    responses={404: {"description": "Not found"}},
)


@router.get("/trade/order/active")
def get_active_trade_orders():
    res = {}
    json_data = json.dumps(res)
    return json_data


@router.get("/trade/order/inactive")
def get_active_trade_orders():
    res = {}
    json_data = json.dumps(res)
    return json_data


@router.get("/trade/order/buy/new")
def send_new_buy_order(from_coin: str = 'USDT', to_coin: str = 'BTC', from_amount: float = 1.0, strategy: str = 'greedy'):
    gb = GreedyBroker(time.time(), from_coin, to_coin, from_amount, strategy)
    response = gb.send_buy_order()
    if "success" in response:
        df_fields = gb.get_fields_for_db()
        add_trade_to_db(exchange=df_fields[0], datetime_buy=df_fields[1], asset_from=df_fields[2], asset_to=df_fields[3],
                        asset_from_buy_value=df_fields[4], asset_to_buy_quantity=df_fields[5], strategy=df_fields[6],
                        status=df_fields[7])
    return response

