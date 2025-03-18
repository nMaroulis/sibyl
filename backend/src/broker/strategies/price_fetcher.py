import time
from threading import Thread
import pandas as pd


class PriceFetcher:
    def __init__(self, exchange, symbol: str, update_interval: int = 60):
        """
        Fetch the latest price from the exchange at regular intervals.
        Args:
            exchange: The exchange object (e.g., Binance, Kraken).
            symbol: The trading pair symbol (e.g., 'BTC/USD').
            update_interval: Time in seconds between price fetches.
        """
        self.exchange = exchange
        self.symbol = symbol
        self.update_interval = update_interval
        self.current_price = None
        self.running = False

    def fetch_price(self) -> float:
        """
        Fetch the current price for the given symbol.
        This is a placeholder for your actual exchange API.
        """
        # Replace this with actual exchange API calls to fetch the price
        price = self.exchange.get_symbol_price(self.symbol)
        return price

    def update_price(self, data: pd.DataFrame):
        """
        Fetch and update the current price at regular intervals.
        This method appends the latest price to the dataframe.
        """
        while self.running:
            price = self.fetch_price()
            timestamp = pd.Timestamp.now()
            new_data = pd.DataFrame({"timestamp": [timestamp], "close": [price]})
            data = pd.concat([data, new_data], ignore_index=True)  # Append the new data

            print(f"New data added: {new_data}")
            time.sleep(self.update_interval)

    def start(self, data: pd.DataFrame):
        """
        Start the price updating loop in a separate thread.
        """
        self.running = True
        self.thread = Thread(target=self.update_price, args=(data,))
        self.thread.start()

    def stop(self):
        """
        Stop the price updating loop.
        """
        self.running = False
        self.thread.join()
