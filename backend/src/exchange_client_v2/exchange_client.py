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
    def place_spot_order(self, order_type: str, trading_pair: str, side: str, quantity: float, price: Optional[float] = None, stop_price: Optional[float] = None, take_profit_price: Optional[float] = None, time_in_force: Optional[str] = None) -> Dict[str, Any]:
        """
        Places an order on Exchange based on the given parameters.

        Args:
            order_type (str): The type of order (e.g., Market, Limit, Stop-Loss, etc.).
            trading_pair (str): The trading pair (e.g., BTCUSDT).
            side (str): Order side (BUY or SELL).
            quantity (float): Quantity to trade.
            price (Optional[float]): Price for limit orders.
            stop_price (Optional[float]): Stop price for stop-loss or take-profit orders.
            take_profit_price (Optional[float]): Take profit price for take-profit orders.
            time_in_force (Optional[str]): Time in force policy.

        Returns:
            Dict[str, Any]: Response from Exchange API.
        """

        pass


    @abstractmethod
    def place_spot_test_order(self, order_type: str, trading_pair: str, side: str, quantity: float, price: Optional[float] = None, stop_price: Optional[float] = None, take_profit_price: Optional[float] = None, time_in_force: Optional[str] = None) -> Dict[str, str]:
        """
        Same as place_spot_order but to test if the trade is possible.

        Returns:
            Dict with result
                - status: 'success' or 'error'
                - message: Empty '' in case of success, Error message in case of error.
        """
        pass


    @abstractmethod
    def fetch_market_price(self, pair: str) -> dict:
        """
        Fetch the current price of a given cryptocurrency trading pair.

        Args:
            pair (str): The trading pair symbol (e.g., 'BTCUSDT').

        Returns:
            dict: A dictionary containing the price or an error message.
        """
        pass


    @abstractmethod
    def get_spot_balance(self) -> dict:
        """
        Retrieve the user's spot balance, including free and locked amounts, along with current prices.

        Returns:
            dict: A dictionary containing spot balances, locked earn balances, staked balances, or an error message.
        """
        pass

    @abstractmethod
    def get_available_coins(self, quote_asset: str = "all") -> Optional[List[str]]:
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

    @abstractmethod
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
    def get_current_asset_price(self, pair_symbol: str) -> float | None:
        """
        Function to get the current price of an asset in a specific quote currency using Exchange API.

        :param pair_symbol: The trading pair symbol (e.g., 'BTCUSDT', 'ETHUSDT')
        :return: Current price of the asset in the specified quote currency
        """
        pass
