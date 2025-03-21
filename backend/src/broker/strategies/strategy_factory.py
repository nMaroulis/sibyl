from backend.src.broker.strategies.bollinger_bands_strategy import BollingerBandsStrategy
from backend.src.broker.strategies.ema_crossover_strategy import EMACrossoverStrategy
from backend.src.broker.strategies.rsi_strategy import RSIStrategy
from typing import Type, Dict, Any


class StrategyFactory:
    _strategies: Dict[str, Type] = {
        'bollinger_bands': BollingerBandsStrategy,
        'exponential_moving_average_(ema)_crossover': EMACrossoverStrategy,
        'rsi': RSIStrategy,
    }

    @classmethod
    def get_strategy(cls, strategy_name: str, params: Dict[str, Any]) -> Any:
        strategy_class = cls._strategies.get(strategy_name)
        print(params)
        if not strategy_class:
            raise ValueError(f"Unknown Strategy name: {strategy_name}")
        return strategy_class(**params)
