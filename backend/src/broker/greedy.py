from backend.settings import BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
import requests
import hmac, hashlib
import time
from backend.src.broker.broker import Broker


class GreedyBroker(Broker):

    def __init__(self, datetime=None, trade_from='USDT', trade_to='BTC', from_amount=1.0, order_type='swap'):
        super().__init__(datetime=datetime, trade_from=trade_from, trade_to=trade_to, from_amount=from_amount, order_type=order_type)
        self.strategy = 'Greedya'
        self.sub_strategy = ''

    def send_buy_order(self):
        # GET CURRENT PRICE AND RETURN PRICE TO SELL FOR % OF PROFIT
        res_status = self.fetch_sell_order_price()
        if res_status != 200:
            return {"error": "Buy order failed :: Retrieving Current Price Failed"}

        if self.order_type == 'swap':
            res_status = self.post_swap_order()
            if res_status != 200:
                return {"error": "Buy order failed :: Swap Buy Order was Unsuccessful"}
        else:  # Normal Buy order
            # SEND BUY ORDER ON CURRENT PRICE AND GET AMOUNT BOUGHT
            res_status = self.post_buy_order()
            if res_status != 200:
                return {"error": "Buy order failed :: Trade Buy Order was Unsuccessful"}

        # SEND BUY ORDER ON CURRENT PRICE
        res_status = self.post_sell_order()

        # Process the response
        if res_status == 200:
            return {
                "success": f"Successfully bought {self.quantity_bought} {self.trade_to} worth {self.from_amount} {self.trade_from}!"}
        else:  # Error occurred
            # This means that buy order was done successfuly but the limit-sell order failed
            # Sell now what was bought
            return {"error": "Buy order failed - Sell Order was Unsuccessful"}
