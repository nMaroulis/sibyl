from backend.src.exchange_client.exchange_client import ExchangeAPIClient
from database.api_keys_db_client import APIEncryptedDatabase
from binance.client import Client
from binance.exceptions import BinanceAPIException
from binance.enums import ORDER_TYPE_STOP_LOSS, ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET, ORDER_TYPE_STOP_LOSS_LIMIT, \
    ORDER_TYPE_TAKE_PROFIT_LIMIT, ORDER_TYPE_TAKE_PROFIT
from typing import Optional, Dict, Any, List, Union
from database.trade_history_db_client import TradeHistoryDBClient
import requests

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
            order_type (str): The type of order (e.g., Market, Limit, Stop-Loss, etc.).
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

    def fetch_market_price(self, pair: str) -> dict:
        """
        Fetch the current price of a given cryptocurrency trading pair.

        Args:
            pair (str): The trading pair symbol (e.g., 'BTCUSDT').

        Returns:
            dict: A dictionary containing the price or an error message.
        """
        try:
            price = self.client.get_symbol_ticker(symbol=pair)['price']
            return {"price": price}
        except BinanceAPIException as e:
            return {"error": str(e)}


    def get_spot_balance(self) -> dict:
        """
        Retrieve the user's spot balance, including free and locked amounts, along with current prices.

        Returns:
            dict: A dictionary containing spot balances, locked earn balances, staked balances, or an error message.
        """
        if self.client is None:
            return {"error": "Invalid API credentials"}
        try:
            account_info = self.client.get_account()
            spot_balances = {}
            locked_earn_balances, staked_balances = {}, {}

            for asset in account_info['balances']:
                if float(asset['free']) > 0.0 or float(asset['locked']) > 0.0:
                    pair_price = 1.0
                    if asset['asset'] != 'USDT':
                        fetched_price = self.fetch_market_price(asset['asset'] + 'USDT')
                        if "error" not in fetched_price:
                            pair_price = fetched_price['price']

                    balance_data = {
                        'free': float(asset['free']),
                        'locked': float(asset['locked']),
                        'price': pair_price
                    }

                    spot_balances[asset['asset']] = balance_data
                    if asset['asset'].startswith('LD'):
                        locked_earn_balances[asset['asset']] = balance_data
                    if asset['asset'].startswith('ST'):
                        staked_balances[asset['asset']] = balance_data

            return {
                'spot_balances': spot_balances,
                'locked_earn_balances': locked_earn_balances,
                'staked_balances': staked_balances
            }
        except BinanceAPIException as e:
            return {"error": str(e)}


    def get_available_assets(self, quote_asset: str = "all") -> Optional[List[str]]:
        """
        Fetches a list of unique base assets (coins) available for trading on Binance.

        Args:
            quote_asset (str, optional):
                - If `"all"` (default), returns all coins available for trading.
                - If a specific trading quote_asset (e.g., `"USDT"` or `"BTC"`), returns only coins that can be traded with the given quote_asset.

        Returns:
            Optional[List[str]]:
                - A list of unique base assets that match the specified trading quote_asset.
                - Returns None if an error occurs.

        Raises:
            BinanceAPIException: Logs an error message if the Binance API request fails.
        """
        try:
            exchange_info = self.client.get_exchange_info()
            if quote_asset == "all":
                available_coins = [s['baseAsset'] for s in exchange_info['symbols'] if s['status'] == 'TRADING']
            else:
                available_coins = [s['baseAsset'] for s in exchange_info['symbols'] if quote_asset in s['symbol']]
            return list(set(available_coins))
        except BinanceAPIException as e:
            print(f"Binance Exchange Client :: get_available_assets :: {str(e)}")
            return None


    def get_price_history(self, symbol: str, interval: str = "1d", plot_type: str = "line", limit: int = 100) -> Optional[List[Dict[str, float]]]:
        """
        Fetches historical price data for a given symbol from the client.

        Args:
            symbol (str): Trading pair symbol (e.g., "BTCUSDT"). Default is "BTCUSDT".
            interval (str): Time interval for the price data (e.g., "1d", "1h"). Default is "1d".
            plot_type (str): Type of data format to return. "line" returns only open prices,
                            while other values return detailed OHLC data. Default is "line".
            limit (int): Number of historical records to fetch. Default is 100.

        Returns:
            Optional[List[Dict[str, float]]]: A list of dictionaries containing price history data,
                                              or None if an error occurs.
        """
        try:
            klines = self.client.get_klines(symbol=symbol.upper(), interval=interval, limit=limit)

            if plot_type == "line":
                return [{"Open Time": entry[0], "Open Price": float(entry[1])} for entry in klines]
            else:
                return [
                    {
                        "Open Time": entry[0],
                        "Open Price": float(entry[1]),
                        "Highs": float(entry[2]),
                        "Lows": float(entry[3]),
                        "Closing Price": float(entry[4]),
                    }
                    for entry in klines
                ]

        except Exception as e:
            print(f"get_price_history :: Error fetching price history: {e}")
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


    def get_current_asset_price(self, pair_symbol: str) -> float | None:
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