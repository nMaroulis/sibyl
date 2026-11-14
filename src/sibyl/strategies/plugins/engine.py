"""Causal immutable-prefix plugin decisions shared by backtests and validation.

The installed implementation is trusted Python, not a sandbox. Supplying only
past/current bars prevents accidental look-ahead through this interface; it does
not restrict arbitrary filesystem/network access by owner-installed code.
"""

from types import MappingProxyType

from sibyl.strategies.plugins.contracts import StrategyPlugin


def plugin_signals(factory, spec, values, candles):
    """Use a fresh checked instance and reject invalid directions without leaking plugin errors."""
    bars = tuple(
        MappingProxyType({key: row[key] for key in ("timestamp", "open", "high", "low", "close", "volume")})
        for row in candles
    )
    try:
        plugin = factory()
        if not isinstance(plugin, StrategyPlugin) or plugin.spec.model_dump() != spec.model_dump():
            raise ValueError("The plugin manifest changed.")
        directions = [0] * len(candles)
        for index in range(spec.warmup - 1, len(candles) - 1):
            value = plugin.signal(bars[: index + 1], MappingProxyType(values.copy()))
            if type(value) is not int or value not in {-1, 0, 1}:
                raise ValueError("Invalid plugin direction.")
            directions[index] = value
        return directions
    except Exception:
        raise ValueError(
            "The custom strategy failed or returned an invalid signal. No successful study or order was saved. Check the trusted plugin implementation."
        ) from None
