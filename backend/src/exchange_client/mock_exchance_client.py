import numpy as np
import time


class MockExchangeClient:


    def get_symbol_price(self, symbol: str) -> float:
        # Simulate getting the latest price of the symbol (e.g., BTC/USD).
        # In a real scenario, you would fetch the price from the exchange's API.
        return np.random.normal(1000, 50)  # Replace with actual dynamic pricing logic.


    def get_klines(self, symbol: str, interval: str = "1d", limit: int = 100, start_time: int = None, end_time: int = None):

        # Generate 100 timestamps, starting from 100 seconds ago
        now = time.time()
        timestamps = [(now - (limit - i)) * 1000 for i in range(limit)]  # Convert to ms

        data = []
        for i in range(limit):
            kline = {
                "open_time": timestamps[i],  # Convert to milliseconds
                "close_price": np.random.uniform(low=980, high=1020)
            }
            data.append(kline)

        return data


    def get_pair_market_price(self, symbol: str) -> float:
        return np.random.uniform(low=980, high=1020)


    def create_buy_order(self, symbol: str, quote_amount: float):

        res = {"symbol":"BTCUSDT",
             "orderId":6839649,
             "orderListId":-1,
             "clientOrderId":"x-HNA2TXFJ7169bd7e34ab875e058151",
             "transactTime":1742318968754,
             "price":"0.00000000",
             "origQty":"0.00012000",
             "executedQty":"0.00012000",
             "origQuoteOrderQty":"10.00000000",
             "cummulativeQuoteQty":"9.79990560",
             "status":"FILLED",
             "timeInForce":"GTC",
             "type":"MARKET",
             "side":"BUY",
             "workingTime":1742318968754,
             "fills":[{"price":"81665.88000000","qty":"0.00012000","commission":"0.00000000","commissionAsset":"BTC","tradeId":1462374}],
             "selfTradePreventionMode":"EXPIRE_MAKER"}

        fills = res["fills"]
        average_price = sum(float(fill["price"]) * float(fill["qty"]) for fill in fills) / sum(float(fill["qty"]) for fill in fills)
        return {"executed_quote_amount": res["cummulativeQuoteQty"], "executed_base_quantity": res["executedQty"], 'price':average_price, 'orderId': res["orderId"], "status": res["status"]}


    def create_sell_order(self, symbol: str, quantity: float):
        # Simulate creating an order with the exchange API.

        res = {"symbol":"BTCUSDT",
            "orderId":6845815,
            "orderListId":-1,
            "clientOrderId":"x-HNA2TXFJ136e565f1196cc63ea6c6f",
            "transactTime":1742319808650,
            "price":"0.00000000",
            "origQty":"0.00012000",
            "executedQty":"0.00012000",
            "origQuoteOrderQty":"10.00000000",
            "cummulativeQuoteQty":"9.80245080",
            "status":"FILLED",
            "timeInForce":"GTC",
            "type":"MARKET",
            "side":"SELL",
            "workingTime":1742319808650,
            "fills":[{"price":"81687.09000000","qty":"0.00012000","commission":"0.00000000","commissionAsset":"USDT","tradeId":1463738}],
            "selfTradePreventionMode":"EXPIRE_MAKER"}

        fills = res["fills"]
        average_price = sum(float(fill["price"]) * float(fill["qty"]) for fill in fills) / sum(float(fill["qty"]) for fill in fills)

        return {"executed_quote_amount": res["cummulativeQuoteQty"], "executed_base_quantity": res["executedQty"], 'price':average_price, 'orderId': res["orderId"], "status": res["status"]}
