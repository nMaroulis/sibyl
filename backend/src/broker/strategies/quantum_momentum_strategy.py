from backend.src.broker.strategies.strategy_base import BaseStrategy
import pandas as pd
import numpy as np


class QuantumMomentumStrategy(BaseStrategy):
    """
    Advanced multi-factor strategy using MACD, ATR-based stop-loss, CMF, and TSI.

    - Uses MACD for trend confirmation.
    - Adaptive stop-loss using ATR.
    - Volume-based filtering with Chaikin Money Flow (CMF).
    - Trend Strength Index (TSI) for improved momentum signals.
    """

    def __init__(self, macd_short=12, macd_long=26, macd_signal=9,
                 atr_window=14, cmf_window=20, tsi_long=25, tsi_short=13) -> None:
        super().__init__()
        self.macd_short = macd_short
        self.macd_long = macd_long
        self.macd_signal = macd_signal
        self.atr_window = atr_window
        self.cmf_window = cmf_window
        self.tsi_long = tsi_long
        self.tsi_short = tsi_short
        self.name = "Quantum Momentum Strategy"


    def calculate_indicators(self, data: pd.DataFrame) -> None:
        """
        Compute MACD, ATR, CMF, and TSI.
        """

        # MACD Calculation
        short_ema = data["close_price"].ewm(span=self.macd_short, adjust=False).mean()
        long_ema = data["close_price"].ewm(span=self.macd_long, adjust=False).mean()
        data["MACD"] = short_ema - long_ema
        data["MACD_Signal"] = data["MACD"].ewm(span=self.macd_signal, adjust=False).mean()

        # ATR Calculation for Stop-Loss
        high_low = data["high_price"] - data["low_price"]
        high_close = np.abs(data["high_price"] - data["close_price"].shift())
        low_close = np.abs(data["low_price"] - data["close_price"].shift())
        tr = np.maximum.reduce([high_low, high_close, low_close])
        data["ATR"] = pd.Series(tr).rolling(window=self.atr_window).mean()

        # CMF (Chaikin Money Flow) Calculation
        money_flow_mult = ((data["close_price"] - data["low_price"]) - (data["high_price"] - data["close_price"])) / (
                    data["high_price"] - data["low_price"] + 1e-9)
        money_flow_vol = money_flow_mult * data["volume"]
        data["CMF"] = money_flow_vol.rolling(window=self.cmf_window).sum() / data["volume"].rolling(
            window=self.cmf_window).sum()

        # TSI (Trend Strength Index) Calculation
        price_diff = data["close_price"].diff()
        abs_price_diff = abs(price_diff)
        smoothed_diff = price_diff.ewm(span=self.tsi_short, adjust=False).mean().ewm(span=self.tsi_long,
                                                                                     adjust=False).mean()
        smoothed_abs_diff = abs_price_diff.ewm(span=self.tsi_short, adjust=False).mean().ewm(span=self.tsi_long,
                                                                                             adjust=False).mean()
        data["TSI"] = 100 * (smoothed_diff / (smoothed_abs_diff + 1e-9))


    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generates buy and sell signals based on MACD, CMF, ATR, and TSI.
        """
        self.data = data.copy()
        self.calculate_indicators(self.data)

        # Buy Signal: MACD crossover, TSI above 20, CMF positive, ATR-based stop
        buy_condition = (
                (self.data["MACD"] > self.data["MACD_Signal"]) &  # MACD bullish crossover
                (self.data["TSI"] > 20) &  # TSI indicates strong momentum
                (self.data["CMF"] > 0) &  # Smart money flowing in
                (self.data["ATR"] > self.data["ATR"].rolling(window=10).mean())  # Volatility is high
        )

        # Sell Signal: MACD bearish crossover, TSI below -20, CMF negative
        sell_condition = (
                (self.data["MACD"] < self.data["MACD_Signal"]) &  # MACD bearish crossover
                (self.data["TSI"] < -20) &  # TSI indicates weak momentum
                (self.data["CMF"] < 0)  # Smart money flowing out
        )

        self.data["signal"] = np.where(buy_condition, "BUY",
                                       np.where(sell_condition, "SELL", "HOLD"))

        return self.data[["timestamp", "close_price", "MACD", "CMF", "TSI", "ATR", "signal"]]
