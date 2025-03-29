from tinydb import TinyDB, Query
from datetime import datetime
from dotenv import load_dotenv
import os
from typing import Optional, List, Dict, Any


class StrategyDBClient:
    """
    A class to interact with the TinyDB database for storing and retrieving strategy results.
    """

    def __init__(self, db_path_env: str = 'database/db_paths.env') -> None:
        """
        Initializes the database connection.

        :param db_path_env: Path to the environment file containing the database path.
        """
        load_dotenv(db_path_env)
        db_path = os.getenv("STRATEGY_DB_PATH")
        if not db_path:
            raise ValueError("Database path not found in environment variables.")
        self.db = TinyDB(db_path) # will be created if it doesnt exist
        self.logs_table = self.db.table("logs")
        self.metadata_table = self.db.table("strategies")


    def add_strategy(self, strategy_id: str, symbol: str, quote_amount: float, time_interval: str, trades_limit: int, strategy_name: str, created_at: int ) -> None:
        """
        Adds metadata for a strategy.

        :param strategy_id: Unique identifier for the trading strategy.
        :param symbol: The trading pair symbol (e.g., BTC/USDT).
        :param quote_amount: The amount to trade.
        :param time_interval: The time interval to trade in.
        :param trades_limit: The number of trades before the loop stops.
        :param strategy_name: The name of the strategy.
        :param created_at: The time the strategy was created.
        """
        self.metadata_table.insert({
            "strategy_id": strategy_id,
            "symbol": symbol,
            "quote_amount": quote_amount,
            "time_interval": time_interval,
            "trades_limit": trades_limit,
            "strategy_name": strategy_name,
            "created_at": created_at
        })


    def add_log(self, strategy_id: str, timestamp: int, price: float, slippage: float, order: str) -> None:
        """
        Adds a log entry to the database for a given strategy.

        :param strategy_id: Unique identifier for the trading strategy.
        :param timestamp: Unix timestamp of the log entry.
        :param price: Price at the time of logging.
        :param slippage: Slippage of the Order (Order Price - Price which was used to make the decision.).
        :param order: Type of order executed (e.g., 'buy', 'sell').
        """
        self.logs_table.insert({
            "strategy_id": strategy_id,
            "timestamp": timestamp,
            "price": price,
            "slippage": slippage,
            "order": order,
        })


    # def get_logs(self, strategy_id: str, timestamp: Optional[str] = None) -> List[Dict[str, Any]]:
    #     """
    #     Retrieves strategy results. If a timestamp is provided, it returns all results from that timestamp onward.
    #
    #     :param strategy_name: The name of the strategy to query.
    #     :param timestamp: An optional timestamp string (ISO format). If provided, results are filtered accordingly.
    #     :return: A list of strategy records.
    #     """
    #     logs = Query()
    #     results = self.logs_table.search(logs.strategy_id == strategy_id)
    #
    #     if timestamp:
    #         try:
    #             timestamp_dt = datetime.fromisoformat(timestamp)
    #             results = [r for r in results if datetime.fromisoformat(r["timestamp"]) > timestamp_dt]
    #         except ValueError:
    #             raise ValueError("Invalid timestamp format. Use ISO 8601 format.")
    #
    #     return results

    def get_logs(self, strategy_id: str, timestamp: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retrieves strategy results. If a timestamp is provided, it returns all results from that timestamp onward.

        :param strategy_id: The ID of the strategy to query.
        :param timestamp: An optional Unix timestamp (float, int). If provided, results are filtered accordingly.
        :return: A list of strategy records.
        """
        logs = Query()
        results = self.logs_table.search(logs.strategy_id == strategy_id)

        if timestamp:
            try:
                # Ensure timestamp is a number
                if not isinstance(timestamp, (int, float)):
                    raise ValueError("Timestamp must be a Unix timestamp (int or float).")

                results = [r for r in results if r["timestamp"] > timestamp]
            except (ValueError, TypeError):
                raise ValueError("Invalid timestamp format. Use a Unix timestamp (int or float).")

        return results

    def get_latest_log_price(self, strategy_name: str) -> Optional[float]:
        """
        Retrieves the most recent price for a given strategy.

        :param strategy_name: The name of the strategy to query.
        :return: The latest price if available, otherwise None.
        """
        results = self.get_logs(strategy_name)
        return results[-1]["price"] if results else None


    def get_strategy_metadata(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves metadata for a strategy.
        """
        strategy = Query()
        results = self.metadata_table.search(strategy.strategy_id == strategy_id)
        return results[0] if results else None


    def get_all_strategies(self) -> List[Dict[str, Any]]:
        """
        Retrieves metadata for all strategies.

        :return: A list of dictionaries containing strategy metadata.
        """

        return self.metadata_table.all()
