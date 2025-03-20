from backend.src.broker.strategies.strategy_base import BaseStrategy
import logging
from typing import Any, Dict, List
import time
import threading
import json
import os
import pandas as pd

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

        # Threading
        self.thread = None
        self.thread_id = None
        self.history_file = "./trade_history.json"
        self.pid_file = "./tactician_pid.txt"

        # Data
        self.dataset = None
        # Setup logging
        # logging.basicConfig(filename="trade_log.log", level=logging.INFO)


    def _save_trade_history(self) -> None:
        """Save trade history to a JSON file."""
        with open(self.history_file, "w") as f:
            json.dump(self.trade_history, f, indent=4)


    def _load_trade_history(self):
        """Load trade history from a JSON file if it exists."""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, "r") as f:
                    self.trade_history = json.load(f)
                return self.trade_history
            else:
                return None
        except Exception as e:
            print(e)
            return None

    def _save_pid(self):
        """Save the thread ID (not an actual PID, but useful for tracking)."""
        with open(self.pid_file, "w") as f:
            f.write(str(self.thread_id))


    def _clear_pid(self):
        """Remove the PID file when the strategy stops."""
        if os.path.exists(self.pid_file):
            os.remove(self.pid_file)


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
                self.trade_history.append({"timestamp": time.time(), "action": "BUY", "order_id": order["orderId"], "quote_amount": float(order["executed_quote_amount"]), "price": price, "amount": self.position, "status": "executed"})
                print(f"Tactician :: \033[92m BUY ORDER \033[0m quote:{order["executed_quote_amount"]}, base:{self.position} {self.symbol} at {price:.2f}")
                self._save_trade_history() # save to json
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
                self.trade_history.append({"timestamp": time.time(), "action": "SELL", "price": price, "amount": self.position, "status": "executed"})
                print(f"Tactician :: \033[93m SELL ORDER \033[0m quote: {self.capital} {self.position} {self.symbol} at {price:.2f}")
                self._save_trade_history() # save to json
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


    def initiate_dataset(self, interval: str, limit: int) -> None:
        """
        Calls the Exchange API to get the latest price data. It fetches :limit: prices on call and initiates the dataset.
        Typically called before starting the strategy loop.

        Args:
            limit (int): The number of prices to fetch.
            interval (str): The klines interval.
        """
        # Convert to DataFrame
        data = self.exchange.get_price_history(self.symbol, interval=interval, limit=limit)
        df = pd.DataFrame(data)
        df.rename(columns={"open_time": "timestamp", "close_price": "price"}, inplace=True)
        self.dataset = df


    def update_dataset(self) -> None:
        latest_price = self.exchange.get_pair_market_price(self.symbol)
        current_timestamp_ms = int(time.time() * 1000)
        # drop first row
        self.dataset = self.dataset.iloc[1:].reset_index(drop=True)

        # add new
        self.dataset = pd.concat([self.dataset, pd.DataFrame([{"timestamp": current_timestamp_ms, "price": latest_price}])], ignore_index=True)


    def strategy_loop(self, strategy: BaseStrategy, interval: int = 5, min_capital: float = 0.0, trades_limit: int = 1) -> None:
        """
        Runs the trading strategy in a loop, checking for signals and executing trades.

        Args:
            strategy (TradingStrategy): The strategy that generates trade signals.
            interval (int): Time interval (in seconds) between checking for new signals. Default is 5.
            min_capital (float): The minimum capital threshold for running the strategy. If capital goes below this, the strategy will stop. Default is 0.
            trades_limit (int): Number of trades (one trade is consisted of one BUY then one SELL order) to execute before stopping. Must be even to end with a SELL.
        """
        self.is_running = True
        self.thread_id = threading.get_ident()
        self._save_pid()
        while self.is_running:
            if len(self.get_trade_history()) >= trades_limit*2: # exit after N trades, must be even to end with a sell
                print(f"Maximum number of trades reached {trades_limit}.")
                # self.stop_strategy()
                break

            self.update_dataset()
            signals = strategy.generate_signals(self.dataset.copy())
            latest_signal = signals.iloc[-1]["signal"]
            latest_price = signals.iloc[-1]["price"]
            print(f"Tactician :: signals | t: {pd.to_datetime(signals.iloc[-1]["timestamp"], unit="ms").strftime('%H:%M:%S')}, p: {latest_price:.2f}, action: {latest_signal}") # signals.iloc[-1]["timestamp"].strftime("%H:%M:%S")}
            if latest_signal in ["BUY", "SELL"]:
                self.execute_trade(latest_signal)

            time.sleep(interval)  # Wait before checking again


    def run_strategy(self, strategy: BaseStrategy, interval: int = 5, min_capital: float = 0.0, trades_limit: int = 2) -> None:
        """
        Initiates the trading loop.

        Args:
            strategy (TradingStrategy): The strategy that generates trade signals.
            interval (int): Time interval (in seconds) between checking for new signals. Default is 5.
            min_capital (float): The minimum capital threshold for running the strategy. If capital goes below this, the strategy will stop. Default is 0.
            trades_limit (int): Number of trades to execute before stopping. Must be even to end with a SELL.
        """

        print("Tactician :: Initiating Strategy loop.")
        self.initiate_dataset("1s", 200)
        self.thread = threading.Thread(target=self.strategy_loop, daemon=True, args=(strategy, interval, min_capital, trades_limit))
        self.thread.start()
        print("Tactician :: Strategy loop started.")
        # print(f"Tactician :: {self.get_trade_history()}")


    def stop_strategy(self) -> None:
        """
        Stops the strategy loop. This will stop further execution of trades.

        """
        self.is_running = False
        self._clear_pid()
        if self.thread and self.thread.is_alive():
            self.thread.join()
        print("Tactician :: Strategy has been stopped.")


    def get_position_info(self) -> Dict[str, float]:
        """
        Returns the current position and available capital.

        Returns:
            Dict[str, float]: A dictionary containing the current position and available capital.
        """
        return {"position": self.position, "capital": self.capital}
