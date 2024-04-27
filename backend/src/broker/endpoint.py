from fastapi import APIRouter
from fastapi import Query
from typing import Optional, List
from backend.settings import SERVER_IP, SERVER_PORT, BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
import json
import requests
import hmac, hashlib
import time
from backend.db.query_handler import add_trade_to_db, fetch_trading_history, update_strategy_status
from backend.src.broker.greedy import GreedyBroker
from datetime import datetime


# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/broker",
    tags=["Broker"],
    responses={404: {"description": "Not found"}},
)


@router.get("/trade/strategy/history")
def get_active_trade_orders(status: str = 'all'):
    active_trade_strategies = fetch_trading_history(status=status)
    return active_trade_strategies


@router.get("/trade/order/buy/new")
def send_new_buy_order(from_coin: str = 'USDT', to_coin: str = 'BTC', from_amount: float = 1.0, strategy: str = 'greedy', order_type: str = 'swap'):
    gb = GreedyBroker(time.strftime('%Y-%m-%d %H:%M:%S'), from_coin, to_coin, from_amount, order_type)
    print(gb.get_db_fields())
    response = gb.send_buy_order()
    if "success" in response:
        db_fields = gb.get_db_fields()
        add_trade_to_db(exchange=db_fields[0], datetime_buy=db_fields[1], orderid_buy=db_fields[2],
                        asset_from=db_fields[3], asset_to=db_fields[4], asset_from_amount=db_fields[5],
                        asset_to_quantity=db_fields[6], asset_to_price=db_fields[7], datetime_sell=db_fields[8],
                        orderid_sell=db_fields[9], asset_to_sell_price=db_fields[10], order_type=db_fields[11],
                        strategy=db_fields[12], status=db_fields[13])
        print('Backend :: Broker :: endpoint :: ', gb)
    return response


@router.get("/trade/info/minimum_order")
def is_buy_order_possible(symbol: str = 'BTCUSDT'):
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


@router.get("/trade/order/status/update")
def get_order_status(symbol: str = 'BNBUSDT', order_id: str = ''):
    """
    NEW: The order has been created and is active but has not been executed yet.
    PARTIALLY_FILLED: The order has been partially filled, meaning that a portion of the requested quantity has been executed, but there are still remaining unfilled quantities.
    FILLED: The order has been completely filled, indicating that the entire requested quantity has been executed.
    CANCELED: The order has been canceled either by the user or due to other conditions, such as time in force (TIF) expiration or insufficient funds.
    PENDING_CANCEL: The order is in the process of being canceled.
    REJECTED: The order has been rejected, usually due to invalid parameters or other error conditions.
    EXPIRED: The order has expired and was not executed within the specified time frame.
    INVALID: The order is considered invalid, often due to incorrect parameters or other issues.
    """
    active_orders = fetch_trading_history(status='all')  # (active, partially completed)
    url = f"{BINANCE_API_URL}/api/v3/order"

    for i in active_orders:
        symbol_from = i[3]
        symbol_to = i[4]
        symbol_pair = symbol_to + symbol_from
        order_id = i[9]

        # Create the request parameters
        params = {
            'symbol': symbol_pair,  # Replace with the symbol of your asset
            'orderId': order_id,
            'timestamp': int(time.time() * 1000),
            'recvWindow': 5000,
        }
        query_string = '&'.join([f'{key}={params[key]}' for key in params])
        signature = hmac.new(BINANCE_API_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'),
                             hashlib.sha256).hexdigest()
        query_string += f'&signature={signature}'
        headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
        response = requests.get(f'{url}?{query_string}', headers=headers)
        # print(response.text)
        # Process the response
        new_status = 'active'
        time_sold = None
        if response.status_code == 200:
            order_status = response.json()
            if order_status['status'] == 'NEW':
                pass  # remain active
            elif order_status['status'] == 'PARTIALLY_FILLED':
                new_status = 'partially_completed'
            elif order_status['status'] == 'FILLED':
                url_to_get_time_sold = f"{BINANCE_API_URL}/api/v3/myTrades"
                res_time_sold = requests.get(f'{url_to_get_time_sold}?{query_string}', headers=headers)
                time_sold = res_time_sold.json()[0]['time']  # str()
                time_sold = str(datetime.utcfromtimestamp(time_sold//1000).strftime('%Y-%m-%d %H:%M:%S'))
                new_status = 'completed'
            else:  # CANCELLED, PENDING_CANCEL, REJECTED, EXPIRED, INVALID
                new_status = 'cancelled'
            update_strategy_status(sell_id=order_id, asset_from=symbol_from, asset_to=symbol_to,
                                       new_status=new_status, time_sold=time_sold)
        else:
            print(f"Error occurred. Status code: {response.status_code}, Response: {response.text}")
    return {"success": "Trading History DB Updated"}


@router.get("/trade/order/status/single_order")
def get_order_status(symbol: str = 'BNBUSDT', order_id: str = ''):

    url = f"{BINANCE_API_URL}/api/v3/myTrades"
    params = {'symbol': symbol, 'orderId': order_id, 'timestamp': int(time.time() * 1000), 'recvWindow': 5000}
    query_string = '&'.join([f'{key}={params[key]}' for key in params])
    signature = hmac.new(BINANCE_API_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'),
                         hashlib.sha256).hexdigest()
    query_string += f'&signature={signature}'
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    response = requests.get(f'{url}?{query_string}', headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": 'Trade not found!'}
