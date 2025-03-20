from extra_streamlit_components import stepper_bar
from streamlit import write, container, expander, html, link_button, tabs, segmented_control, popover, dialog, pills
import re


@dialog('📖 Strategies Wiki', width="large")
def get_strategy_instructions(exp=False):

    # with expander('📖 Strategies Wiki', expanded=exp):
    with popover("Strategy types", icon=":material/info:"):
        write("""1. Trend Following Strategies:
            These strategies aim to capitalize on the momentum of an asset, typically in the direction of the prevailing market trend.
            Indicators used: EMA, Moving Averages, ADX (Average Directional Index), MACD (Moving Average Convergence Divergence)
            Example: A strategy that buys when a short-term EMA crosses above a long-term EMA (bullish crossover) and sells when it crosses below (bearish crossover).
            Common name: Moving Average Crossover strategy.
            2. Mean Reversion Strategies:
            These strategies assume that price tends to return to an average or equilibrium level after deviating too far from it.
            Indicators used: RSI, Bollinger Bands, Moving Averages, Z-Score
            Example: A strategy that buys when the price touches the lower Bollinger Band (assuming the price will revert back to the middle band or trend upwards) and sells when it touches the upper Bollinger Band.
            Common names: Bollinger Bands Reversal, RSI Reversion, Mean Reversion Strategy.
            3. Breakout Strategies:
            These strategies focus on identifying when an asset breaks out of a certain range or pattern, expecting that the price will continue in the breakout direction.
            Indicators used: Bollinger Bands, Price Action, Volume, Volatility Indicators
            Example: A strategy that buys when the price breaks above the upper Bollinger Band (breakout to the upside) and sells when it breaks below the lower Bollinger Band (breakout to the downside).
            Common names: Bollinger Bands Breakout, Volatility Breakout strategy.
            4. Momentum Strategies:
            These strategies aim to capture trends in their early stages by focusing on the strength of the price movement.
            Indicators used: RSI, MACD, Momentum Indicator
            Example: A strategy that buys when the RSI crosses above 30 and the price shows strong momentum in an upward direction, and sells when RSI shows overbought conditions (above 70) or price momentum weakens.
            Common names: RSI Momentum, Momentum Oscillator strategy.
            5. Swing Trading Strategies:
            Swing trading focuses on capturing short- to medium-term moves in the market, often within a trend or during periods of consolidation.
            Indicators used: RSI, EMA, MACD, Fibonacci Retracement, Bollinger Bands
            Example: A strategy that buys when RSI is oversold and the price is near the lower Bollinger Band, then sells when the price moves back to the middle band or higher.
            Common names: Swing Reversal, Swing Trading strategy.
            6. Scalping Strategies:
            These strategies aim to make quick profits from small price movements within a very short time frame.
            Indicators used: EMA, RSI, MACD
            Example: A scalping strategy that buys when short-term EMA crosses above the long-term EMA and sells when it crosses below, all within a few minutes or hours.
            Common names: Scalping Strategy, EMA Scalping.
            7. Volatility-Based Strategies:
            These strategies are based on measuring and reacting to market volatility.
            Indicators used: Bollinger Bands, ATR (Average True Range), VIX (Volatility Index)
            Example: A strategy that buys when the Bollinger Bands contract (indicating low volatility) and sells when they expand (indicating high volatility).
            Common names: Volatility Breakout, Bollinger Squeeze.
            Summary of Strategy Types:
            Trend Following: Follow the market’s direction (EMA, moving averages).
            Mean Reversion: Trade against the price extremes (RSI, Bollinger Bands).
            Breakout: Capitalize on a significant price movement beyond a range (Bollinger Bands, Price Action).
            Momentum: Focus on the strength of price movements (RSI, MACD).
            Swing Trading: Capture shorter-term moves within a larger trend (RSI, EMA, Bollinger Bands).
            Scalping: Make small profits on rapid, frequent trades (EMA, RSI, MACD).
            Volatility-Based: Trade based on market volatility (Bollinger Bands, ATR).
            These strategies are not mutually exclusive, and many traders combine indicators from different categories to improve the accuracy of their trades. For instance, a trend-following strategy could incorporate a RSI filter to avoid buying into overbought conditions. Similarly, a breakout strategy might use an EMA to confirm the direction of the trend before executing the trade.
            """)
    strat_filter = pills("Strategy types:", options=["All", "Trend Following", "Mean Reversion", "Breakout", "Momentum", "Swing Trading", "Scalping", "Volatility-Based", "ML Model"], default="All", )

    if strat_filter in ["All", "Mean Reversion", "Momentum", "Swing Trading", "Scalping"]:

        with expander("**RSI**", expanded=False):
            write("""Purpose: RSI is a momentum oscillator that measures the speed and change of price movements. It ranges from 0 to 100 and is typically used to identify overbought or oversold conditions.
                Common Strategy:
                Overbought (>70): The asset may be overbought and could be due for a price correction (sell signal).
                Oversold (<30): The asset may be oversold and could rebound (buy signal).
                When to Use:
                RSI works well in ranging (sideways) markets.
                Good for short-term trades where you want to identify potential reversals.
                It's best used with other indicators to confirm entry and exit signals.
                """)
    if strat_filter in ["All", "Trend Following", "Swing Trading", "Scalping"]:
        with expander("**Exponential Moving Average Crossover**", expanded=False):
            write("""Exponential Moving Average (EMA):
                Purpose: EMA is a type of moving average that gives more weight to recent prices, making it more responsive to price changes compared to a simple moving average (SMA).
                Common Strategy:
                EMA Crossover: When a short-term EMA crosses above a long-term EMA, it generates a buy signal. When a short-term EMA crosses below a long-term EMA, it generates a sell signal.
                EMA can also be used to determine trend direction. For instance, if the price is above the 50-period EMA, it might indicate an uptrend, and if below, a downtrend.
                When to Use:
                EMA is particularly effective in trending markets (either up or down).
                Best used for medium to long-term trading strategies where you are looking for trend-following signals.
                """)
    if strat_filter in ["All", "Mean Reversion", "Breakout", "Swing Trading", "Volatility-Based"]:
        with expander("**Bollinger Bands**", expanded=False):
            write("""Purpose: Bollinger Bands consist of a middle band (SMA), and two outer bands that are typically two standard deviations away from the middle band. The bands widen during periods of high volatility and contract during low volatility.
                Common Strategy:
                Price Touching the Upper Band: This suggests the market may be overbought, indicating a potential sell signal.
                Price Touching the Lower Band: This suggests the market may be oversold, indicating a potential buy signal.
                Bollinger Band Squeeze: When the bands tighten, it indicates low volatility and could precede a significant price move (breakout or breakdown).
                When to Use:
                Useful in volatile markets where price can fluctuate within a certain range.
                Best for swing trading and breakout strategies, especially when you're looking for price reversals or anticipating volatility.
                """)


def extract_coin_symbol(text):
    match = re.search(r'\[([^\]]+)\]$', text)
    return match.group(1) if match else text
