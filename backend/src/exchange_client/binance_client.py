from backend.src.exchange_client.exchange_client import ExchangeAPIClient
from database.api_keys_db_client import APIEncryptedDatabase
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from binance.enums import ORDER_TYPE_STOP_LOSS, ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET, ORDER_TYPE_STOP_LOSS_LIMIT, \
    ORDER_TYPE_TAKE_PROFIT_LIMIT, ORDER_TYPE_TAKE_PROFIT
from typing import Optional, Dict, Any, List, Union
from database.trade_history_db_client import TradeHistoryDBClient
import requests
import bisect


class BinanceClient(ExchangeAPIClient):

    def __init__(self):
        super().__init__()
        self.name = 'binance'
        self.api_base_url = 'https://api.binance.com'  # api[1-4]
        api_creds = APIEncryptedDatabase.get_api_key_by_name(self.name)
        if api_creds is None:
            self.client = None
        else:
            self.client = Client(api_creds.api_key, api_creds.secret_key)

    def check_status(self) -> str:
        """
        Check the status of the Binance client connection.

        Returns:
            str: A status message indicating whether the credentials are valid or not.
                  - 'Empty Credentials' if no client is initialized.
                  - 'Active' if the API credentials are valid.
                  - 'Invalid Credentials' if the API credentials are incorrect or expired.
        """

        if self.client is None:
            return 'Empty Credentials'
        try:
            self.client.get_account()
            return 'Active'
        except BinanceAPIException:
            return 'Invalid Credentials'


    def place_spot_order(self, order_type: str, quote_asset: str, base_asset: str, side: str, quantity: float, price: Optional[float] = None, stop_price: Optional[float] = None, take_profit_price: Optional[float] = None, time_in_force: Optional[str] = None) -> Dict[str, Any]:
        """
        Places an order on Binance based on the given parameters.

        Args:
            order_type (str): The type of order (e.g., market, market_quote, limit, stop-loss, etc.).
            quote_asset (str): The quote asset.
            base_asset (str): The base asset.
            side (str): Order side (BUY or SELL).
            quantity (float): Quantity to trade.
            price (Optional[float]): Price for limit orders.
            stop_price (Optional[float]): Stop price for stop-loss or take-profit orders.
            take_profit_price (Optional[float]): Take profit price for take-profit orders.
            time_in_force (Optional[str]): Time in force policy.

        trading_pair (str): The trading pair to use, e.g. quote_asset: USDT, base_asset: BTC -> BTCUSDT

        Returns:
            Dict[str, Any]: Response from Binance API.

            E.g. Binance API response: {'symbol': 'ATOMUSDT', 'orderId': 400900, 'orderListId': -1,
            'clientOrderId': '...', 'transactTime': 1741634468553,
            'price': '0.00000000', 'origQty': '11.00000000', 'executedQty': '11.00000000',
            'origQuoteOrderQty': '0.00000000', 'cummulativeQuoteQty': '40.85400000',
            'status': 'FILLED', 'timeInForce': 'GTC', 'type': 'MARKET', 'side': 'BUY',
            'workingTime': 1741634468553, 'fills': [{'price': '3.71400000',
            'qty': '11.00000000', 'commission': '0.00000000',
            'commissionAsset': 'ATOM', 'tradeId': 31700}], 'selfTradePreventionMode': 'EXPIRE_MAKER'}
        """
        try:
            trading_pair = f"{base_asset}{quote_asset}"
            if order_type == "market":
                res = self.client.order_market(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_MARKET,
                    quantity=quantity
                )
            elif order_type == "market_quote":
                res = self.client.order_market(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_MARKET,
                    quoteOrderQty=quantity # this quantity specifies the amount of quote asset to be spent for this transaction. e.g. for BTCUSDT buy 10 USDT worth of BTC
                )
            elif order_type == "limit":
                res = self.client.order_limit(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_LIMIT,
                    quantity=quantity,
                    price=price,
                    timeInForce=time_in_force
                )
            elif order_type == "stop-Loss":
                res = self.client.create_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_STOP_LOSS,
                    quantity=quantity,
                    stopPrice=stop_price
                )
            elif order_type == "stop-loss limit":
                res = self.client.create_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_STOP_LOSS_LIMIT,
                    quantity=quantity,
                    price=price,
                    stopPrice=stop_price,
                    timeInForce=time_in_force
                )
            elif order_type == "take-profit":
                res = self.client.create_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_TAKE_PROFIT,
                    quantity=quantity,
                    stopPrice=take_profit_price
                )
            elif order_type == "take-profit limit":
                res = self.client.create_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_TAKE_PROFIT_LIMIT,
                    quantity=quantity,
                    price=price,
                    stopPrice=take_profit_price,
                    timeInForce=time_in_force
                )
            elif order_type == "oco":
                res = self.client.create_oco_order(
                    symbol=trading_pair,
                    side=side,
                    quantity=quantity,
                    price=price,
                    stopPrice=stop_price
                )
            else:
                raise ValueError("Invalid order type")

            return {"status": "success", "message": res}
        except BinanceAPIException as e:
            return {"status": "error", "message": str(e)}
        except Exception as e:
            return {"status": "error", "message": str(e)}


    def place_spot_test_order(self, order_type: str, quote_asset: str, base_asset: str, side: str, quantity: float, price: Optional[float] = None, stop_price: Optional[float] = None, take_profit_price: Optional[float] = None, time_in_force: Optional[str] = None) -> Dict[str, str]:
        """
        Same as place_spot_order but to test if the trade is possible.

        Returns:
            Dict with result
                - status: 'success' or 'error'
                - message: Empty '' in case of success, Error message in case of error.
        """
        try:
            trading_pair = f"{base_asset}{quote_asset}"
            if order_type == "market":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_MARKET,
                    quantity=quantity
                )
            elif order_type == "market_quote":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_MARKET,
                    quoteOrderQty=quantity
                )
            elif order_type == "limit":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_LIMIT,
                    quantity=quantity,
                    price=price,
                    timeInForce=time_in_force
                )
            elif order_type == "stop-Loss":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_STOP_LOSS,
                    quantity=quantity,
                    stopPrice=stop_price
                )
            elif order_type == "stop-loss limit":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_STOP_LOSS_LIMIT,
                    quantity=quantity,
                    price=price,
                    stopPrice=stop_price,
                    timeInForce=time_in_force
                )
            elif order_type == "take-profit":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_TAKE_PROFIT,
                    quantity=quantity,
                    stopPrice=take_profit_price
                )
            elif order_type == "take-profit limit":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_TAKE_PROFIT_LIMIT,
                    quantity=quantity,
                    price=price,
                    stopPrice=take_profit_price,
                    timeInForce=time_in_force
                )
            elif order_type == "oco":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    quantity=quantity,
                    price=price,
                    stopPrice=stop_price
                )
            else:
                return {"status": "error", "message": "Invalid order type"}
            if res == {}: # SUCCESS
                return {"status": "success", "message": ""}
            else:
                return {"status": "error", "message": res}
        except Exception as e:
            return {"status": "error", "message": str(e)}


    def get_account_information(self) -> Dict[str, Any]:
        """
        Fetches the account information from the exchange, including the commission rates
        (maker, taker, buyer, and seller) and the account's ability to perform trading,
        depositing, and withdrawing operations.

        The function is designed to work with various exchanges, and it returns a dictionary
        with the relevant data or an error message in case of failure.

        **Response Dictionary:**
        - "maker_commission" (int): The maker commission rate in basis points (BPS).
        - "taker_commission" (int): The taker commission rate in basis points (BPS).
        - "buyer_commission" (int): The commission rate applied when buying in basis points (BPS).
        - "seller_commission" (int): The commission rate applied when selling in basis points (BPS).
        - "can_trade" (bool): True if the account can trade.
        - "can_deposit" (bool): True if the account can deposit funds.
        - "can_withdraw" (bool): True if the account can withdraw funds.

        **Exceptions:**
        - `ExchangeRequestException`: Raised if there is an issue with the API request.
        - `ExchangeAPIException`: Raised if the API returns an error or unexpected response.

        **Returns:**
        - A dictionary with the account information or an error message.
        """

        try:
            account_info = self.client.get_account()
            return {"maker_commission": account_info["makerCommission"]/100, "taker_commission": account_info["takerCommission"]/100,
                    "buyer_commission": account_info["buyerCommission"]/100, "seller_commission": account_info["sellerCommission"]/100, "can_trade": account_info["canTrade"], "can_deposit": account_info["canDeposit"], "can_withdraw": account_info["canWithdraw"]}
        except BinanceRequestException as e:
            return {"error": str(e)}
        except BinanceAPIException as e:
            return {"error": str(e)}


    def get_spot_balance(self, quote_asset_pair_price: str = None) -> Dict[str, Any]:
        """
        Retrieve the user's spot balance, including free and locked amounts, along with current prices.

        Args:
            quote_asset_pair_price (str, optional):
                - calculate the price of each asset in the account according to the quote asset pair.

        Returns:
            Dict[str, Any]: A dictionary containing spot balances, locked earn balances, staked balances, or an error message.
        """
        if self.client is None:
            return {"error": "Invalid API credentials"}
        try:
            account_info = self.client.get_asset_balance()
            spot_balances = {}

            for asset in account_info:
                if float(asset['free']) > 0.0 or float(asset['locked']) > 0.0:

                    # IN CASE OF LOCKED ASSET, in Binance it is denoted as LD+Asset_name
                    if asset['asset'].startswith('LD'):  # or asset['asset'].startswith('ST'): # TODO Examine staked balance

                        price = self.get_pair_market_price(f"{asset['asset'][2:]}{quote_asset_pair_price}") if quote_asset_pair_price else 0.0
                        if price is None: price = 0.0
                        balance_data = {
                            'free': 0.0,
                            'locked': float(asset['free']),
                            'price': price
                        }
                        if asset['asset'][2:] in spot_balances.keys():
                            spot_balances[asset['asset'][2:]]['locked'] += balance_data['locked']
                        else:
                            spot_balances[asset['asset'][2:]] = balance_data
                    else:
                        price = self.get_pair_market_price(f"{asset['asset']}{quote_asset_pair_price}") if quote_asset_pair_price else 0.0
                        if price is None: price = 0.0
                        balance_data = {
                            'free': float(asset['free']),
                            'locked': float(asset['locked']),
                            'price': price
                        }
                        if asset['asset'] in spot_balances.keys():
                            spot_balances[asset['asset']]['free'] += balance_data['free']
                        else:
                            spot_balances[asset['asset']] = balance_data
            return {
                'spot_balances': spot_balances,
            }
        except BinanceAPIException as e:
            return {"error": str(e)}


    def get_available_assets(self, quote_asset: str = "all") -> Optional[Dict[str, List[str]]]:
        """
        Fetches available trading pairs from Binance and groups them by quote asset.

        Args:
            quote_asset (str, optional):
                - If `"all"` (default), returns all quote assets with their corresponding base assets.
                - If a specific quote asset is provided (e.g., `"USDT"` or `"BTC"`), returns only the base assets for that quote asset.

        Returns:
            Optional[Dict[str, List[str]]]:
                - A dictionary where keys are quote assets and values are lists of base assets.
                - If a specific quote asset is provided, returns a dictionary with only that quote asset.
                - Returns None if an error occurs.

        Raises:
            BinanceAPIException: Logs an error message if the Binance API request fails.
        """
        try:
            exchange_info = self.client.get_exchange_info()
            # Dictionary to store quote assets and their corresponding base assets
            assets_by_quote: Dict[str, List[str]] = {}

            for symbol in exchange_info["symbols"]:
                if symbol["status"] == "TRADING":  # Only include actively trading pairs
                    base_currency = symbol["baseAsset"]
                    quote_currency = symbol["quoteAsset"]

                    if quote_currency not in assets_by_quote:
                        assets_by_quote[quote_currency] = []

                    bisect.insort(assets_by_quote[quote_currency], base_currency) # insert in alphabetical order

            # Apply filtering if a specific quote_asset is requested
            if quote_asset != "all":
                return {quote_asset: assets_by_quote.get(quote_asset, [])}

            return assets_by_quote  # Return full dictionary if "all" is requested

        except BinanceAPIException as e:
            print(f"Binance Exchange Client :: get_available_assets :: {str(e)}")
            return None


    def get_klines(self, symbol: str, interval: str, limit: int, start_time: int = None, end_time: int = None) -> Optional[List[Dict[str, float]]]:
        """
        Fetches historical OHLCV data for a given symbol from the client.

        Args:
            symbol (str): Trading pair symbol (e.g., "BTCUSDT").
            interval (str): Time interval for the price data (e.g., "1d", "1h").
            limit (int): Number of historical records to fetch.
            start_time (Optional[int]): Start time of historical records. Default is None.
            end_time (Optional[int]): End time of historical records. Default is None.

        :binance client get_klines response:
            {    1499040000000,  # Open time
                "0.01634790",  # Open
                "0.80000000",  # High
                "0.01575800",  # Low
                "0.01577100",  # Close
                "148976.11427815",  # Volume
                1499644799999,  # Close time
                "2434.19055334",  # Quote asset volume
                308,  # Number of trades
                "1756.87402397",  # Taker buy base asset volume
                "28.46694368",  # Taker buy quote asset volume
                "17928899.62484339"  # Can be ignored
            }

        Returns:
            Optional[List[Dict[str, float]]]: A list of dictionaries containing price history data,
                                              or None if an error occurs.
        """
        try:
            if start_time:
                klines = self.client.get_klines(symbol=symbol.upper(), interval=interval, limit=limit, startTime=start_time)
            else:
                klines = self.client.get_klines(symbol=symbol.upper(), interval=interval, limit=limit)
            return [
                {
                    "open_time": entry[0],
                    "open_price": float(entry[1]),
                    "high": float(entry[2]),
                    "low": float(entry[3]),
                    "close_price": float(entry[4]),
                    "close_time": float(entry[6]),
                    "volume": float(entry[5]),
                    "trades_num": float(entry[8]),
                }
                for entry in klines
            ]
        except Exception as e:
            print(f"get_klines :: Error fetching price history: {e}")
            return None


    def get_minimum_trade_value(self, symbol: str) -> Optional[Dict[str, Union[float, str]]]:
        """
        Retrieves the minimum trade value required for a given trading pair.

        This function queries the exchange for the minimum allowable trade value,
        typically defined in the quote currency. The implementation varies
        depending on the exchange API.

        Args:
            symbol (str): Trading pair symbol (e.g., "BTCUSDT").

        Returns:
            Dict[str, Union[float, str]] | None:
                - {'min_trade_value': float} if successful.
                - None if no minimum trade value is found.
                - None if an exception occurs.
        """
        try:
            exchange_info = self.client.get_symbol_info(symbol.upper())
            if not exchange_info:
                return {"error": f"Symbol {symbol} not found"}

            for filter_item in exchange_info.get("filters", []):
                if filter_item.get("filterType") == "NOTIONAL":
                    return {"min_trade_value": float(filter_item.get("minNotional", -1))}
            return None
        except BinanceAPIException as e:
            print(f"Binance API error: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None


    def get_pair_market_price(self, pair_symbol: str) -> float | None:
        """
        Function to get the current price of an asset in a specific quote currency using Binance API.

        :param pair_symbol: The trading pair symbol (e.g., 'BTCUSDT', 'ETHUSDT')
        :return: Current price of the asset in the specified quote currency
        """
        pair_symbol = pair_symbol.upper()
        try:
            # Get the current price for the symbol
            ticker = self.client.get_symbol_ticker(symbol=pair_symbol)
            if ticker:
                return float(ticker['price'])
            else:
                print(f"Error: No data found for symbol {pair_symbol}")
                return None
        except Exception as e:
            print(f"Error: {e}")
            return None


    def add_spot_order_to_trade_history_db(self, quote_asset: str, base_asset: str, trade_dict: dict) -> bool:
        """
        Function add the successful spot trade order to the trade history DB using the TradeHistoryDBClient

        Args:
        quote_asset (str)
        base_asset (str)
        trade_dict: contains the information of the trade as returned by the API.
        :return: True if successful else False.
        """
        try:
            TradeHistoryDBClient.add_trade_to_db(self.name, trade_dict["transactTime"], str(trade_dict["orderId"]),
                                                 quote_asset, base_asset, trade_dict["executedQty"],
                                                 trade_dict["cummulativeQuoteQty"], trade_dict["side"], trade_dict["type"],
                                                 trade_dict["status"], trade_dict["timeInForce"], None, None, trade_dict["selfTradePreventionMode"])
            return True
        except Exception as e:
            print(f"Error: {e}")
            return False


    def get_orderbook(self, quote_asset: str, base_asset: str, limit: int) ->Optional[List[List[Dict[str, float]]]]:
        """
        Fetches the order book for a given trading pair from Binance and formats the data.

        Args:
            quote_asset (str): The quote asset (e.g., "USDT").
            base_asset (str): The base asset (e.g., "ETH").
            limit (int): The number of order book entries to retrieve.

        Returns:
            Optional[List[List[Dict[str, float]]]]: A list containing two lists (bids and asks), where each entry is a
            dictionary with:
                - 'x' (int): The index position in the order book.
                - 'y' (float): The volume
                - 'price' (float): The order price.
            Returns None if the request fails.
        """
        # static implementation
        pair_symbol = f"{base_asset}{quote_asset}"
        binance_orderbook_url = "https://api.binance.com/api/v3/depth"
        response = requests.get(binance_orderbook_url, params={"symbol": pair_symbol, "limit": limit})
        if response.status_code == 200:
            order_book = response.json()
            bids = order_book["bids"]
            asks = order_book["asks"]

            # Format bids and asks into the required structure
            formatted_bids = [
                {"x": i, "y": float(bid[1]), "price": float(bid[0])}
                for i, bid in enumerate(bids)
            ]
            formatted_asks = [
                {"x": i, "y": float(ask[1]), "price": float(ask[0])}
                for i, ask in enumerate(asks)
            ]

            return [formatted_bids, formatted_asks]

        else:
            print("BinanceClient :: Failed to fetch order book data.")
            return None


# check_token_swap_status()
# get_spot_trade_order_status