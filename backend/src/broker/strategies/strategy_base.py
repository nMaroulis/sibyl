import pandas as pd
from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.

    Attributes:
        data (pd.DataFrame): The historical price data.
    """

    def __init__(self) -> None:
        """
        Initializes the trading strategy with market data.

        Vars:
            data (pd.DataFrame): A DataFrame containing price data with a 'close' column.
            name (str): The name of the strategy.
        """
        self.data = None
        self.name = "base"


    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Abstract method to generate trading signals.

        Returns:
            pd.DataFrame: The modified DataFrame including trading signals.
        """
        pass