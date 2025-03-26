from backend.src.broker.strategies.strategy_base import BaseStrategy
import pandas as pd
import numpy as np


class BollingerSurgeStrategy(BaseStrategy):
    """
    Full Name: Bollinger RSI Volume Surge Strategy
    Advanced trading strategy using Bollinger Bands, RSI, EMA, and Volume analysis.

    Buys when price is near the lower Bollinger Band, RSI is oversold, and EMA shows upward trend.
    Sells when price is near the upper Bollinger Band, RSI is overbought, and EMA signals a downward trend.
    """

    def __init__(self, bb_window: int = 20, bb_std_dev: float = 2.0,
                 rsi_window: int = 14, ema_short: int = 9, ema_long: int = 21,
                 volume_factor: float = 1.5) -> None:
        """
        Initializes the strategy.

        Args:
            bb_window (int): Bollinger Bands moving average window.
            bb_std_dev (float): Standard deviation for Bollinger Bands.
            rsi_window (int): RSI lookback period.
            ema_short (int): Short-term EMA window.
            ema_long (int): Long-term EMA window.
            volume_factor (float): Multiplier to detect volume spikes.
        """
        super().__init__()
        self.bb_window = bb_window
        self.bb_std_dev = bb_std_dev
        self.rsi_window = rsi_window
        self.ema_short = ema_short
        self.ema_long = ema_long
        self.volume_factor = volume_factor
        self.name = "Bollinger Surge Strategy"

    def calculate_indicators(self, data: pd.DataFrame) -> None:
        """
        Computes Bollinger Bands, RSI, EMA, and volume trends.
        """
        # Bollinger Bands
        data["SMA"] = data["close_price"].rolling(window=self.bb_window).mean()
        data["std_dev"] = data["close_price"].rolling(window=self.bb_window).std()
        data["upper_band"] = data["SMA"] + (data["std_dev"] * self.bb_std_dev)
        data["lower_band"] = data["SMA"] - (data["std_dev"] * self.bb_std_dev)

        # RSI Calculation
        delta = data["close_price"].diff()
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)

        avg_gain = pd.Series(gain).rolling(window=self.rsi_window).mean()
        avg_loss = pd.Series(loss).rolling(window=self.rsi_window).mean()
        rs = avg_gain / (avg_loss + 1e-9)  # Avoid division by zero
        data["RSI"] = 100 - (100 / (1 + rs))

        # EMA Calculation
        data["EMA_Short"] = data["close_price"].ewm(span=self.ema_short, adjust=False).mean()
        data["EMA_Long"] = data["close_price"].ewm(span=self.ema_long, adjust=False).mean()

        # Volume Spike Detection
        data["Avg_Volume"] = data["volume"].rolling(window=self.bb_window).mean()
        data["Volume_Spike"] = data["volume"] > (self.volume_factor * data["Avg_Volume"])

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generates buy, sell, or hold signals based on multiple factors.
        """
        self.data = data.copy()
        self.calculate_indicators(self.data)

        # Buy Conditions
        buy_condition = (
            (self.data["close_price"] < self.data["lower_band"]) &  # Price near lower BB
            (self.data["RSI"] < 30) &  # RSI oversold
            (self.data["EMA_Short"] > self.data["EMA_Long"]) &  # Uptrend EMA crossover
            (self.data["Volume_Spike"])  # High volume confirmation
        )

        # Sell Conditions
        sell_condition = (
            (self.data["close_price"] > self.data["upper_band"]) &  # Price near upper BB
            (self.data["RSI"] > 70) &  # RSI overbought
            (self.data["EMA_Short"] < self.data["EMA_Long"]) &  # Downtrend EMA crossover
            (self.data["Volume_Spike"])  # High volume confirmation
        )

        self.data["signal"] = np.where(buy_condition, "BUY",
                                       np.where(sell_condition, "SELL", "HOLD"))

        return self.data[["timestamp", "close_price", "upper_band", "lower_band", "RSI",
                          "EMA_Short", "EMA_Long", "Volume_Spike", "signal"]]
