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
    active_trade_strategies = fetch_trading_history()
    return active_trade_strategies


@router.get("/trade/order/inactive")
def get_active_trade_orders():
    inactive_trade_strategies = fetch_trading_history(status='inactive')
    return inactive_trade_strategies


@router.get("/trade/order/buy/new")
def send_new_buy_order(from_coin: str = 'USDT', to_coin: str = 'BTC', from_amount: float = 1.0, strategy: str = 'greedy', order_type: str = 'swap'):
    gb = GreedyBroker(time.time(), from_coin, to_coin, from_amount, order_type)
    print(gb.get_fields_for_db())
    response = gb.send_buy_order()
    if "success" in response:
        df_fields = gb.get_fields_for_db()
        add_trade_to_db(exchange=df_fields[0], datetime_buy=df_fields[1], asset_from=df_fields[2], asset_to=df_fields[3],
                        asset_from_amount=df_fields[4], asset_to_buy_quantity=df_fields[5], strategy=df_fields[6],
                        status=df_fields[7])
    return response


@router.get("/trade/info/minimum_order")
def is_buy_order_possible(symbol: str = 'BTCUSDT'):
    # Binance API endpoint for exchange information
    url = f"{BINANCE_API_URL}/api/v3/exchangeInfo?symbol={symbol}"  # {symbol}&quantity={quantity}&price={price}"
    response = requests.get(url)  # Send a GET request to retrieve the trading pairs' details
    exchange_info = response.json()
    minimum_buy = -1
    # print(exchange_info['symbols'][0]['filters'])
    # Find the symbol in the exchange information
    try:
        for symbol_info in exchange_info['symbols'][0]['filters']:
            if symbol_info['filterType'] == 'NOTIONAL':
                minimum_buy = float(symbol_info['minNotional'])
                # print(symbol_info['minNotional'])
    except KeyError:
        return {'min_notional': -1}
    except AttributeError:
        return {'min_notional': -1}

    return {'min_notional': minimum_buy}  # If the symbol is not found, return False


@router.get("/trade/convert/info")  # https://binance-docs.github.io/apidocs/spot/en/#convert-endpoints
def send_new_convert_order():  # Alternative to BUY order with No fees in Binance
    # Send a simple getQuote request in order to see if convert/swap API is enables
    # API endpoint URLs
    url = BINANCE_API_URL + '/sapi/v1/convert/getQuote'
    # Default Parameters for the conversion
    amount = 1  # Amount of USDT to convert
    symbol = "USDT"  # Trading pair symbol (USDT to ADA)
    symbol_to = "BTC"  # Trading pair symbol (USDT to ADA)
    timestamp = str(int(time.time() * 1000))
    params = {
        'fromAsset': symbol,
        'toAsset': symbol_to,
        'fromAmount': amount,
        'walletType': 'SPOT',
        'recvWindow': '5000',
        'timestamp': timestamp,
    }
    headers = {
        'X-MBX-APIKEY': BINANCE_API_KEY
    }
    query_string = '&'.join([f'{key}={params[key]}' for key in params])
    signature = hmac.new(BINANCE_API_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'),
                         hashlib.sha256).hexdigest()
    query_string += f'&signature={signature}'
    response = requests.post(f'{url}?{query_string}', headers=headers)
    if response.status_code == 200:
        if "quoteId" in response.json():
            return {"success": "Binance Convert API is enabled!"}

    return {"error": "Binance Convert API is NOT enabled!"}

