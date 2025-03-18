from backend.src.broker.strategies.strategy_base import BaseStrategy
import logging
from typing import Any, Dict, List
import time


class Tactician:
    """
    A class to handle the execution of trades for a given strategy.
    It interfaces with a crypto exchange client to place buy and sell orders, track positions,
    and log trade activity.
    """

    def __init__(self, exchange: Any, symbol: str, capital: float = 1000.0) -> None:
        """
        Initializes the TradeExecutor.

        Args:
            exchange (Any): The exchange object to interact with the crypto exchange.
            symbol (str): The trading symbol (e.g., 'BTC/USD').
            capital (float): The amount of capital available for trading. Default is 1000.
        """
        self.exchange = exchange
        self.symbol = symbol
        self.capital = capital
        self.position = 0  # Tracks how much of the asset we own
        self.trade_history: List[Dict[str, Any]] = []  # Store all trade actions
        self.is_running = False  # Track if the strategy is running

        # Setup logging
        logging.basicConfig(filename="trade_log.log", level=logging.INFO)

    def execute_trade(self, action: str, price: float) -> Dict[str, Any]:
        """
        Executes a trade based on the strategy's signal (BUY/SELL).

        Args:
            action (str): The action to take, either "BUY" or "SELL".
            price (float): The price at which to execute the trade.

        Returns:
            Dict[str, Any]: The response from the exchange API, indicating if the trade was successful.
        """
        if action == "BUY" and self.capital > 0:
            amount = self.capital / price
            order = self.exchange.create_order(symbol=self.symbol, side="BUY", amount=amount, price=price)
            self.position += amount
            self.capital = 0  # Fully invested
            self.trade_history.append({"action": "BUY", "price": price, "amount": amount, "status": "executed"})
            logging.info(f"BUY {amount:.4f} {self.symbol} at {price:.2f}")
            return order

        elif action == "SELL" and self.position > 0:
            order = self.exchange.create_order(symbol=self.symbol, side="SELL", amount=self.position, price=price)
            self.capital = self.position * price  # Convert position back to cash
            self.position = 0
            self.trade_history.append({"action": "SELL", "price": price, "amount": self.position, "status": "executed"})
            logging.info(f"SELL {self.symbol} at {price:.2f}")
            return order

        return {"status": "No action taken"}

    def get_trade_history(self) -> List[Dict[str, Any]]:
        """
        Returns the history of all executed trades (buy/sell actions, price, amount).

        Returns:
            List[Dict[str, Any]]: A list of dictionaries with trade details.
        """
        return self.trade_history

    def get_status(self) -> str:
        """
        Returns the current status of the strategy (active or inactive).

        Returns:
            str: "Running" if the strategy is active, "Stopped" if not.
        """
        return "Running" if self.is_running else "Stopped"


    def run_strategy(self, strategy: BaseStrategy, interval: int = 5, min_capital: float = 0.0) -> None:
        """
        Runs the trading strategy in a loop, checking for signals and executing trades.

        Args:
            strategy (TradingStrategy): The strategy that generates trade signals.
            interval (int): Time interval (in seconds) between checking for new signals. Default is 5.
            min_capital (float): The minimum capital threshold for running the strategy. If capital goes below this, the strategy will stop. Default is 0.
        """
        self.is_running = True  # Set the status to running
        while self.is_running:

            if self.capital < min_capital:
                logging.warning(f"Capital is below {min_capital}. Stopping strategy.")
                self.stop_strategy()
                break  # Stop the strategy if the capital is below the threshold

            data = strategy.generate_signals()
            latest_signal = data.iloc[-1]["signal"]
            latest_price = data.iloc[-1]["close"]

            if latest_signal in ["BUY", "SELL"]:
                self.execute_trade(latest_signal, latest_price)

            time.sleep(interval)  # Wait before checking again
        logging.info("Strategy stopped.")


    def stop_strategy(self) -> None:
        """
        Stops the strategy loop. This will stop further execution of trades.

        """
        self.is_running = False
        logging.info("Strategy has been stopped.")


    def get_position_info(self) -> Dict[str, float]:
        """
        Returns the current position and available capital.

        Returns:
            Dict[str, float]: A dictionary containing the current position and available capital.
        """
        return {"position": self.position, "capital": self.capital}
