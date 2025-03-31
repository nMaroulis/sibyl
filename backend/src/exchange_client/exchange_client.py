from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Union


class ExchangeAPIClient(ABC):

    def __init__(self):
        self.name: str = ""
        self.api_key: str = ""
        self.api_secret: str = ""
        self.api_base_url: str = ""

    @abstractmethod
    def check_status(self) -> str:
        """
        Check the status of the Binance client connection.

        Returns:
            str: A status message indicating whether the credentials are valid or not.
                  - 'Empty Credentials' if no client is initialized.
                  - 'Active' if the API credentials are valid.
                  - 'Invalid Credentials' if the API credentials are incorrect or expired.
        """
        pass

    @abstractmethod
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


    @abstractmethod
    def place_spot_test_order(self, order_type: str, quote_asset: str, base_asset: str, side: str, quantity: float, price: Optional[float] = None, stop_price: Optional[float] = None, take_profit_price: Optional[float] = None, time_in_force: Optional[str] = None) -> Dict[str, str]:
        """
        Same as place_spot_order but to test if the trade is possible.

        Returns:
            Dict with result
                - status: 'success' or 'error'
                - message: Empty '' in case of success, Error message in case of error.
        """
        pass


    @abstractmethod
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
        pass

    @abstractmethod
    def get_spot_balance(self, quote_asset_pair_price: str = None) -> Dict[str, Any]:
        """
        Retrieve the user's spot balance, including free and locked amounts, along with current prices.

        Args:
            quote_asset_pair_price (str, optional):
                - calculate the price of each asset in the account according to the quote asset pair.
        Returns:
            Dict[str, Any]: A dictionary containing spot balances, locked earn balances, staked balances, or an error message.
        """
        pass

    @abstractmethod
    def get_available_assets(self, quote_asset: str = "all") -> Optional[Dict[str, List[str]]]:
        """
        Fetches available trading pairs from Exchange and groups them by quote asset.

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
            Exception: Logs an error message if the Exchange API request fails.
        """
        pass

    @abstractmethod
    def get_klines(self, symbol: str, interval: str, limit: int, start_time: int = None, end_time: int = None) -> Optional[List[Dict[str, float]]]:
        """
        Fetches historical OHLCV data for a given symbol from the client.

        Args:
            symbol (str): Trading pair symbol (e.g., "BTCUSDT").
            interval (str): Time interval for the price data (e.g., "1d", "1h").
            limit (int): Number of historical records to fetch.
            start_time (Optional[int]): Start time of historical records. Default is None.
            end_time (Optional[int]): End time of historical records. Default is None.

        Returns:
            Optional[List[Dict[str, float]]]: A list of dictionaries containing price history data,
                                              or None if an error occurs.
        """
        pass


    @abstractmethod
    def get_symbol_info(self, symbol: str) -> Dict[str, Any] | None:
        """
        Retrieves information about a specific symbol pair.

        Args:
            symbol (str): The symbol pair to fetch.

        Returns:
            Dict[str, Any]: A dictionary containing information about the symbol.
        """
        pass


    @abstractmethod
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


    @abstractmethod
    def get_pair_market_price(self, pair_symbol: str) -> float | None:
        """
        Function to get the current price of an asset in a specific quote currency using Exchange API.

        :param pair_symbol: The trading pair symbol (e.g., 'BTCUSDT', 'ETHUSDT')
        :return: Current price of the asset in the specified quote currency
        """
        pass


    @abstractmethod
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

    @abstractmethod
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