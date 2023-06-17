from backend.src.broker.broker import Broker


class GreedyBroker(Broker):

    def __init__(self, datetime=None, trade_from='USDT', trade_to='BTC', from_amount=1.0, order_type='swap'):
        super().__init__(datetime=datetime, trade_from=trade_from, trade_to=trade_to, from_amount=from_amount, order_type=order_type)
        self.strategy = 'Greedy'
        self.sub_strategy = ''

    def greedy_algorithm(self):

        count_after_decimal = str(self.current_trade_to_price)[::-1].find('.')
        self.sell_order_price = round(self.current_trade_to_price * (1 + self.profit_percentage / 100), count_after_decimal)
        print('bought at ', self.current_trade_to_price, 'sold at', self.sell_order_price)

    def send_buy_order(self):
        # GET CURRENT PRICE AND RETURN PRICE TO SELL FOR % OF PROFIT
        res_status = self.fetch_sell_order_price()
        if res_status != 200:
            return {"error": "Buy order failed :: Retrieving Current Price Failed"}

        # DEPLOY STRATEGY
        self.greedy_algorithm()

        # SEND BUY ORDER ON CURRENT PRICE
        if self.order_type == 'swap':
            res_status = self.post_swap_order()
            if res_status != 200:
                return {"error": "Buy order failed :: Swap Buy Order was Unsuccessful"}
        else:  # Normal Buy order
            # SEND BUY ORDER ON CURRENT PRICE AND GET AMOUNT BOUGHT
            res_status = self.post_buy_order()
            if res_status != 200:
                return {"error": "Buy order failed :: Trade Buy Order was Unsuccessful"}

        # SELL ORDER
        res_status = self.post_sell_order()

        # Process the response
        if res_status == 200:
            return {
                "success": f"Successfully bought {self.quantity_bought} {self.trade_to} worth {self.from_amount} {self.trade_from}!"}
        else:  # Error occurred
            # This means that buy order was done successfuly but the limit-sell order failed
            # Sell now what was bought
            return {"error": "Buy order failed - Sell Order was Unsuccessful"}

    def get_db_fields(self):  # Override Function
        return ["binance", self.datetime, self.buy_order_id, self.trade_from, self.trade_to, self.from_amount, self.quantity_bought,
                self.current_trade_to_price, self.datetime_sell,
                self.sell_order_id, self.sell_order_price, self.order_type, self.strategy, 'active']
