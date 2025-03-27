from backend.src.broker.strategies.bollinger_bands_strategy import BollingerBandsStrategy
from backend.src.broker.strategies.ema_crossover_strategy import EMACrossoverStrategy
from backend.src.broker.strategies.rsi_strategy import RSIStrategy
from backend.src.broker.strategies.bollinger_surge_strategy import BollingerSurgeStrategy
from backend.src.broker.strategies.impulse_breakout_strategy import ImpulseBreakoutStrategy
from backend.src.broker.strategies.quantum_momentum_strategy import QuantumMomentumStrategy
from typing import Type, Dict, Any


class StrategyFactory:
    _strategies: Dict[str, Type] = {
        'bollinger_bands': BollingerBandsStrategy,
        'bollinger_surge': BollingerSurgeStrategy,
        'exponential_moving_average_(ema)_crossover': EMACrossoverStrategy,
        'impulse_breakout': ImpulseBreakoutStrategy,
        'quantum_momentum': QuantumMomentumStrategy,
        'rsi': RSIStrategy,
    }

    @classmethod
    def get_strategy(cls, strategy_name: str, params: Dict[str, Any]) -> Any:
        strategy_class = cls._strategies.get(strategy_name)
        if not strategy_class:
            raise ValueError(f"Unknown Strategy name: {strategy_name}")
        return strategy_class(**params)
