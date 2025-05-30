from typing import Dict, Any
from backend.src.exchange_client.exchange_client import ExchangeAPIClient
import pandas as pd
import time
import math


class TacticianExchangeInterface:

    def __init__(self, exchange_client: ExchangeAPIClient):
        self.exchange_client = exchange_client


    def get_market_symbol(self, quote_asset: str, base_asset: str) -> str:
        if self.exchange_client.name in ["binance", "binance_testnet", "kraken"]:
            return f"{base_asset}{quote_asset}"
        else: # Coinbase
            return f"{base_asset}-{quote_asset}"


    def get_kline_data(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        """
        Calls the Exchange API to get the latest price data. It fetches :limit: prices on call and initiates the dataset.
        Typically called before starting the strategy loop.

        In case of 15s interval: Most exchanges do not support a 15s interval. Therefore in order to initiate the dataset, the 1s API is used and the data are sampled.
        Args:
            symbol (str): The crypto pair symbol.
            limit (int): The number of prices to fetch.
            interval (str): The klines interval.
        """
        # There is no 15s interval in exchange APIs, there
        if interval == "15s":

            data = self.exchange_client.get_klines(symbol, interval="1s", limit=1000, start_time=int((time.time() - 3000)*1000))
            data_1 = self.exchange_client.get_klines(symbol, interval="1s", limit=1000, start_time=int((time.time() - 2000)*1000))
            data_2 = self.exchange_client.get_klines(symbol, "1s", limit=1000)

            data.extend(data_1)
            data.extend(data_2)
            df_1sec = pd.DataFrame(data)
            aggregated_data = []
            for i in range(0, df_1sec.shape[0], 15):
                interval_df = df_1sec.iloc[i:i+15]
                aggregated_data.append({
                    "timestamp": interval_df.iloc[0]["open_time"],
                    "open_price": interval_df.iloc[0]["open_price"],
                    "high": interval_df["high"].max(),
                    "low": interval_df["low"].min(),
                    "close_price": interval_df.iloc[-1]["close_price"],
                    "close_time": interval_df.iloc[-1]["close_time"],
                    "volume": interval_df["volume"].sum(),
                    "trades_num": interval_df["trades_num"].sum()
                })
            df = pd.DataFrame(aggregated_data)
        else:
            data = self.exchange_client.get_klines(symbol, interval=interval, limit=limit)
            df = pd.DataFrame(data)
            df.rename(columns={"open_time": "timestamp"}, inplace=True)

        return df


    def get_symbol_trade_info(self, symbol: str) -> Dict[str, Any] | None:

        try:
            res = self.exchange_client.get_symbol_info(symbol)
            # replace float values with int indicating the precision. e.g. 0.001 -> 3
            res["quote_precision"] = int(-math.log10(float(res["quote_precision"])))
            res["base_precision"] = int(-math.log10(float(res["base_precision"])))
        except Exception as e:
            print("TacticianExchangeInterface :: get_symbol_trade_info", e)
            res = None

        return res


    def get_last_market_price(self, symbol: str) -> pd.DataFrame | None:
        """
        Calls the Exchange API to get the latest price ticker.

        Args:
            symbol (str): The crypto pair symbol.
        """
        try:
            latest_price = self.exchange_client.get_pair_market_price(symbol)
            current_timestamp_ms = int(time.time() * 1000)
            return pd.DataFrame([{"timestamp": current_timestamp_ms, "close_price": latest_price}])
        except Exception as e:
            print("TacticianExchangeInterface :: get_last_market_price :: ", e)
            return None


    def get_last_kline(self, symbol: str, interval: str) -> pd.DataFrame | None:
        """
        Calls the Exchange API to get the latest kline.

        Args:
            symbol (str): The crypto pair symbol.
            interval (str): The klines interval.
        """

        if interval == "15s":
            latest_klines = self.exchange_client.get_klines(symbol, interval="1s", limit=15)
            aggregated_df = pd.DataFrame(latest_klines)
            df = pd.DataFrame({
                "timestamp": [aggregated_df.iloc[0]["open_time"]],
                "open_price": [aggregated_df.iloc[0]["open_price"]],
                "high": [aggregated_df["high"].max()],
                "low": [aggregated_df["low"].min()],
                "close_price": [aggregated_df.iloc[-1]["close_price"]],
                "close_time": [aggregated_df.iloc[-1]["close_time"]],
                "volume": [aggregated_df["volume"].sum()],
                "trades_num": [aggregated_df["trades_num"].sum()]
            })
        else:
            latest_kline = self.exchange_client.get_klines(symbol, interval=interval, limit=1)
            if latest_kline is None:
                return None

            df = pd.DataFrame(latest_kline)
            df.rename(columns={"open_time": "timestamp"}, inplace=True)

        return df


    def place_buy_order(self, quote_asset: str, base_asset: str, quote_amount: float) -> Dict[str, Any]:

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
            order_response = self.exchange_client.place_spot_order("market_quote", quote_asset, base_asset, "BUY", quote_amount)
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


    def place_sell_order(self, quote_asset: str, base_asset: str, quantity: float) -> Dict[str, Any]:
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
            order_response = self.exchange_client.place_spot_order("market", quote_asset, base_asset, "SELL", quantity)
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