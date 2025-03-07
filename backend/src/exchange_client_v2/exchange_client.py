from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


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
    def place_spot_test_order(self, order_type: str, trading_pair: str, side: str, quantity: float, price: Optional[float] = None, stop_price: Optional[float] = None, take_profit_price: Optional[float] = None, time_in_force: Optional[str] = None) -> bool:
        """
        Same as place_spot_order but to test if the trade is possible.

        Returns:
            True if trade is possible, False if not.
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