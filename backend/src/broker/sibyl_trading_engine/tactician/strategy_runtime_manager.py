from typing import Dict, List
from backend.src.broker.sibyl_trading_engine.tactician.tactician_base import Tactician


class StrategyRuntimeHandler:
    """Handles the runtime execution of trading strategies.

    This class keeps track of running strategies and provides methods to add, stop, and retrieve them.
    """

    def __init__(self) -> None:
        """Initializes the handler with an empty dictionary of running strategies."""
        self.running_strategies: Dict[str, Tactician] = {}


    def add_strategy(self, strategy_id: str, strategy: Tactician) -> None:
        """Adds a new strategy to the running strategies list.

        Args:
            strategy_id (str): Unique identifier of the strategy.
            strategy (Tactician): Instance of the strategy to be executed.
        """
        self.running_strategies[strategy_id] = strategy


    def remove_strategy(self, strategy_id: str) -> None:
        """Removes a strategy from the running strategies list.

        Args:
            strategy_id (str): Unique identifier of the strategy.
        """
        del self.running_strategies[strategy_id]


    def stop_strategy(self, strategy_id: str) -> int | None:
        """Stops a running strategy by invoking its stop method.

        Args:
            strategy_id (str): Unique identifier of the strategy to stop.

        Raises:
            KeyError: If the strategy ID does not exist in the running strategies.
        """

        if strategy_id not in self.running_strategies.keys():
            raise KeyError(f"Strategy with ID '{strategy_id}' is not running.")

        self.running_strategies[strategy_id].stop_strategy()
        del self.running_strategies[strategy_id]  # Remove from active strategies
        return 1


    def get_active_strategies(self) -> List[str]:
        """Returns a list of active strategy IDs.

        Returns:
            List[str]: A list of currently running strategy IDs.
        """
        return list(self.running_strategies.keys())
