import random
from backend.src.exchange_client.exchange_client import ExchangeAPIClient
from typing import Optional, Dict, Any, List, Union
import time
from dotenv import load_dotenv, dotenv_values, set_key
import os


ENV_PATH = "backend/src/exchange_client/mock_status.env"

class MockExchangeClient(ExchangeAPIClient):

    def __init__(self):
        super().__init__()
        self.name = 'mock_exchange'
        self.api_base_url = ""
        load_dotenv(ENV_PATH)


    def check_status(self) -> str:
        status = os.getenv("MOCK_STATUS")
        if status =="true":
            return 'Active'
        else:
            return 'Inactive'


    @staticmethod
    def enable() -> bool:
        try:
            # with open(ENV_PATH, "w") as f:
            #     f.write('MOCK_STATUS="true"\n')
            set_key(ENV_PATH, "MOCK_STATUS", "true")  # alternate way
            os.environ["MOCK_STATUS"] = "true"
            return True
        except Exception as e:
            print(e)
            return False


    @staticmethod
    def disable() -> bool:
        try:
            # with open("mock_status.env", "w") as f:
            #     f.write('MOCK_STATUS="false"\n')
            set_key(ENV_PATH, "MOCK_STATUS", "false")  # alternate way
            os.environ["MOCK_STATUS"] = "false"
            return True
        except Exception as e:
            print(e)
            return False

    def place_spot_order(self, order_type: str, quote_asset: str, base_asset: str, side: str, quantity: float, price: Optional[float] = None, stop_price: Optional[float] = None, take_profit_price: Optional[float] = None, time_in_force: Optional[str] = None) -> Dict[str, Any]:

        if side == 'BUY':
            res = {"symbol": "BTCUSDT",
                   "orderId": 7000000,
                   "orderListId": -1,
                   "clientOrderId": "x-HNA2T5e058151",
                   "transactTime": 1742318968754,
                   "price": "0.00000000",
                   "origQty": "0.00012000",
                   "executedQty": "0.00012000",
                   "origQuoteOrderQty": "10.00000000",
                   "cummulativeQuoteQty": "9.79990560",
                   "status": "FILLED",
                   "timeInForce": "GTC",
                   "type": "MARKET",
                   "side": "BUY",
                   "workingTime": 1742318968754,
                   "fills": [{"price": "81665.88000000", "qty": "0.00012000", "commission": "0.00000000",
                              "commissionAsset": "BTC", "tradeId": 1462374}],
                   "selfTradePreventionMode": "EXPIRE_MAKER"}
        else:
            res = {
                "symbol":"BTCUSDT",
                "orderId":6000000,
                "orderListId":-1,
                "clientOrderId":"x-HNA2TXFJc63ea6c6f",
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
            }
        return {"status": "success", "message": res}


    def place_spot_test_order(self, order_type: str, quote_asset: str, base_asset: str, side: str, quantity: float, price: Optional[float] = None, stop_price: Optional[float] = None, take_profit_price: Optional[float] = None, time_in_force: Optional[str] = None) -> Dict[str, str]:

        return {"status": "success", "message": ""}



    def get_account_information(self) -> Dict[str, Any]:
        res = {
            "maker_commission": 0.1,
            "taker_commission": 0.1,
            "buyer_commission": 0.0,
            "seller_commission": 0.0,
            "can_trade": True,
            "can_deposit": True,
            "can_withdraw": False
        }
        return res


    def get_spot_balance(self, quote_asset_pair_price: str = None) -> Dict[str, Any]:
        """
        Retrieve the user's spot balance, including free and locked amounts, along with current prices.

        Args:
            quote_asset_pair_price (str, optional):
                - calculate the price of each asset in the account according to the quote asset pair.

        Returns:
            Dict[str, Any]: A dictionary containing spot balances, locked earn balances, staked balances, or an error message.
        """
        if quote_asset_pair_price is None:
            prices = [0.0, 0.0, 0.0, 0.0]
        else:
            prices = [82000.0, 2400.0, 0.62, 1.0]
        res = {
            "BTC": {
                "free": 1.24,
                "locked": 0.0,
                "price": prices[0]
            },
            "ETH": {
                "free": 4.6,
                "locked": 4.6,
                "price": prices[1]
            },
            "ADA": {
                "free": 1005.9,
                "locked": 500.0,
                "price": prices[2]
            },
            "USDT": {
                "free": 9300.0,
                "locked": 0.0,
                "price": prices[3]
            }
        }
        return {'spot_balances': res}


    def get_available_assets(self, quote_asset: str = "all") -> Optional[Dict[str, List[str]]]:
        res = {
            "USDT": ["BTC", "ETH", "ADA"],
            "BTC": ["ETH"],
        }
        return res


    def get_klines(self, symbol: str, interval: str, limit: int, start_time: int = None, end_time: int = None) -> Optional[List[Dict[str, float]]]:
        """
        Mock function to generate realistic kline (candlestick) data for testing.

        Args:
            symbol (str): The trading pair symbol (e.g., "ETHUSDT").
            interval (str): The time interval for the candlestick data.
            limit (int): The number of candlestick entries to generate.
            start_time (int, optional): The start timestamp for the data.
            end_time (int, optional): The end timestamp for the data.

        Returns:
            Optional[List[Dict[str, float]]]: A list of dictionaries representing kline data, each with:
                - 'open_time' (int): The open time of the candle.
                - 'open_price' (float): The opening price.
                - 'high' (float): The highest price.
                - 'low' (float): The lowest price.
                - 'close_price' (float): The closing price.
                - 'close_time' (float): The close time.
                - 'volume' (float): The volume of trades.
                - 'trades_num' (float): The number of trades.
        """
        current_time = int(time.time() * 1000)
        time_step = 60000  # default: 1-minute candles

        if start_time is not None:
            start_time = current_time - (limit * time_step)

        price_ranges = {
            "BTCUSDT": (50000, 0.01),  # (starting price, volatility)
            "ETHUSDT": (3000, 0.015),
            "ADAUSDT": (1.0, 0.02),
        }

        base_price, volatility = price_ranges.get(symbol.upper(), (1000, 0.01))

        klines = []
        price = base_price

        for i in range(limit):
            open_time = start_time + (i * time_step)

            # Simulate open -> close with some drift
            drift = random.uniform(-1, 1) * volatility * price
            close_price = round(price + drift, 2)

            high = round(max(price, close_price) + abs(drift) * random.uniform(0.2, 0.5), 2)
            low = round(min(price, close_price) - abs(drift) * random.uniform(0.2, 0.5), 2)

            volume = round(random.uniform(10, 10000), 2)
            trades_num = random.randint(50, 1000)

            klines.append({
                "open_time": open_time,
                "open_price": round(price, 2),
                "high": high,
                "low": low,
                "close_price": close_price,
                "close_time": open_time + time_step,
                "volume": volume,
                "trades_num": trades_num,
            })

            price = close_price  # Set next candle's open to current close

        return klines


    def get_symbol_info(self, symbol: str) -> Dict[str, Any] | None:
        res = {
            "status": "TRADING",
            "order_types": ["LIMIT", "MARKET"],
            "quote_precision": 0.01,
            "base_precision": 0.0001,
            "min_trade_value": 0.001
        }
        return res


    def get_minimum_trade_value(self, symbol: str) -> Optional[Dict[str, Union[float, str]]]:
        pass


    def get_pair_market_price(self, pair_symbol: str) -> float | None:
        if pair_symbol == "BTCUSDT":
            return 82000.0
        elif pair_symbol == "ETHUSDT":
            return 2400.0
        elif pair_symbol == "ADAUSDT":
            return 0.62
        elif pair_symbol == "BTCETH":
            return 37
        else:
            return 1

    def add_spot_order_to_trade_history_db(self, quote_asset: str, base_asset: str, trade_dict: dict) -> bool:
        return False


    def get_orderbook(self, quote_asset: str, base_asset: str, limit: int) ->Optional[List[List[Dict[str, float]]]]:
        """
        Mock function to generate order book data for testing.

        Args:
            quote_asset (str): The quote asset (e.g., "USDT").
            base_asset (str): The base asset (e.g., "ETH").
            limit (int): The number of order book entries to generate.

        Returns:
            Optional[List[List[Dict[str, float]]]]: A list containing two lists (bids and asks), where each entry is a
            dictionary with:
                - 'x' (int): The index position in the order book.
                - 'y' (float): The volume
                - 'price' (float): The order price.
        """
        # Generate mock bid and ask prices around a midpoint
        mid_price = random.uniform(1000, 3000)  # Simulated price range

        bids = [
            {"x": i, "y": round(random.uniform(0.1, 5), 4), "price": round(mid_price - random.uniform(0, 50), 2)}
            for i in range(limit)
        ]

        asks = [
            {"x": i, "y": round(random.uniform(0.1, 5), 4), "price": round(mid_price + random.uniform(0, 50), 2)}
            for i in range(limit)
        ]

        return [bids, asks]
