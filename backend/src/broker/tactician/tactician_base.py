from backend.src.broker.strategies.strategy_base import BaseStrategy
import logging
from typing import Any, Dict, List
import time
import threading
import json
import os
import pandas as pd
from database.strategy.strategy_db_client import StrategyDBClient
from backend.src.broker.tactician.exchange_interface import TacticianExchangeInterface


class Tactician:
    """
    A class to handle the execution of trades for a given strategy.
    It interfaces with a crypto exchange client to place buy and sell orders, track positions,
    and log trade activity.
    """

    def __init__(self, exchange_api: TacticianExchangeInterface, symbol: str, capital_allocation: float) -> None:
        """
        Initializes the TradeExecutor.

        Args:
            exchange_api (TacticianExchangeInterface): The exchange interface object which interacts with the crypto exchange.
            symbol (str): The trading symbol (e.g., 'BTC/USD').
            capital_allocation (float): The amount of capital available for trading. Default is 10.

        :params:
            capital: The amount of quote asset available for trading.
            position: The amount of base asset bought using the quote asset.
            trade_history: After each iteration of the strategy loop, the logs are appended there.
            is_running (bool): Whether the strategy is running.
            last_order
        """
        self.exchange_api = exchange_api
        self.symbol = symbol
        self.capital = capital_allocation
        self.position = 0  # Tracks how much of the asset you own
        self.trade_history: List[Dict[str, Any]] = []  # Store all trade actions
        self.is_running = False  # Track if the strategy is running
        self.last_order_type = "None"
        self.time_interval = None

        self.quote_min_notional = self.exchange_api.get_minimum_trade_value(self.symbol)

        # Threading
        self.thread = None
        self.thread_id = None
        self.history_file = "./trade_history.json"
        self.pid_file = "./tactician_pid.txt"

        # Data
        self.dataset = None
        self.is_price_only = False

        # Setup logging
        # logging.basicConfig(filename="trade_log.log", level=logging.INFO)
        self.db_client = StrategyDBClient()


    def _save_trade_history(self) -> None:
        """
        --Deprecated--
        Save trade history to a JSON file.
        """
        with open(self.history_file, "w") as f:
            json.dump(self.trade_history, f, indent=4)


    def _load_trade_history(self):
        """
        --Deprecated--
        Load trade history from a JSON file if it exists.
        """
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
        """
        --Deprecated--
        Save the thread ID (not an actual PID, but useful for tracking).
        """
        with open(self.pid_file, "w") as f:
            f.write(str(self.thread_id))


    def _clear_pid(self):
        """
        --Deprecated--
        Remove the PID file when the strategy stops.
        """
        if os.path.exists(self.pid_file):
            os.remove(self.pid_file)


    def execute_trade(self, action: str) -> Dict[str, Any] | None:
        """
        Executes a trade based on the strategy's signal (BUY/SELL).

        Args:
            action (str): The action to take, either "BUY" or "SELL".

        Returns:
            Dict[str, Any]: The response from the exchange API, indicating if the trade was successful.
        """

        if action == "BUY":
            if self.last_order_type != "BUY" and self.capital > self.quote_min_notional:
                self.last_order_type = "BUY"
                order = self.exchange_api.place_buy_order(symbol=self.symbol, quote_amount=self.capital)
                if order:
                    self.position += order["position"]
                    self.capital = self.capital - order["executed_quote_amount"]
                    self.trade_history.append({"timestamp": time.time(), "action": "BUY", "order_id": order["order_id"], "quote_amount": float(order["executed_quote_amount"]), "price": order["price"], "amount": self.position, "status": "executed"})
                    print(f"Tactician :: execute_trade :: \033[92m BUY ORDER \033[0m quote:{order["executed_quote_amount"]}, base:{self.position} {self.symbol} at {float(order["price"])}")
                else:
                    print(f"Tactician :: execute_trade :: \033[92m BUY ORDER \033[0m Failed.")
                return order
            else:
                print(f"Tactician :: execute_trade :: \033[92m BUY ORDER \033[0m Invalid")
                return None

        elif action == "SELL":
            if self.last_order_type != "SELL" and self.position > 0:
                self.last_order_type = "SELL"
                order = self.exchange_api.place_sell_order(symbol=self.symbol, quantity=self.position)
                if order:
                    self.capital += float(order["executed_quote_amount"])
                    self.position = self.position - float(order["position"])
                    self.trade_history.append({"timestamp": time.time(), "action": "SELL", "order_id": order["order_id"], "price": float(order["price"]), "amount": self.position, "status": "executed"})
                    print(f"Tactician :: execute_trade :: \033[93m SELL ORDER \033[0m quote: {self.capital} {self.position} {self.symbol} at {order["price"]}")
                else:
                    print(f"Tactician :: execute_trade :: \033[93m SELL ORDER \033[0m Failed.")
                return order
            else:
                print(f"Tactician :: execute_trade :: \033[93m SELL ORDER \033[0m Invalid")
                return None
        return None


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


    def initiate_dataset(self, limit: int) -> None:
        """
        Calls the Exchange API to get the latest price data. It fetches :limit: prices on call and initiates the dataset.
        Typically called before starting the strategy loop.

        Args:
            limit (int): The number of prices to fetch.
        """
        self.dataset = self.exchange_api.get_kline_data(symbol=self.symbol, interval=self.time_interval, limit=limit)


    def update_dataset(self) -> None:
        """
        Updates the dataset with the latest market data.

        - If `is_price_only` is True, fetches only the latest closing price.
        - Otherwise, retrieves the latest OHLCV (Open, High, Low, Close, Volume) data.
        - If fetching fails, it fills in with the last known dataset entry.
        - The dataset is maintained at a fixed size by removing the oldest entry.

        This ensures the strategy always has the most recent data while keeping
        the dataset length consistent.

        Returns:
            None
        """
        if self.is_price_only:  # Only close_price is needed
            last_kline = self.exchange_api.get_last_market_price(self.symbol)
        else:  # OHLCV data is needed
            last_kline = self.exchange_api.get_last_kline(self.symbol, self.time_interval)
        # if it fails it fills with the last value
        if last_kline is None:
            last_kline = self.dataset.iloc[-1]

        self.dataset = self.dataset.iloc[1:].reset_index(drop=True)
        self.dataset = pd.concat([self.dataset, last_kline], ignore_index=True)


    def strategy_loop(self, strategy_id: str, strategy: BaseStrategy, interval: int, min_capital: float, trades_limit: int) -> None:
        """
        Runs the trading strategy in a loop, checking for signals and executing trades.

        Args:
            strategy (TradingStrategy): The strategy that generates trade signals.
            strategy_id (str): The id of the strategy.
            interval (int): Time interval (in seconds) between checking for new signals. Default is 5.
            min_capital (float): The minimum capital threshold for running the strategy. If capital goes below this, the strategy will stop. Default is 0.
            trades_limit (int): Number of trades (one trade is consisted of one BUY then one SELL order) to execute before stopping. Must be even to end with a SELL.
        """

        self.is_running = True
        self.thread_id = threading.get_ident()
        while self.is_running:
            # exit after N trades, must be even to end with a sell
            if len(self.get_trade_history()) >= trades_limit*2:
                print(f"Maximum number of trades reached {trades_limit}.")
                break
            # Fetch latest klines data
            self.update_dataset()
            # Call strategy to get the latest signal (e.g. BUY, SELL, HOLD)
            signals = strategy.generate_signals(self.dataset.copy())
            latest_signal = signals.iloc[-1]["signal"]
            latest_price = signals.iloc[-1]["close_price"]
            timestamp = signals.iloc[-1]["timestamp"]
            print(f"Tactician :: Strategy signals | t: {pd.to_datetime(timestamp, unit="ms").strftime('%H:%M:%S')}, p: {latest_price}, action: {latest_signal}")

            if latest_signal in ["BUY", "SELL"]:
                res = self.execute_trade(latest_signal)
                if res is None: # order failed
                    latest_signal = f"INVALID_{latest_signal}"
            # Add log to the DB
            self.db_client.add_log(strategy_id, int(timestamp), latest_price, latest_signal)
            # Wait before checking again
            time.sleep(interval)


    def run_strategy(self, strategy_id: str, strategy: BaseStrategy, interval: str, min_capital: float, trades_limit: int, dataset_size: int) -> None:
        """
        Initiates the trading loop.

        Args:
            strategy_id (str): The id of the strategy to run.
            strategy (TradingStrategy): The strategy that generates trade signals.
            interval (int): Time interval (in seconds) between checking for new signals. Default is 5.
            min_capital (float): The minimum capital threshold for running the strategy. If capital goes below this, the strategy will stop. Default is 0.
            trades_limit (int): Number of trades to execute before stopping. Must be even to end with a SELL.
            dataset_size (int): The size of the dataset to be fed in the strategy algorithm.
        """
        time_interval_dict = {'1s': 1, '15s': 15, '1m': 60, '5m': 300, '15m': 900,
                         '30m': 1800, '1h': 3600, '4h': 14400, '12h': 43200, '1d': 86400}

        self.time_interval = interval
        self.is_price_only = strategy.is_price_only  # whether the strategy needs only the close price and not OHLCV data
        self.db_client.add_strategy(strategy_id, self.symbol, self.capital, interval, trades_limit, strategy.name, int(time.time()*1000))

        print(f"Tactician :: Initiating Strategy loop with id {strategy_id}.")
        self.initiate_dataset(dataset_size)
        self.thread = threading.Thread(target=self.strategy_loop, daemon=True, args=(strategy_id, strategy, time_interval_dict[interval], min_capital, trades_limit))
        self.thread.start()
        print("Tactician :: Strategy loop started.")


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


#TODO initialize min notionals for buy and sell