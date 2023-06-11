from fastapi import APIRouter
from fastapi import Query
from typing import Optional, List
from backend.settings import SERVER_IP, SERVER_PORT, BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
import json
import requests
import hmac, hashlib
import time


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


@router.get("/trade/order/convert/quote")
def send_new_convert_order():
        # API endpoint URLs
    base_url = BINANCE_API_URL
    api_path = '/sapi/v1/'
    trade_path = api_path + 'convert/getQuote'

    # Parameters for the conversion
    amount = '1'  # Amount of USDT to convert
    symbol = 'USDT'  # Trading pair symbol (USDT to ADA)
    symbol_to = 'ADA'  # Trading pair symbol (USDT to ADA)


    # Generate timestamp
    timestamp = str(int(time.time() * 1000))

    # Generate signature
    signature_payload = f'fromAsset={symbol}&amount={amount}&toAsset={symbol_to}&recvWindow=5000&timestamp={timestamp}'
    signature = hmac.new(BINANCE_API_SECRET_KEY.encode('utf-8'), signature_payload.encode('utf-8'), hashlib.sha256).hexdigest()

    # Prepare request parameters
    params = {
        'fromAsset': 'USDT',
        'toAsset': 'ADA',
        'fromAmount': '1',
        'walletType': 'SPOT',
        'recvWindow': '5000',
        'timestamp': timestamp,
    }
    # Prepare headers
    headers = {
        'X-MBX-APIKEY': BINANCE_API_KEY
    }
    # Send POST request to convert USDT to ADA
    response = requests.post(base_url + trade_path, params=params, headers=headers)
    print(response.status_code)
    print(response.text)
    # Process the response
    if response.status_code == 200:
        print(f"Successfully bought {1} ADA worth {1} USDT!")
        return response.json()
    else:
        # Error occurred
        print("Failed to place buy order.")
        return {"error": "Buy order failed"}


@router.get("/trade/order/convert/new")
def send_new_convert_order():
        # API endpoint URLs
    base_url = BINANCE_API_URL
    api_path = '/sapi/v1/'
    trade_path = api_path + 'asset/transfer'

    # Parameters for the conversion
    amount = '1'  # Amount of USDT to convert
    symbol = 'USDTADA'  # Trading pair symbol (USDT to ADA)

    # Generate timestamp
    timestamp = str(int(time.time() * 1000))

    # Generate signature
    signature_payload = f'asset=USDT&amount={amount}&type=MAIN_C2C&recvWindow=5000&timestamp={timestamp}'
    signature = hmac.new(BINANCE_API_SECRET_KEY.encode('utf-8'), signature_payload.encode('utf-8'), hashlib.sha256).hexdigest()

    # Prepare request parameters
    params = {
        'asset': 'USDT',
        'amount': amount,
        'type': 'MAIN_C2C',
        'recvWindow': '5000',
        'timestamp': timestamp,
        'signature': signature
    }
    # Prepare headers
    headers = {
        'X-MBX-APIKEY': BINANCE_API_KEY
    }
    # Send POST request to convert USDT to ADA
    response = requests.post(base_url + trade_path, params=params, headers=headers)
    print(response.status_code)
    print(response.text)
    # Process the response
    if response.status_code == 200:
        print(f"Successfully bought {1} ADA worth {1} USDT!")
        return response.json()
    else:
        # Error occurred
        print("Failed to place buy order.")
        return {"error": "Buy order failed"}


@router.get("/trade/order/buy/new")
def send_new_buy_order():
    url = f"{BINANCE_API_URL}/api/v3/order" # endpoint URL for creating a new order
    # Set the request parameters
    params = {
        'symbol': 'ADAUSDT',  # Trading pair symbol for ADA/USDT
        'side': 'BUY',  # Buy order
        'type': 'MARKET',  # Market order type
        # 'quantity': 3,  # Quantity of ADA to buy
        'quoteOrderQty': 1,  # Quantity of USDT to spend
        'recvWindow': 5000,  # Optional, receive window in milliseconds
        'timestamp': int(time.time() * 1000)  # Timestamp in milliseconds
    }
    # Generate the query string
    query_string = '&'.join([f'{key}={params[key]}' for key in params])
    # Sign the query string
    signature = hmac.new(BINANCE_API_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    # Add the API key and signature to the request headers
    headers = {
        'X-MBX-APIKEY': BINANCE_API_KEY,
    }
    # Add the signature to the query string
    query_string += f'&signature={signature}'
    # Make the API request
    response = requests.post(f'{url}?{query_string}', headers=headers)
    # print(response.status_code)
    # print(response.text)
    # Process the response
    if response.status_code == 200:
        # print(f"Successfully bought {1} ADA worth {1} USDT!")
        return response.json()
    else:
        # Error occurred
        # print("Failed to place buy order.")
        return {"error": "Buy order failed"}
