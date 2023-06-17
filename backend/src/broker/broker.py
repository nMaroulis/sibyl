from backend.settings import BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
import requests
import hmac, hashlib
import time


class Broker:

    def __init__(self, datetime=None, trade_from='USDT', trade_to='BTC', from_amount=1.0, order_type='swap'):
        self.strategy = None  # Strategy Type
        self.sub_strategy = None  # Subcategory of Strategy
        self.datetime = datetime
        self.trade_from = trade_from
        self.trade_to = trade_to
        self.trading_pair = trade_to + trade_from
        self.from_amount = from_amount
        self.quantity_bought = None  # populated after the buy order has been completed
        self.current_trade_to_price = 1.0
        self.sell_order_price = 1.0  # what price to sell the coin in order to make profit
        self.datetime_sell = None
        self.profit_percentage = 5
        self.order_type = order_type
        self.buy_order_id = None   # if swap then this is the quote
        self.sell_order_id = None

    def __str__(self):
        return f"{self.datetime}: Bought {self.quantity_bought} {self.trade_to} for {self.from_amount} {self.trade_from}, in order to sell it at a price of {self.sell_order_price}"

    def fetch_sell_order_price(self):  # Fetches the current price of the coin and returns the price after the x% expected profit, in order to make the sell order

        url = BINANCE_API_URL + '/api/v3/ticker/price' + '?symbol=' + self.trading_pair
        response = requests.get(url)
        print(response.text)
        if response.status_code == 200:
            data = response.json()
            self.current_trade_to_price = float(data['price'])
            return response.status_code
        else:
            print('Broker :: fetch_sell_order_price :: Failed to retrieve current price.')
            return -1

    def post_buy_order(self):

        url = f"{BINANCE_API_URL}/api/v3/order"  # endpoint URL for creating a new order

        # Set the request parameters
        params = {
            'symbol': self.trading_pair,  # Trading pair symbol for ADA/USDT
            'side': 'BUY',  # Buy order
            'type': 'MARKET',  # Market order type
            # 'quantity': 3,  # Quantity of ADA to buy
            'quoteOrderQty': self.from_amount,  # Quantity of USDT to spend
            'recvWindow': 5000,  # Optional, receive window in milliseconds
            'timestamp': int(time.time() * 1000)  # Timestamp in milliseconds
        }
        # Generate the query string
        query_string = '&'.join([f'{key}={params[key]}' for key in params])
        # Sign the query string
        signature = hmac.new(BINANCE_API_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'),
                             hashlib.sha256).hexdigest()
        # Add the API key and signature to the request headers
        headers = {
            'X-MBX-APIKEY': BINANCE_API_KEY,
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
        print("backend :: GreedyBroker :: post_buy_order :: response status ", response.status_code)
        print("backend :: GreedyBroker :: post_buy_order :: response body ", response.text)
        if response.status_code == 200:
            try:
                self.quantity_bought = response.json()['executedQty']
                self.buy_order_id = response.json()['orderId']
            except KeyError:
                return -1

        return response.status_code  # "transactTime"

    def post_swap_order(self):  # Alternative to BUY order with No fees in Binance

        url = f"{BINANCE_API_URL}/sapi/v1/convert/getQuote"
        timestamp = str(int(time.time() * 1000))
        params = {
            'fromAsset': self.trade_from,
            'toAsset': self.trade_to,
            'fromAmount': self.from_amount,
            'walletType': 'SPOT',
            'recvWindow': '5000',
            'timestamp': timestamp,
        }
        headers = {
            'X-MBX-APIKEY': BINANCE_API_KEY
        }
        query_string = '&'.join([f'{key}={params[key]}' for key in params])
        signature = hmac.new(BINANCE_API_SECRET_KEY.encode('utf-8'),
                             query_string.encode('utf-8'),
                             hashlib.sha256).hexdigest()
        query_string += f'&signature={signature}'
        response = requests.post(f'{url}?{query_string}', headers=headers)

        if response.status_code == 200:
            try:
                buy_order_id = response.json()['quoteId']
                print(response.json())
                # accept the Quote
                url = f"{BINANCE_API_URL}/sapi/v1/convert/acceptQuote"
                timestamp = str(int(time.time() * 1000))
                params = {
                    'quoteId': buy_order_id,
                    'recvWindow': '5000',
                    'timestamp': timestamp,
                }
                query_string = '&'.join([f'{key}={params[key]}' for key in params])
                signature = hmac.new(BINANCE_API_SECRET_KEY.encode('utf-8'),
                                     query_string.encode('utf-8'),
                                     hashlib.sha256).hexdigest()
                query_string += f'&signature={signature}'
                response = requests.post(f'{url}?{query_string}', headers=headers)
                self.buy_order_id = response.json()['orderId']
                self.quantity_bought = response.json()['toAmount']
            except KeyError:
                return -1

        return response.status_code

    def post_sell_order(self):

        timestamp = int(time.time() * 1000)
        url = f"{BINANCE_API_URL}/api/v3/order"  # endpoint URL for creating a new order

        print(self.quantity_bought, self.sell_order_price)
        # Build the query string
        query_string = f'symbol={self.trading_pair}&side=SELL&type=LIMIT&timeInForce=GTC&quantity={self.quantity_bought}&price={self.sell_order_price}&timestamp={timestamp}'
        signature = hmac.new(BINANCE_API_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'),
                             hashlib.sha256).hexdigest()
        query_string += f'&signature={signature}'
        headers = {
            'X-MBX-APIKEY': BINANCE_API_KEY,
        }

        # Send to the request URL
        response = requests.post(f'{url}?{query_string}', headers=headers)
        print("backend :: GreedyBroker :: post_sell_order :: response status ", response.status_code)
        print("backend :: GreedyBroker :: post_sell_order :: response body ", response.text)
        """
        response body:
        {"symbol":"ADAUSDT","orderId":10xInt,"orderListId":-1,"clientOrderId":"str",
        "transactTime":timestamp,"price":"0.29260000","origQty":"17.90000000","executedQty":"0.00000000",
        "cummulativeQuoteQty":"0.00000000","status":"NEW","timeInForce":"GTC","type":"LIMIT","side":"SELL",
        "workingTime":timestamp,"fills":[],"selfTradePreventionMode":"NONE"}
        """

        if response.status_code == 200:
            try:
                self.sell_order_id = response.json()['orderId']
            except KeyError:
                return -1

        return response.status_code

    def get_db_fields(self):
        return ["binance", self.datetime, self.trade_from, self.trade_to, self.from_amount, self.quantity_bought, self.buy_order_id, self.sell_order_id, self.order_type, 'Strategy', 'active']
