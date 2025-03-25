from typing import Dict, Any
from backend.src.exchange_client.exchange_client import ExchangeAPIClient
import pandas as pd
import time


class TacticianExchangeInterface:

    def __init__(self, exchange_client: ExchangeAPIClient):
        self.exchange_client = exchange_client


    def get_kline_data(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        """
        Calls the Exchange API to get the latest price data. It fetches :limit: prices on call and initiates the dataset.
        Typically called before starting the strategy loop.

        In case of 6s interval: Most exchanges do not support a 15s interval. Therefore in order to initiate the dataset, the 1s API is used and the data are sampled.
        Args:
            symbol (str): The crypto pair symbol.
            limit (int): The number of prices to fetch.
            interval (str): The klines interval.
        """
        # There is no 15s interval in exchange APIs, there
        if interval == "6s":
            data = self.exchange_client.get_klines(symbol, interval="1s", limit=1200)
            df = pd.DataFrame(data)
            df.rename(columns={"open_time": "timestamp"}, inplace=True)
            df = df.iloc[::6].reset_index(drop=True)
        else:
            data = self.exchange_client.get_klines(symbol, interval=interval, limit=limit)
            df = pd.DataFrame(data)
            df.rename(columns={"open_time": "timestamp"}, inplace=True)

        return df

    def get_minimum_trade_value(self, symbol: str) -> float:

        try:
            res = self.exchange_client.get_minimum_trade_value(symbol)
        except Exception as e:
            print("TacticianExchangeInterface :: get_minimum_trade_value", e)
            res = None

        if res is None:
            return 0.0
        else:
            min_notional = res["min_trade_value"]
            return min_notional


    def get_last_market_price(self, symbol: str, latest_dataset_price: float) -> Dict[str, Any]:
        """
        Calls the Exchange API to get the latest price ticker.

        Args:
            symbol (str): The crypto pair symbol.
            latest_dataset_price (float): Latest price in the dataset.
        """
        try:
            latest_price = self.exchange_client.get_pair_market_price(symbol)
        except Exception as e:
            print("TacticianExchangeInterface :: get_last_market_price", e)
            latest_price = None

        if latest_price is None:
            latest_price = latest_dataset_price
        current_timestamp_ms = int(time.time() * 1000)
        return {"timestamp": current_timestamp_ms, "close_price": latest_price}


    def get_last_ohlcv_data(self, symbol: str, interval: str) -> Dict[str, Any]:
        """
        Calls the Exchange API to get the latest kline.

        Args:
            symbol (str): The crypto pair symbol.
            latest_dataset_price (float): Latest price in the dataset.
        """
        latest_kline = self.exchange_client.get_price_history(symbol, interval=interval, limit=1)

        return {"timestamp": current_timestamp_ms, "close_price": latest_price}


    def place_buy_order(self, symbol: str, quote_amount: float) -> Dict[str, Any]:

        if self.exchange_client.name in ["binance", "binance_testnet"]:
            """
            Example Response:
                "symbol":"BTCUSDT",
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
                 "selfTradePreventionMode":"EXPIRE_MAKER"
            """
            # exchange API expects quote and base assets as arguments, here the pair is given as quote argument and the base is empty
            order_response = self.exchange_client.place_spot_order("market_quote", symbol, "", "BUY", quote_amount)
            print("TacticianExchangeInterface :: place_buy_order", order_response)
            order = order_response["message"]
            fills = order["fills"]
            average_price = sum(float(fill["price"]) * float(fill["qty"]) for fill in fills) / sum(
                float(fill["qty"]) for fill in fills)

            response_dict = {
                "order_id": order["orderId"],
                "position": float(order["executedQty"]),
                "executed_quote_amount": float(order["cummulativeQuoteQty"]),
                "price": average_price}
        else:
            response_dict = None
        return response_dict


    def place_sell_order(self, symbol: str, quantity: float) -> Dict[str, Any]:
        if self.exchange_client.name in ["binance", "binance_testnet"]:
            """
                Example Response:
                    "symbol":"BTCUSDT",
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
                    "selfTradePreventionMode":"EXPIRE_MAKER"
            """
            # exchange API expects quote and base assets as arguments, here the pair is given as quote argument and the base is empty
            order_response = self.exchange_client.place_spot_order("market", symbol, "", "SELL", quantity)
            print("TacticianExchangeInterface :: place_sell_order", order_response)
            order = order_response["message"]
            fills = order["fills"]
            average_price = sum(float(fill["price"]) * float(fill["qty"]) for fill in fills) / sum(
                float(fill["qty"]) for fill in fills)

            response_dict = {
                "order_id": order["orderId"],
                "position": float(order["executedQty"]),
                "executed_quote_amount": float(order["cummulativeQuoteQty"]),
                "price": average_price,
                "status": order["status"]
            }
        else:
            response_dict = None

        return response_dict