from backend.src.exchange_client.exchange_client import ExchangeAPIClient
import requests
import json
from backend.src.analyst.analyst_functions import get_coin_symbol_name_map, update_coin_symbol_name_map
from backend.db.api_keys_db_client import APIEncryptedDatabase
import time
import hmac, hashlib
from datetime import datetime


class BinanceClient(ExchangeAPIClient):

    def __init__(self):
        super().__init__()
        self.name = 'binance'
        self.api_base_url = 'https://api.binance.com'  # 'https://api1.binance.com', 'https://api2.binance.com', 'https://api3.binance.com', 'https://api4.binance.com'
        # Set API Keys
        api_creds = APIEncryptedDatabase.get_api_key_by_name("binance")
        if api_creds is None:
            self.api_key, self.api_secret_key = None, None
        else:
            self.api_key, self.api_secret_key = api_creds.api_key, api_creds.secret_key

    def check_status(self):
        if self.api_key is None or self.api_secret_key is None:
            return 'Empty Credentials'

        base_url = f"{self.api_base_url}/api/v3/account"
        timestamp = int(time.time() * 1000)
        query_string = f"timestamp={timestamp}"
        signature = hmac.new(self.api_secret_key.encode(), query_string.encode(), hashlib.sha256).hexdigest()
        query_string_with_signature = f"{query_string}&signature={signature}"
        headers = {"X-MBX-APIKEY": self.api_key}
        url = f"{base_url}?{query_string_with_signature}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return 'Active'
        else:
            return 'Invalid Credentials'

    def get_crypto_pair_price(self, pair: str):
        # Binance API endpoint for ticker price
        url = f"{self.api_base_url}/api/v3/ticker/price"
        params = {'symbol': pair}
        response = requests.get(url, params=params)
        if response.status_code == 200:  # Checking if the request was successful
            data = response.json()
            pair_price = data['price']
            return {"price": pair_price}
        else:
            print(f'backend :: {self.name} Exchange API client :: get_crypto_pair_price for pair ({pair}) :: Failed to retrieve current price.')
            return {"error": 'Could not fetch price'}

    def get_spot_balance(self):

        # Binance API endpoint
        account_url = f"{self.api_base_url}/api/v3/account"
        # Request headers and parameters
        headers = {'X-MBX-APIKEY': self.api_key}
        params = {'timestamp': int(time.time() * 1000), }
        # Generate the query string
        query_string = '&'.join([f'{key}={value}' for key, value in params.items()])
        # Create a signature
        signature = hmac.new(self.api_secret_key.encode('utf-8'), query_string.encode('utf-8'),
                             hashlib.sha256).hexdigest()
        # Add the signature to the request parameters
        params['signature'] = signature
        # Send the GET request to Binance API
        response = requests.get(account_url, headers=headers, params=params)
        try:
            data = response.json()
        except json.JSONDecodeError as error:
            return {"error": "Unable to parse response JSON."}

        if response.status_code == 200:  # Check if the request was successful
            spot_balances = {}  # all balance
            locked_earn_balances = {}  # Retrieve the locked Earn balances
            staked_balances = {}  # Retrieve the staked balances
            for asset in data['balances']:
                if float(asset['free']) > 0.0 or float(asset['locked']) > 0.0:

                    fetched_price = self.get_crypto_pair_price(asset['asset'] + 'USDT')
                    asset_price = 1.0  # default price, for BUSD, USDT prices in USDT
                    if "error" not in fetched_price:
                        asset_price = fetched_price['price']
                        # if asset_price == 0:
                        #     asset_price = 1.0

                    spot_balances[asset['asset']] = {
                        'free': float(asset['free']),
                        'locked': float(asset['locked']),
                        'price': asset_price
                    }
                    if asset['asset'].startswith('LD'):
                        locked_earn_balances[asset['asset']] = {
                            'free': float(asset['free']),
                            'locked': float(asset['locked']),
                            'price': asset_price
                        }
                    if asset['asset'].startswith('ST'):
                        staked_balances[asset['asset']] = {
                            'free': float(asset['free']),
                            'locked': float(asset['locked']),
                            'price': asset_price
                        }
            # print(json.dumps(spot_balances, indent=4))
            return {'spot_balances': spot_balances,
                    'locked_earn_balances': locked_earn_balances,
                    'staked_balances': staked_balances,
                    }
        else:
            # Request was not successful, return the error message
            return {"error": data['msg']}

    def fetch_available_coins(self):

        headers = {'X-MBX-APIKEY': self.api_key}
        url = f"{self.api_base_url}/api/v1/exchangeInfo"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            try:
                data = response.json()
                if 'symbols' in data:
                    # Function to return all Coins
                    # available_coins = set()
                    #     base_asset = symbol['baseAsset']
                    #     quote_asset = symbol['quoteAsset']
                    #     if base_asset not in available_coins:
                    #         available_coins.add(base_asset)
                    #     if quote_asset not in available_coins:
                    #         available_coins.add(quote_asset)
                    coin_name_dict = get_coin_symbol_name_map()
                    available_coins = []  # = [symbol['symbol'] for symbol in data['symbols']]
                    for symbol in data['symbols']:
                        if 'USDT' in symbol['symbol']:
                            s = symbol['symbol'].replace('USDT', '')
                            if len(s) > 1:
                                if s in coin_name_dict.keys():  # if symbol exists in dict
                                    if coin_name_dict[s] != s:  # if name and symbol are the same, keep one
                                        available_coins.append(f"{coin_name_dict[s]} [{s}]")
                                    else:
                                        available_coins.append(s)
                                else:
                                    available_coins.append(s)
                    return available_coins
                else:
                    print("Error: Unable to fetch data from Binance API")
                    return []
            except json.JSONDecodeError:
                return {"Error": "Unable to parse response JSON."}
        else:
            return {"Error": "Failed to fetch available coins"}

    def fetch_price_history(self, symbol: str = 'BTC', interval: str = '1d', plot_type: str = 'line', limit: int = 100):
        headers = {'X-MBX-APIKEY': self.api_key}
        url = f"{self.api_base_url}/api/v3/klines?symbol={symbol.upper()}&interval={interval}&limit={limit}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            try:
                data = response.json()
            except json.JSONDecodeError as error:
                return []  # {"error": "Unable to parse response JSON."}
            if plot_type == 'line':  # requested line plot
                price_history = [{"Open Time": entry[0], "Open Price": entry[1]} for entry in data]
            else:  # candle plot
                price_history = [{"Open Time": entry[0],
                                  "Open Price": entry[1],
                                  "Highs": entry[2],
                                  "Lows": entry[3],
                                  "Closing Price": entry[4],
                                  } for entry in data]
            return price_history
        else:
            return []  # {"error": "Failed to fetch price history"}

    def get_minimum_buy_order(self, symbol: str = "BTCUSDT"):
        url = f"{self.api_base_url}/api/v3/exchangeInfo?symbol={symbol}"  # {symbol}&quantity={quantity}&price={price}"
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

    """ TRADE FUNCTIONS """
    def post_buy_order(self, trade_from: str, trade_to: str, from_amount: int):

        url = f"{self.api_base_url}/api/v3/order"  # endpoint URL for creating a new order
        trading_pair = f"{trade_to}{trade_from}"
        # Set the request parameters
        params = {
            'symbol': trading_pair,  # Trading pair symbol for ADA/USDT
            'side': 'BUY',  # Buy order
            'type': 'MARKET',  # Market order type
            # 'quantity': 3,  # Quantity of Crypto to buy
            'quoteOrderQty': from_amount,  # Quantity of USDT to spend
            'recvWindow': 5000,  # Optional, receive window in milliseconds
            'timestamp': int(time.time() * 1000)  # Timestamp in milliseconds
        }
        # Generate the query string
        query_string = '&'.join([f'{key}={params[key]}' for key in params])
        # Sign the query string
        signature = hmac.new(self.api_secret_key.encode('utf-8'), query_string.encode('utf-8'),
                             hashlib.sha256).hexdigest()
        # Add the API key and signature to the request headers
        headers = {
            'X-MBX-APIKEY': self.api_key,
        }
        # Add the signature to the query string
        query_string += f'&signature={signature}'
        # Make the API request
        response = requests.post(f'{url}?{query_string}', headers=headers)
        """
        response body:
        {"symbol": "ADAUSDT", "orderId": 10xInt, "orderListId": -1, "clientOrderId": "str",
         "transactTime": "timestamp", "price": "0.00000000", "origQty": "17.90000000", "executedQty": "17.90000000",
         "cummulativeQuoteQty": "4.99768000", "status": "FILLED", "timeInForce": "GTC", "type": "MARKET", "side": "BUY",
         "workingTime": "timestamp", "fills": [
            {"price": "0.27920000", "qty": "17.90000000", "commission": "0.00001618", "commissionAsset": "BNB",
             "tradeId": 10xInt}], "selfTradePreventionMode": "NONE"}
        """
        print("backend :: BinanceExchange client :: post_buy_order :: response status ", response.status_code)
        print("backend :: BinanceExchange client :: post_buy_order :: response body ", response.text)
        if response.status_code == 200:
            try:
                quantity_bought = response.json()['executedQty']
                buy_order_id = response.json()['orderId']
                buy_datetime = str(datetime.utcfromtimestamp(response.json()['transactTime'] // 1000).strftime('%Y-%m-%d %H:%M:%S')) # response.json()['transactTime']  # overwrite Datetime with the Datetime of Buy
                return quantity_bought, buy_order_id, buy_datetime
            except KeyError:
                return None
        else:
            return None  # "transactTime"

    def post_swap_order(self, trade_from: str, trade_to: str, from_amount: int):  # Alternative to BUY order with No fees in Binance

        url = f"{self.api_base_url}/sapi/v1/convert/getQuote"
        timestamp = str(int(time.time() * 1000))
        params = {
            'fromAsset': trade_from,
            'toAsset': trade_to,
            'fromAmount': from_amount,
            'walletType': 'SPOT',
            'recvWindow': '5000',
            'timestamp': timestamp,
        }
        headers = {
            'X-MBX-APIKEY': self.api_key
        }
        query_string = '&'.join([f'{key}={params[key]}' for key in params])
        signature = hmac.new(self.api_secret_key.encode('utf-8'),
                             query_string.encode('utf-8'),
                             hashlib.sha256).hexdigest()
        query_string += f'&signature={signature}'
        response = requests.post(f'{url}?{query_string}', headers=headers)

        if response.status_code == 200:
            try:
                buy_order_id = response.json()['quoteId']
                # print(response.json())
                # accept the Quote
                url = f"{self.api_base_url}/sapi/v1/convert/acceptQuote"
                timestamp = str(int(time.time() * 1000))
                params = {
                    'quoteId': buy_order_id,
                    'recvWindow': '5000',
                    'timestamp': timestamp,
                }
                query_string = '&'.join([f'{key}={params[key]}' for key in params])
                signature = hmac.new(self.api_secret_key.encode('utf-8'),
                                     query_string.encode('utf-8'),
                                     hashlib.sha256).hexdigest()
                query_string += f'&signature={signature}'
                response = requests.post(f'{url}?{query_string}', headers=headers)
                buy_order_id = response.json()['orderId']
                quantity_bought = response.json()['toAmount']
                return buy_order_id, quantity_bought, timestamp
            except KeyError as e:
                print(f"binance_client :: post_swap_order {e}")
                return None
        else:
            return None

    def post_sell_order(self, trade_from: str, trade_to: str, quantity: float, sell_order_price: float):

        timestamp = int(time.time() * 1000)
        url = f"{self.api_base_url}/api/v3/order"  # endpoint URL for creating a new order
        trading_pair = f"{trade_from}{trade_to}"
        print(f"backend :: BinanceExchange client :: post_sell_order :: Sell order for {quantity} {trade_from} at {sell_order_price} {trade_to}")
        # Build the query string
        query_string = f'symbol={trading_pair}&side=SELL&type=LIMIT&timeInForce=GTC&quantity={quantity}&price={sell_order_price}&timestamp={timestamp}'
        signature = hmac.new(self.api_secret_key.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        query_string += f'&signature={signature}'
        headers = {
            'X-MBX-APIKEY': self.api_key,
        }

        # Send to the request URL
        response = requests.post(f'{url}?{query_string}', headers=headers)
        print("backend :: BinanceExchange client :: post_sell_order :: response status ", response.status_code)
        print("backend :: BinanceExchange client :: post_sell_order :: response body ", response.text)
        """
        response body:
        {"symbol":"ADAUSDT","orderId":10xInt,"orderListId":-1,"clientOrderId":"str",
        "transactTime":timestamp,"price":"0.29260000","origQty":"17.90000000","executedQty":"0.00000000",
        "cummulativeQuoteQty":"0.00000000","status":"NEW","timeInForce":"GTC","type":"LIMIT","side":"SELL",
        "workingTime":timestamp,"fills":[],"selfTradePreventionMode":"NONE"}
        """

        if response.status_code == 200:
            try:
                sell_order_id = response.json()['orderId']
                return sell_order_id
            except KeyError:
                return None
        else:
            return None
