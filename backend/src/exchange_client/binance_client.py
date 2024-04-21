from backend.src.exchange_client.exchange_client import ExchangeAPIClient
import requests
import json
from backend.src.analyst.analyst_functions import get_coin_symbol_name_map, update_coin_symbol_name_map
from backend.config.api_key_handler import get_api_key
import time
import hmac, hashlib


class BinanceClient(ExchangeAPIClient):

    def __init__(self):
        super().__init__()
        self.name = 'Binance'
        self.api_base_url = 'https://api.binance.com'  # 'https://api1.binance.com', 'https://api2.binance.com', 'https://api3.binance.com', 'https://api4.binance.com'
        # Set API Keys
        api_creds = get_api_key("binance")
        if api_creds is None:
            self.api_key, self.api_secret_key = None, None
        else:
            self.api_key = api_creds[0]
            self.api_secret_key = api_creds[1]

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

    def get_crypto_pair_price(self, pair='BTCUSDT'):
        # Binance API endpoint for ticker price
        url = f"{self.api_base_url}/api/v3/ticker/price"
        params = {'symbol': pair}
        response = requests.get(url, params=params)
        if response.status_code == 200:  # Checking if the request was successful
            data = response.json()
            pair_price = data['price']
            return {"price": pair_price}
        else:
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

    def fetch_available_coins(self, symbol):

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

    def fetch_price_history(self, symbol='BTC', interval='1d', plot_type='line', limit=100):
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

