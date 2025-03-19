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

    def __init__(self, exchange: Any, symbol: str, capital_allocation: float = 10.0) -> None:
        """
        Initializes the TradeExecutor.

        Args:
            exchange (Any): The exchange object to interact with the crypto exchange.
            symbol (str): The trading symbol (e.g., 'BTC/USD').
            capital_allocation (float): The amount of capital available for trading. Default is 10.
        """
        self.exchange = exchange
        self.symbol = symbol
        self.capital = capital_allocation
        self.position = 0  # Tracks how much of the asset you own
        self.trade_history: List[Dict[str, Any]] = []  # Store all trade actions
        self.is_running = False  # Track if the strategy is running
        self.last_order_type = "None"
        # Setup logging
        # logging.basicConfig(filename="trade_log.log", level=logging.INFO)


    def execute_trade(self, action: str) -> Dict[str, Any]:
        """
        Executes a trade based on the strategy's signal (BUY/SELL).

        Args:
            action (str): The action to take, either "BUY" or "SELL".

        Returns:
            Dict[str, Any]: The response from the exchange API, indicating if the trade was successful.
        """
        if action == "BUY":
            if self.last_order_type != "BUY" and self.capital > 0:
                self.last_order_type = "BUY"
                order = self.exchange.create_buy_order(symbol=self.symbol, quote_amount=self.capital)
                self.position += float(order["executed_base_quantity"])
                self.capital = self.capital - float(order["executed_quote_amount"])
                price = float(order["price"])
                self.trade_history.append({"action": "BUY", "order_id": order["orderId"], "quote_amount": float(order["executed_quote_amount"]), "price": price, "amount": self.position, "status": "executed"})
                print(f"Tactician :: BUY ORDER quote:{order["executed_quote_amount"]}, base:{self.position} {self.symbol} at {price:.2f}")

                return order
            else:
                print(f"Tactician :: BUY ORDER - NOT ENOUGH CAPITAL {self.capital} or last order was BUY")

        elif action == "SELL":
            if self.last_order_type != "SELL" and self.position > 0:
                self.last_order_type = "SELL"

                order = self.exchange.create_sell_order(symbol=self.symbol, quantity=self.position)
                price = float(order["price"])
                self.capital += float(order["executed_quote_amount"])
                self.position = self.position - float(order["executed_base_quantity"])
                self.trade_history.append({"action": "SELL", "price": price, "amount": self.position, "status": "executed"})
                print(f"Tactician :: SELL ORDER quote: {self.capital} {self.position} {self.symbol} at {price:.2f}")
                return order
            else:
                print(f"Tactician :: SELL ORDER - NOT ENOUGH POSITION {self.position}")

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


    def run_strategy(self, strategy: BaseStrategy, interval: int = 5, min_capital: float = 0.0, trades_limit: int = 2) -> None:
        """
        Runs the trading strategy in a loop, checking for signals and executing trades.

        Args:
            strategy (TradingStrategy): The strategy that generates trade signals.
            interval (int): Time interval (in seconds) between checking for new signals. Default is 5.
            min_capital (float): The minimum capital threshold for running the strategy. If capital goes below this, the strategy will stop. Default is 0.
            trades_num (int): Number of trades to execute before stopping. Must be even to end with a SELL.
        """
        self.is_running = True  # Set the status to running
        while self.is_running:
            if len(self.get_trade_history()) >= trades_limit: # exit after N trades, must be even to end with a sell
                print(f"Capital {self.capital} is below {min_capital}. Stopping strategy.")
                self.stop_strategy()
                break

            data = strategy.generate_signals()
            latest_signal = data.iloc[-1]["signal"]
            latest_price = data.iloc[-1]["close"]
            print(f"Tactician :: data | t: {data.iloc[-1]["timestamp"].strftime("%H:%M:%S")}, p: {latest_price:.2f}, action: {latest_signal}")
            if latest_signal in ["BUY", "SELL"]:
                self.execute_trade(latest_signal)

            time.sleep(interval)  # Wait before checking again
        print("Tactician :: Strategy stopped.")
        print(f"Tactician :: {self.get_trade_history()}")


    def stop_strategy(self) -> None:
        """
        Stops the strategy loop. This will stop further execution of trades.

        """
        self.is_running = False
        print("Tactician :: Strategy has been stopped.")


    def get_position_info(self) -> Dict[str, float]:
        """
        Returns the current position and available capital.

        Returns:
            Dict[str, float]: A dictionary containing the current position and available capital.
        """
        return {"position": self.position, "capital": self.capital}
