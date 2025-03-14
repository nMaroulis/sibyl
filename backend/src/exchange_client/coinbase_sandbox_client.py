from backend.src.exchange_client.exchange_client import ExchangeAPIClient
from database.api_keys_db_client import APIEncryptedDatabase
import requests, time, hmac, hashlib, base64
from typing import Dict, Any, Optional, Union, List


class CoinbaseSandboxClient(ExchangeAPIClient):

    def __init__(self):
        super().__init__()
        self.name = 'coinbase_sandbox'
        self.api_base_url = 'https://api-public.sandbox.exchange.coinbase.com'
        self.coinbase_base_url = 'https://api.exchange.coinbase.com'
        # Set API Keys
        api_creds = APIEncryptedDatabase.get_api_key_by_name(self.name)
        if api_creds:
            self.api_key = api_creds.api_key
            self.api_secret = api_creds.secret_key
            self.api_passphrase = api_creds.api_metadata # metadata contains the passphrase
        else:
            self.api_key = None


    def check_status(self) -> str:
        """
        Check the status of the client connection.

        Returns:
            str: A status message indicating whether the credentials are valid or not.
                  - 'Empty Credentials' if no client is initialized.
                  - 'Active' if the API credentials are valid.
                  - 'Invalid Credentials' if the API credentials are incorrect or expired.
        """

        if self.api_key is None:
            return 'Empty Credentials'
        try:
            acc = self.get_spot_balance()
            if "error" in acc.keys():
                return 'Invalid Credentials'
            else:
                return 'Active'
        except Exception as e:
            return 'Invalid Credentials'


    def generate_request_headers(self, endpoint: str) -> Dict[str, str]:
        timestamp = str(int(time.time()))

        # Pre-signature string
        message = timestamp + "GET" + endpoint
        hmac_key = base64.b64decode(self.api_secret)
        signature = hmac.new(hmac_key, message.encode(), hashlib.sha256).digest()
        signature_b64 = base64.b64encode(signature).decode()

        # Headers
        headers = {
            "CB-ACCESS-KEY": self.api_key,
            "CB-ACCESS-SIGN": signature_b64,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "CB-ACCESS-PASSPHRASE": self.api_passphrase,
            "Content-Type": "application/json"
        }
        return headers


    def get_spot_balance(self) -> Dict[str, Any]:

        try:
            endpoint = '/accounts'
            headers = self.generate_request_headers(endpoint)
            response = requests.get(self.api_base_url+endpoint, headers=headers)

            if response.status_code == 200:
                accounts = response.json()
                # Keep only non-zero balances
                balances = {}
                for account in accounts:
                    if float(account["balance"]) > 0:
                        pair_price = self.fetch_market_price(f"{account["currency"]}-USDT")
                        print(pair_price)
                        if "error" not in pair_price:
                            pair_price = pair_price['price']
                        else:
                            pair_price = 1.0
                        balances[account["currency"]] = {'free': round(float(account["balance"]), 4), 'locked': 0.0 , 'price': pair_price}

                res_json = {
                    'spot_balances': balances,
                    'locked_earn_balances': {},
                    'staked_balances': {}
                }
                return res_json
            else:
                return {"error": "Coinbase API status code {}".format(response.status_code)}
        except Exception as e:
            return {"error": str(e)}

    def place_spot_order(self, order_type: str, quote_asset: str, base_asset: str, side: str, quantity: float, price: Optional[float] = None, stop_price: Optional[float] = None, take_profit_price: Optional[float] = None, time_in_force: Optional[str] = None) -> Dict[str, Any]:
        """
        Places an order on Exchange based on the given parameters.

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
            Dict[str, Any]: Response from Exchange API.
        """

        pass


    def place_spot_test_order(self, order_type: str, quote_asset: str, base_asset: str, side: str, quantity: float, price: Optional[float] = None, stop_price: Optional[float] = None, take_profit_price: Optional[float] = None, time_in_force: Optional[str] = None) -> Dict[str, str]:
        """
        Same as place_spot_order but to test if the trade is possible.

        Returns:
            Dict with result
                - status: 'success' or 'error'
                - message: Empty '' in case of success, Error message in case of error.
        """
        pass


    def fetch_market_price(self, pair: str) -> Dict[str, Any]:
        """
        Fetch the current price of a given cryptocurrency trading pair.

        Args:
            pair (str): The trading pair symbol (e.g., 'BTCUSDT').

        Returns:
            Dict[str, Any]: A dictionary containing the price or an error message.
        """
        try:
            endpoint = f"/products/{pair}/ticker"
            headers = self.generate_request_headers(endpoint)
            response = requests.get(self.coinbase_base_url + endpoint, headers=headers)

            if response.status_code == 200:
                data = response.json()
                return {"price": data["price"]}
            else:
                return {"error": f"Coinbase API status code {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}


    def get_available_assets(self, quote_asset: str = "all") -> Optional[List[str]]:
        """
        Fetches a list of unique base assets (coins) available for trading on the Exchange.

        Args:
            quote_asset (str, optional):
                - If `"all"` (default), returns all coins available for trading.
                - If a specific trading quote_asset (e.g., `"USDT"` or `"BTC"`), returns only coins that can be traded with the given quote_asset.

        Returns:
            Optional[List[str]]:
                - A list of unique base assets that match the specified trading quote_asset.
                - Returns None if an error occurs.

        Raises:
            Exception: Logs an error message if the API request fails.
        """
        pass


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
        pass


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
        pass


    def get_current_asset_price(self, pair_symbol: str) -> float | None:
        """
        Function to get the current price of an asset in a specific quote currency using Exchange API.

        :param pair_symbol: The trading pair symbol (e.g., 'BTCUSDT', 'ETHUSDT')
        :return: Current price of the asset in the specified quote currency
        """
        pass


    def add_spot_order_to_trade_history_db(self, quote_asset: str, base_asset: str, trade_dict: dict) -> bool:
        """
        Function add the successful spot trade order to the trade history DB using the TradeHistoryDBClient

        Args:
        quote_asset (str)
        base_asset (str)
        trade_dict: contains the information of the trade as returned by the API.
        :return: True if successful else False.
        """
        pass


    def get_orderbook(self, quote_asset: str, base_asset: str, limit: int) ->Optional[List[List[Dict[str, float]]]]:
        """
        Fetches the order book for a given trading pair from Exchange API and formats the data.

        Args:
            quote_asset (str): The quote asset (e.g., "USDT").
            base_asset (str): The base asset (e.g., "ETH").
            limit (int): The number of order book entries to retrieve.

        Returns:
            Optional[List[List[Dict[str, float]]]]: A list containing two lists (bids and asks), where each entry is a
            dictionary with:
                - 'x' (int): The index position in the order book.
                - 'y' (float): The volume.
                - 'price' (float): The order price.
            Returns None if the request fails.
        """
        pass