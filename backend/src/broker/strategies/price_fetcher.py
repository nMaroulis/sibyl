import time
from threading import Thread, Lock
import pandas as pd
from typing import Any


class PriceFetcher:
    def __init__(self, exchange: Any, symbol: str, update_interval: int = 60, data: pd.DataFrame = None):
        """
        Fetch the latest price from the exchange at regular intervals.
        Args:
            exchange: The exchange object (e.g., Binance, Kraken).
            symbol: The trading pair symbol (e.g., 'BTC/USD').
            update_interval: Time in seconds between price fetches.
            data: The DataFrame that holds the price data for strategy.
        """
        self.exchange = exchange
        self.symbol = symbol
        self.update_interval = update_interval
        self.data = data if data is not None else pd.DataFrame(columns=["timestamp", "close"])
        self.running = False
        self.lock = Lock()
        self.thread = None


    def fetch_price(self) -> float:
        """
        Fetch the current price for the given symbol.
        """
        price = self.exchange.get_symbol_price(self.symbol)  # Simulate fetching price from exchange
        return price


    def update_price(self):
        """
        Fetch and update the current price at regular intervals.
        This method appends the latest price to the dataframe.
        """
        while self.running:
            price = self.fetch_price()
            timestamp = pd.Timestamp.now().floor("s")
            new_data = pd.DataFrame({"timestamp": [timestamp], "close": [price]})
            self.data = pd.concat([self.data[1:], new_data], ignore_index=True) # remove first, append new
            print(f"PriceFetcher :: fetched data | t: {new_data["timestamp"].iloc[0].strftime("%H:%M:%S")}, p: {new_data['close'].iloc[0]:.2f} {self.data.shape}")
            # print(self.data[0:1]["timestamp"], self.data[-2:-1]["timestamp"])
            time.sleep(self.update_interval)

    def start(self):
        """
        Start the price fetching loop in a separate thread.
        """
        self.running = True
        self.thread = Thread(target=self.update_price, daemon=True)
        self.thread.start()
        print(f"PriceFetcher :: thread started")

    def stop(self):
        """
        Stop the price fetching loop.
        """
        self.running = False
        if self.thread:
            self.thread.join()
        print(f"PriceFetcher :: thread stopped")

    def get_data(self):
        return self.data.copy()