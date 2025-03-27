from backend.src.broker.strategies.strategy_base import BaseStrategy
import pandas as pd
import numpy as np


class ImpulseBreakoutStrategy(BaseStrategy):
    """
    A comprehensive trading strategy combining trend-following and reversal signals.

    Uses Bollinger Bands, RSI, MACD, ADX, and Volume to detect high-probability trade entries.

    - **Buys** when there is trend confirmation and a momentum shift from oversold levels.
    - **Sells** when price momentum weakens and indicators suggest an overbought condition.

    Inspired by Freqtrade's CombinedBinHClucAndMADV3
    """

    def __init__(self, bb_window: int = 20, bb_std_dev: float = 2.0,
                 rsi_window: int = 14, ema_short: int = 9, ema_long: int = 21,
                 macd_short: int = 12, macd_long: int = 26, macd_signal: int = 9,
                 adx_window: int = 14, volume_factor: float = 1.5) -> None:
        """
        Initializes the strategy parameters.

        Args:
            bb_window (int): Bollinger Bands moving average window.
            bb_std_dev (float): Standard deviation for Bollinger Bands.
            rsi_window (int): RSI lookback period.
            ema_short (int): Short-term EMA.
            ema_long (int): Long-term EMA.
            macd_short (int): MACD short EMA.
            macd_long (int): MACD long EMA.
            macd_signal (int): MACD signal line.
            adx_window (int): ADX strength indicator window.
            volume_factor (float): Multiplier to detect volume spikes.
        """
        super().__init__()
        self.bb_window = bb_window
        self.bb_std_dev = bb_std_dev
        self.rsi_window = rsi_window
        self.ema_short = ema_short
        self.ema_long = ema_long
        self.macd_short = macd_short
        self.macd_long = macd_long
        self.macd_signal = macd_signal
        self.adx_window = adx_window
        self.volume_factor = volume_factor

        self.name = "Impulse Breakout Strategy"
        self.is_price_only = False


    def calculate_indicators(self, data: pd.DataFrame) -> None:
        """
        Computes Bollinger Bands, RSI, MACD, ADX, and Volume indicators.
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

        # MACD Calculation
        data["MACD"] = data["close_price"].ewm(span=self.macd_short, adjust=False).mean() - \
                       data["close_price"].ewm(span=self.macd_long, adjust=False).mean()
        data["MACD_Signal"] = data["MACD"].ewm(span=self.macd_signal, adjust=False).mean()

        # ADX Calculation
        data["ADX"] = data["close_price"].diff(self.adx_window).abs().rolling(window=self.adx_window).mean()

        # Volume Spike Detection
        data["Avg_Volume"] = data["volume"].rolling(window=self.bb_window).mean()
        data["Volume_Spike"] = data["volume"] > (self.volume_factor * data["Avg_Volume"])


    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generates buy and sell signals using multiple indicators.
        """
        self.data = data.copy()
        self.calculate_indicators(self.data)

        # Buy Conditions
        buy_condition = (
                (self.data["RSI"] < 35) &  # RSI near oversold
                (self.data["EMA_Short"] > self.data["EMA_Long"]) &  # EMA Uptrend
                (self.data["MACD"] > self.data["MACD_Signal"]) &  # MACD bullish crossover
                (self.data["ADX"] > 25) &  # Trend strength confirmation
                (self.data["close_price"] < self.data["lower_band"]) &  # Near lower BB
                (self.data["Volume_Spike"])  # High volume confirmation
        )

        # Sell Conditions
        sell_condition = (
                (self.data["RSI"] > 65) &  # RSI near overbought
                (self.data["EMA_Short"] < self.data["EMA_Long"]) &  # EMA Downtrend
                (self.data["MACD"] < self.data["MACD_Signal"]) &  # MACD bearish crossover
                (self.data["ADX"] > 25) &  # Trend strength confirmation
                (self.data["close_price"] > self.data["upper_band"]) &  # Near upper BB
                (self.data["Volume_Spike"])  # High volume confirmation
        )

        self.data["signal"] = np.where(buy_condition, "BUY",
                                       np.where(sell_condition, "SELL", "HOLD"))

        return self.data[["timestamp", "close_price", "upper_band", "lower_band", "RSI",
                          "EMA_Short", "EMA_Long", "MACD", "MACD_Signal", "ADX",
                          "Volume_Spike", "signal"]]


# 96049.3711205 USDT