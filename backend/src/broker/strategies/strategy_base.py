import pandas as pd
from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.

    Attributes:
        data (pd.DataFrame): The historical price data.
    """

    def __init__(self, data: pd.DataFrame) -> None:
        """
        Initializes the trading strategy with market data.

        Args:
            data (pd.DataFrame): A DataFrame containing price data with a 'close' column.
        """
        self.data = data


    @abstractmethod
    def generate_signals(self) -> pd.DataFrame:
        """
        Abstract method to generate trading signals.

        Returns:
            pd.DataFrame: The modified DataFrame including trading signals.
        """
        pass
