from backend.src.broker.broker import Broker
from backend.src.exchange_client.exchange_client import ExchangeAPIClient


class GreedyBroker(Broker):

    def __init__(self, exchange_client: ExchangeAPIClient, datetime: str, trade_from: str, trade_to: str, from_amount: float, order_type: str, strategy_params: dict):
        super().__init__(exchange_client=exchange_client, datetime=datetime, trade_from=trade_from, trade_to=trade_to, from_amount=from_amount, order_type=order_type, strategy_params=strategy_params)
        self.strategy = 'Greedy'

    def init_trading_algorithm(self) -> dict:
        try:
            self.current_trade_to_price = float(self.exchange_client.get_crypto_pair_price(f"{self.trade_to}{self.trade_from}")["price"])
            count_after_decimal = str(self.current_trade_to_price)[::-1].find('.')
            if self.strategy_params['type'] == "profit_percentage":
                self.sell_order_price = round(self.current_trade_to_price * (1 + (self.strategy_params['value'] / 100)), count_after_decimal)
                print(f"GreedyBroker :: buying price {self.current_trade_to_price}, selling price {self.sell_order_price}")
            elif self.strategy_params['type'] == "profit_value":
                self.sell_order_price = round(self.current_trade_to_price * self.strategy_params['value'], count_after_decimal)
                print(f"GreedyBroker :: buying price {self.current_trade_to_price}, selling price {self.sell_order_price}")
            elif self.strategy_params['type'] == "auto":
                auto_greedy_dict ={
                    'Very Low': 1.0,
                    'Low': 2.5,
                    'Moderate': 4.5,
                    'High': 10.0,
                    'Extreme': 20.0
                }
                self.sell_order_price = round(self.current_trade_to_price * (1 + (auto_greedy_dict[self.strategy_params['value']] / 100)), count_after_decimal)
                print(f"GreedyBroker :: buying price {self.current_trade_to_price}, selling price {self.sell_order_price}")
            else:
                return {"error": "Trading Algorithm type not found"}
            res = self.send_buy_and_sell_order()
            return res
        except Exception as e:
            return {"error": str(e)}

    def send_buy_and_sell_order(self):

        # SEND BUY ORDER ON CURRENT PRICE
        if self.order_type == 'swap':
            res_status = self.exchange_client.post_swap_order(self.trade_from, self.trade_to, self.from_amount)
            if res_status != 200:
                return {"error": "Buy order failed :: Swap Buy Order was Unsuccessful"}
        else:  # Normal Buy order
            # SEND BUY ORDER ON CURRENT PRICE AND GET AMOUNT BOUGHT
            self.quantity_bought, self.buy_order_id, self.buy_datetime = self.exchange_client.post_buy_order(self.trade_from, self.trade_to, self.from_amount)
            # if res_status != 200:
            #     return {"error": "Buy order failed :: Trade Buy Order was Unsuccessful"}

        # SELL ORDER
        self.sell_order_id = self.exchange_client.post_sell_order(self.trade_to, self.trade_from, self.quantity_bought, self.sell_order_price)

        # Process the response
        if self.sell_order_id is not None:
            return {
                "success": f"Successfully bought {self.quantity_bought} {self.trade_to} worth {self.from_amount} {self.trade_from}!"}
        else:  # Error occurred
            # This means that buy order was done successfully but the limit-sell order failed
            # Sell now what was bought
            return {"error": "Buy order failed - Sell Order was Unsuccessful"}

    def get_db_fields(self):  # Override Function
        return [self.exchange_client.name, self.datetime, self.buy_order_id, self.trade_from, self.trade_to, self.from_amount, self.quantity_bought,
                self.current_trade_to_price, self.datetime_sell,
                self.sell_order_id, self.sell_order_price, self.order_type, self.strategy, 'active']
