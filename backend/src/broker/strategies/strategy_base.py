import pandas as pd
from abc import ABC, abstractmethod
from backend.src.broker.strategies.price_fetcher import PriceFetcher


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.

    Attributes:
        data (pd.DataFrame): The historical price data.
        price_fetcher (PriceFetcher): fetches latest price data.
    """

    def __init__(self, data: pd.DataFrame, price_fetcher: PriceFetcher) -> None:
        """
        Initializes the trading strategy with market data.

        Args:
            data (pd.DataFrame): A DataFrame containing price data with a 'close' column.
        """
        self.data = data
        self.price_fetcher = price_fetcher

    @abstractmethod
    def generate_signals(self) -> pd.DataFrame:
        """
        Abstract method to generate trading signals.

        Returns:
            pd.DataFrame: The modified DataFrame including trading signals.
        """
        pass

