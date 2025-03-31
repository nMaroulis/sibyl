from typing import List, Dict, Any, Optional
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, ADXIndicator
from ta.volatility import BollingerBands
import numpy as np


class Analyst:

    def __init__(self, klines: List[Dict[str, float]]):
        self.id = None
        self.data = self.generate_dataset(klines)


    @staticmethod
    def generate_dataset(klines: List[Dict[str, float]]) -> pd.DataFrame:
        df = pd.DataFrame(klines)
        return df


    def calc_rsi(self, window=14):
        delta = self.data["close_price"].astype(float).diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        RS = gain / loss
        return 100 - (100 / (1 + RS))


    def calc_ema(self, method: str, window=5):
        if method == "exponential":
            return self.data["close_price"].ewm(span=window, adjust=False).mean()
        else:
            return self.data["close_price"].rolling(window=window).mean()


    def calc_bollinger_bands(self, window=3):
        std = 2
        lower_band = self.data["Moving Average"] - std * self.data["close_price"].ewm(span=window).std()
        upper_band = self.data["Moving Average"] + std * self.data["close_price"].ewm(span=window).std()
        return lower_band, upper_band


    def calc_kline_analytics(self):
        self.data["Moving Average"] = self.calc_ema("exponential", 5)
        self.data['RSI'] = self.calc_rsi(14)
        self.data['LowerBand'], self.data['UpperBand'] = self.calc_bollinger_bands(3)
        return self.data.to_dict()  # to_json(orient='records')


    def get_market_condition_score(self) -> float:
        """
        Calculates an advanced market condition score by incorporating trend strength (ADX),
        volatility (Bollinger Bands width), momentum (MACD), and overbought/oversold conditions (RSI).

        Returns:
            float: Market condition score (0-100).
        """

        # Compute indicators
        adx = ADXIndicator(high=self.data["high"], low=self.data["low"], close=self.data["close_price"]).adx()
        bb_width = BollingerBands(close=self.data["close_price"]).bollinger_wband()
        rsi = RSIIndicator(close=self.data["close_price"]).rsi()
        macd_hist = MACD(close=self.data["close_price"]).macd_diff()

        # Normalize indicators
        trend_strength = np.clip(adx.iloc[-1], 0, 50)
        volatility = np.clip(bb_width.iloc[-1] * 100, 0, 50)
        momentum = np.clip(macd_hist.iloc[-1] * 100, -50, 50)  # Normalize MACD histogram
        rsi_score = np.clip(50 - abs(rsi.iloc[-1] - 50), 0, 50)  # 50 means neutral, lower score if extreme

        # Dynamic weighting
        if adx.iloc[-1] > 25:  # Strong trend
            weights = [0.4, 0.3, 0.2, 0.1]  # More weight on trend & volatility
        else:
            weights = [0.2, 0.3, 0.3, 0.2]  # More weight on RSI & momentum

        # Compute final score
        score = (weights[0] * trend_strength) + (weights[1] * volatility) + \
                (weights[2] * momentum) + (weights[3] * rsi_score)

        return np.clip(score, 0, 100)  # Ensure the score is between 0-100


    def get_analytics(self) -> Optional[Dict[str, Any]]:
        try:
            klines_dict = self.calc_kline_analytics()
            score = self.get_market_condition_score()
            return {"klines": klines_dict, "score": score}
        except Exception as e:
            print(e)
            return None