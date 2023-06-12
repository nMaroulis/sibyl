from backend.settings import BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
import requests
import hmac, hashlib
import time


class GreedyBroker:

    def __init__(self, datetime=None, trade_from='USDT', trade_to='BTC', from_amount=1.0, strategy='Moderate'):
        self.datetime = datetime
        self.trade_from = trade_from
        self.trade_to = trade_to
        self.trading_pair = trade_to + trade_from
        self.from_amount = from_amount
        self.quantity_bought = 1.0  # populated after the buy order has been completed
        self.sell_order = 1.0  # what price to sell the coin in order to make profit
        self.profit_percentage = 5
        self.strategy = strategy

    def __str__(self):
        return f"{self.datetime},{self.trade_from},{self.trade_to},{self.trading_pair},{self.from_amount},{self.quantity_bought},{self.sell_order},{self.profit_percentage},{self.strategy}"

    def fetch_sell_order_price(
            self):  # Fetches the current price of the coin and returns the price after the x% expected profit, in order to make the sell order

        url = BINANCE_API_URL + '/api/v3/ticker/price' + '?symbol=' + self.trading_pair
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            count_after_decimal = str(float(data['price']))[::-1].find('.')

            sell_order = round(float(data['price']) * (1 + self.profit_percentage / 100), count_after_decimal)
            print(float(data['price']))
            self.sell_order = sell_order
            return response.status_code
        else:
            print('Failed to retrieve current price.')
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
         "workingTime": 1686582543034, "fills": [
            {"price": "0.27920000", "qty": "17.90000000", "commission": "0.00001618", "commissionAsset": "BNB",
             "tradeId": 439694546}], "selfTradePreventionMode": "NONE"}
        """
        print("backend :: GreedyBroker :: post_buy_order :: response status ", response.status_code)
        print("backend :: GreedyBroker :: post_buy_order :: response body ", response.text)
        if response.status_code == 200:
            try:
                self.quantity_bought = response.json()['executedQty']
            except KeyError:
                return -1

        return response.status_code  # "transactTime"

    def send_new_convert_order(self):  # Alternative to BUY order with No fees in Binance

        # API endpoint URLs
        url = BINANCE_API_URL + '/sapi/v1/convert/getQuote'

        # Parameters for the conversion
        amount = self.from_amount  # Amount of USDT to convert
        symbol = self.trade_from  # Trading pair symbol (USDT to ADA)
        symbol_to = self.trade_to  # Trading pair symbol (USDT to ADA)

        # Generate timestamp
        timestamp = str(int(time.time() * 1000))

        # Generate signature
        signature_payload = f'fromAsset={symbol}&amount={amount}&toAsset={symbol_to}&recvWindow=5000&timestamp={timestamp}'
        signature = hmac.new(BINANCE_API_SECRET_KEY.encode('utf-8'), signature_payload.encode('utf-8'),
                             hashlib.sha256).hexdigest()

        # Prepare request parameters
        params = {
            'fromAsset': symbol,
            'toAsset': symbol_to,
            'fromAmount': amount,
            'walletType': 'SPOT',
            'recvWindow': '5000',
            'timestamp': timestamp,
        }
        # Prepare headers
        headers = {
            'X-MBX-APIKEY': BINANCE_API_KEY
        }
        # Send POST request to convert USDT to ADA
        query_string = '&'.join([f'{key}={params[key]}' for key in params])
        query_string += f'&signature={signature}'

        response = requests.post(f'{url}?{query_string}', headers=headers)

        print(response.status_code)
        print(response.text)
        # Process the response
        return response.status_code

    def post_sell_order(self):

        timestamp = int(time.time() * 1000)
        url = f"{BINANCE_API_URL}/api/v3/order"  # endpoint URL for creating a new order
        print(self.quantity_bought, self.sell_order)
        # Build the query string
        query_string = f'symbol={self.trading_pair}&side=SELL&type=LIMIT&timeInForce=GTC&quantity={self.quantity_bought}&price={self.sell_order}&timestamp={timestamp}'
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
        {"symbol":"ADAUSDT","orderId":4008157831,"orderListId":-1,"clientOrderId":"sXaU5jsuEIowtrYMsUVfhO",
        "transactTime":1686583266703,"price":"0.29260000","origQty":"17.90000000","executedQty":"0.00000000",
        "cummulativeQuoteQty":"0.00000000","status":"NEW","timeInForce":"GTC","type":"LIMIT","side":"SELL",
        "workingTime":1686583266703,"fills":[],"selfTradePreventionMode":"NONE"}
        """
        return response.status_code

    def send_buy_order(self):
        # GET CURRENT PRICE AND RETURN PRICE TO SELL FOR % OF PROFIT
        res_status = self.fetch_sell_order_price()
        if res_status != 200:
            return {"error": "Buy order failed :: Retrieving Current Price Failed"}

        # SEND BUY ORDER ON CURRENT PRICE AND GET AMOUNT BOUGHT
        # res_status = self.post_buy_order()
        # if res_status != 200:
        #     return {"error": "Buy order failed :: Buy Order was Unsuccessful"}
        #
        # # SEND BUY ORDER ON CURRENT PRICE
        # res_status = self.post_sell_order()

        # Process the response
        if res_status == 200:
            return {
                "success": f"Successfully bought {self.quantity_bought} {self.trade_to} worth {self.from_amount} {self.trade_from}!"}
        else:  # Error occurred
            # This means that buy order was done successfuly but the limit-sell order failed
            # Sell now what was bought
            return {"error": "Buy order failed - Sell Order was Unsuccessful"}

    def get_fields_for_db(self):
        return ["binance", self.datetime, self.trade_from, self.trade_to, self.from_amount, self.quantity_bought, 'Greedy [Moderate]', 'active']
