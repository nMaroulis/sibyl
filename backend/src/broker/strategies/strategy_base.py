import pandas as pd
from abc import ABC, abstractmethod
from backend.src.broker.strategies.price_fetcher import PriceFetcher

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


    def run_strategy(self, price_fetcher: PriceFetcher, interval: int = 60):
        """
        NOTE: Not required to be implemented by subclasses
        Run the strategy in real-time by fetching prices and generating signals.

        Args:
            price_fetcher (PriceFetcher): The price fetcher instance.
            interval (int): The interval (in seconds) for checking new data.
        """
        price_fetcher.start(self.data)  # Start the price fetching loop

        try:
            while True:
                # Wait for a new price update
                if not self.data.empty:
                    print(f"Data updated: {self.data.tail(1)}")
                    signals = self.generate_signals()
                    print("Generated signals:\n", signals.tail(1))  # Print last signal for example

                time.sleep(interval)
        except KeyboardInterrupt:
            price_fetcher.stop()  # Stop the price fetching loop on interrupt
