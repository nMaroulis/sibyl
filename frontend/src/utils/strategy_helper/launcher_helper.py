from streamlit import write, expander, popover, dialog, pills, number_input, warning, button, caption, columns, html, markdown, latex
import re
from typing import Dict, Any

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


def strategy_params_form(strategy: str) -> Dict[str, Any]:
    write("**Strategy Params**")

    strategy_params_dict = {}
    if strategy == "Bollinger Bands":
        caption("Bollinger Bands Strategy – Uses Bollinger Bands to identify price volatility. "
                "It **buys** when the price crosses the **lower band** and **sells** when it crosses the **upper band**, assuming a price reversal.")
        window = number_input("Window Size", value=20, min_value=1, max_value=1000)
        st_dev = number_input("Standard Deviation", value=2.0, min_value=0.0, max_value=4.0)
        strategy_params_dict["window"] = window
        strategy_params_dict["std_dev"] = st_dev
    elif strategy == "[Sibyl] Bollinger Surge":
        caption("Bollinger RSI Volume Surge Strategy – A **multi-factor** approach combining Bollinger Bands, RSI, EMA crossover, "
                "and volume spikes. It **buys** when the price is near the **lower band**, RSI is **oversold**, and **volume surges**, "
                "and **sells** when the price is near the **upper band**, RSI is **overbought**, and **volume confirms the trend**.")
        caption("**Bollinger Bands** parameters.")
        c00, c01 = columns(2)
        with c00:
            bb_window = number_input("Bollinger Bands moving average window", min_value=1, value = 20, max_value=1000)
        with c01:
            bb_std_dev = number_input("Standard deviation for Bollinger Bands", min_value=0.0, value=2.0, max_value=10.0)
        caption("**RSI**: Relative Strength Index parameters.")
        rsi_window = number_input("RSI lookback window", min_value=1, value = 20, max_value=100)
        caption("**EMA**: Exponential Moving Averages parameters.")
        c10, c11 = columns(2)
        with c10:
            ema_short = number_input("Short-term EMA window", min_value=1, value = 9, max_value=80)
        with c11:
            ema_long = number_input("Long-term EMA window", min_value=1, value = 21, max_value=100)
        caption("**Volume**: Multiplier factor.")
        volume_factor = number_input("Multiplier to detect volume spikes", min_value=1.0, value=1.5, max_value=50.0)
        strategy_params_dict["bb_window"] = bb_window
        strategy_params_dict["bb_std_dev"] = bb_std_dev
        strategy_params_dict["rsi_window"] = rsi_window
        strategy_params_dict["ema_short"] = ema_short
        strategy_params_dict["ema_long"] = ema_long
        strategy_params_dict["volume_factor"] = volume_factor
    elif strategy == "Exponential Moving Average (EMA) crossover":
        caption("EMA Crossover Strategy – Tracks **price trends** using two **Exponential Moving Averages** (EMA). "
                "A **buy** signal occurs when the **short EMA crosses above the long EMA**, while a **sell** signal is triggered when it **crosses below**.")
        short_window = number_input("Short Window Size", value=10, min_value=1, max_value=1000)
        long_window = number_input("Long Window Size", value=50, min_value=1, max_value=1000)
        strategy_params_dict["short_window"] = short_window
        strategy_params_dict["long_window"] = long_window
    elif strategy == "[Sibyl] Impulse Breakout":
        caption("The Impulse Breakout Strategy focuses on detecting **sudden price movements** and **breakouts** from established "
                "**support** or **resistance levels**. It aims to capitalize on strong price momentum following a breakout by entering "
                "trades when the price exhibits significant strength. The strategy relies on price volume confirmation to filter out false breakouts and capture larger market moves.")
        with popover("Strategy info", icon=":material/contact_support:"):
            write("""
            1. Bollinger Bands (BB)
            bb_window = 20: The number of periods (candles) used to calculate the Bollinger Bands.
            bb_std_dev = 2.0: The number of standard deviations used to create the upper and lower Bollinger Bands.
            What it does:
            Bollinger Bands help measure volatility and identify potential breakouts.
            Price breaking above the upper band may indicate a strong bullish impulse, while breaking below the lower band suggests a bearish breakout.
            2. Relative Strength Index (RSI)
            rsi_window = 14: The number of periods used to calculate RSI.
            What it does:
            RSI measures the speed and magnitude of price movements.
            Values above 70 indicate overbought conditions (potential sell signal), and values below 30 indicate oversold conditions (potential buy signal).
            This is useful in confirming whether a breakout has momentum.
            3. Exponential Moving Averages (EMA)
            ema_short = 9: A short-term EMA that reacts quickly to price changes.
            ema_long = 21: A longer-term EMA that smooths out price trends.
            What it does:
            When the short EMA crosses above the long EMA, it signals a bullish trend.
            When the short EMA crosses below the long EMA, it signals a bearish trend.
            These EMAs help filter false breakouts by confirming trend direction.
            4. Moving Average Convergence Divergence (MACD)
            macd_short = 12: Short-term EMA used in MACD.
            macd_long = 26: Long-term EMA used in MACD.
            macd_signal = 9: Signal line EMA for MACD.
            What it does:
            The MACD measures trend momentum and strength.
            A MACD line crossing above the signal line is bullish, while crossing below is bearish.
            Helps confirm the validity of a breakout.
            5. Average Directional Index (ADX)
            adx_window = 14: The number of periods used to calculate ADX.
            What it does:
            The ADX measures the strength of a trend, regardless of direction.
            A high ADX (above 25) indicates a strong trend, making breakouts more reliable.
            A low ADX suggests a weak trend, where breakouts might fail.
            6. Volume Factor
            volume_factor = 1.5: A multiplier used to check if the breakout occurs with higher-than-average volume.
            What it does:
            Ensures that breakouts are accompanied by a surge in volume, making them more reliable.
            If the current volume is 1.5x the average volume, it confirms strong market participation in the breakout.
            Summary of Impulse Breakout Strategy:
            Identifies breakouts using Bollinger Bands.
            Confirms trend strength with EMAs, MACD, and ADX.
            Filters false signals using RSI and volume surges.
            Targets high-momentum moves with a combination of these indicators.
            This strategy is ideal for short-term trading, as it quickly identifies breakouts with strong volume and momentum confirmation. 🚀
            """)

        caption("**Bollinger Bands** parameters.")
        c00, c01 = columns(2)
        with c00:
            bb_window = number_input("Bollinger Bands: Window Size", min_value=1, value = 20, max_value=100,
                                      help="The number of periods (candles) used to calculate the Bollinger Bands.")
        with c01:
            bb_std_dev = number_input("Bollinger Bands: Standard Deviations for upper & lower bands", min_value=0.1, value=2.0, max_value=10.0,
                                     help="The number of standard deviations used to create the upper and lower Bollinger Bands.")
        caption("**RSI**: Relative Strength Index parameters.")
        rsi_window = number_input("RSI: Number of Periods", min_value=1, value = 14, max_value=100,
                                  help="The number of periods used to calculate RSI.")
        caption("**EMA**: Exponential Moving Averages parameters.")
        c10, c11 = columns(2)
        with c10:
            ema_short = number_input("EMA: Short-term", min_value=1, value = 9, max_value=1000,
                                      help="A short-term EMA that reacts quickly to price changes.")
        with c11:
            ema_long = number_input("EMA: Long-term", min_value=1, value = 21, max_value=1000,
                                      help="A longer-term EMA that smooths out price trends.")
        caption("**MACD**: Provides signals based on the convergence or divergence of short-term and long-term trends.")
        c20, c21, c22 = columns(3)
        with c20:
            macd_short = number_input("MACD: Short-term exponential moving average (EMA) period", min_value=1, value = 12, max_value=100,
                                      help="This is the short-term exponential moving average (EMA) period used in the MACD calculation. It represents a faster-moving average that reacts more quickly to price changes.")
        with c21:
            macd_long = number_input("MACD: Long-term exponential moving average (EMA) period", min_value=2, value=26, max_value=100,
                                     help="This is the long-term EMA period used in the MACD calculation. It represents a slower-moving average that responds more slowly to price changes.")
        with c22:
            macd_signal = number_input("MACD: Signal Line", min_value=1, value = 9, max_value=100,
                                       help="This is the signal line, which is the n-period EMA of the MACD. The signal line is used to generate buy or sell signals when the MACD crosses above or below it.")
        caption("**ADX**: Average Directional Index (ADX) parameters.")
        adx_window = number_input("ADX: Window Size", min_value=1, value=14, max_value=1000,
                                help="Measures the strength of a trend, regardless of direction.")
        caption("**Volume** Surge parameters.")
        volume_factor = number_input("Volume: Multiplier Factor", min_value=0.0, value=1.5, max_value=50.0,
                                help="A multiplier used to check if the breakout occurs with higher-than-average volume.")
        strategy_params_dict["bb_window"] = bb_window
        strategy_params_dict["bb_std_dev"] = bb_std_dev
        strategy_params_dict["rsi_window"] = rsi_window
        strategy_params_dict["ema_short"] = ema_short
        strategy_params_dict["ema_long"] = ema_long
        strategy_params_dict["macd_short"] = macd_short
        strategy_params_dict["macd_long"] = macd_long
        strategy_params_dict["macd_signal"] = macd_signal
        strategy_params_dict["adx_window"] = adx_window
        strategy_params_dict["volume_factor"] = volume_factor

    elif strategy == "[Sibyl] Quantum Momentum":
        caption("The Quantum Momentum Strategy uses a combination of** momentum indicators** and **price trends** to identify powerful market moves. "
                "By analyzing the acceleration of price changes and the strength of momentum, it aims to catch trend reversals or breakouts. "
                "It buys when there is strong upward momentum and sells when momentum weakens, maximizing potential gains during trending periods.")

        with popover("Strategy info", icon=":material/contact_support:"):
            write("""
            1. MACD (Moving Average Convergence Divergence):
            macd_short = 12: This is the short-term exponential moving average (EMA) period used in the MACD calculation. It represents a faster-moving average that reacts more quickly to price changes.
            macd_long = 26: This is the long-term EMA period used in the MACD calculation. It represents a slower-moving average that responds more slowly to price changes.
            macd_signal = 9: This is the signal line, which is the 9-period EMA of the MACD. The signal line is used to generate buy or sell signals when the MACD crosses above or below it.
            What it does: The MACD is a momentum indicator that shows the difference between the short-term and long-term moving averages. When the MACD crosses above the signal line, it’s a bullish signal, and when it crosses below, it’s a bearish signal.
            2. ATR (Average True Range):
            atr_window = 14: The ATR is a volatility indicator. The 14 is the window size used to calculate the average true range, which is the average of the true range values over the past 14 periods (usually 14 days or 14 bars/candles). It measures market volatility.
            What it does: ATR helps identify the volatility of an asset. A higher ATR means more volatility, while a lower ATR indicates less volatility. This can be used to adjust stop-losses or gauge potential price movement.
            3. CMF (Chaikin Money Flow):
            cmf_window = 20: This is the period used to calculate the CMF. The CMF combines both price and volume to measure the flow of money into or out of an asset. It’s calculated by comparing the closing price to the range of the asset during a specific period, typically 20 periods.
            What it does: The CMF indicates whether money is flowing into (bullish) or out of (bearish) an asset. A positive CMF suggests buying pressure, and a negative CMF suggests selling pressure.
            4. TSI (True Strength Index):
            tsi_long = 25: The long-term period used for calculating the TSI. It’s a smoothing factor that helps calculate the TSI over a longer period, capturing the overall trend.
            tsi_short = 13: The short-term period used for calculating the TSI. It reacts quicker to price changes and can help identify short-term momentum changes.
            What it does: The TSI is a momentum oscillator that helps measure the strength of a trend. It is similar to the MACD but uses double smoothing to remove noise and focus on the strength of the price trend. The TSI compares short-term and long-term momentum, and crossovers between the short and long TSI can signal trend changes.
            Summary of their role in the strategy:
            MACD: Provides signals based on the convergence or divergence of short-term and long-term trends.
            ATR: Measures volatility and can be used for position sizing and setting stop-losses.
            CMF: Indicates money flow into or out of the asset, helping assess whether there’s buying or selling pressure.
            TSI: Focuses on momentum and trend strength, indicating whether the current trend is strong or weakening.         
            """)

        caption("**MACD**: Provides signals based on the convergence or divergence of short-term and long-term trends.")
        c00, c01, c02 = columns(3)
        with c00:
            macd_short = number_input("MACD: Short-term exponential moving average (EMA) period", min_value=1, value = 12, max_value=100,
                                      help="This is the short-term exponential moving average (EMA) period used in the MACD calculation. It represents a faster-moving average that reacts more quickly to price changes.")
        with c01:
            macd_long = number_input("MACD: Long-term exponential moving average (EMA) period", min_value=2, value=26, max_value=100,
                                     help="This is the long-term EMA period used in the MACD calculation. It represents a slower-moving average that responds more slowly to price changes.")
        with c02:
            macd_signal = number_input("MACD: Signal Line", min_value=1, value = 9, max_value=100,
                                       help="This is the signal line, which is the n-period EMA of the MACD. The signal line is used to generate buy or sell signals when the MACD crosses above or below it.")
        caption("**ATR**: Measures volatility and can be used for position sizing and setting stop-losses.")
        atr_window = number_input("ATR (Average True Range): Window Size", min_value=1, value = 14, max_value=100,
                                  help="The ATR is a volatility indicator. The 14 is the window size used to calculate the average true range, "
                                       "which is the average of the true range values over the past 14 periods (usually 14 days or 14 bars/candles). It measures market volatility.")
        caption("**CMF**: Indicates money flow into or out of the asset, helping assess whether there’s buying or selling pressure.")
        cmf_window = number_input("CMF (Chaikin Money Flow): Window Size", min_value=1, value = 20, max_value=100,
                                  help="This is the period used to calculate the CMF. The CMF combines both price and volume to "
                                       "measure the flow of money into or out of an asset. It’s calculated by comparing the closing price to the range of the asset during a specific period, typically 20 periods.")
        caption("**TSI**: Focuses on momentum and trend strength, indicating whether the current trend is strong or weakening.")
        c10, c11 = columns(2)
        with c10:
            tsi_long = number_input("TSI (True Strength Index): Long Period", min_value=2, value=25, max_value=200,
                                    help="The long-term period used for calculating the TSI. It’s a smoothing factor that helps calculate the TSI over a longer period, capturing the overall trend.")
        with c11:
            tsi_short = number_input("TSI (True Strength Index): Short Period", min_value=1, value=13, max_value=200,
                                     help="The short-term period used for calculating the TSI. It reacts quicker to price changes and can help identify short-term momentum changes.")
        strategy_params_dict["macd_short"] = macd_short
        strategy_params_dict["macd_long"] = macd_long
        strategy_params_dict["macd_signal"] = macd_signal
        strategy_params_dict["atr_window"] = atr_window
        strategy_params_dict["cmf_window"] = cmf_window
        strategy_params_dict["tsi_long"] = tsi_long
        strategy_params_dict["tsi_short"] = tsi_short
    elif strategy == "RSI":
        caption("RSI Strategy – Based on the Relative Strength Index (RSI), this strategy **buys** when the RSI indicates "
                "an **oversold market** (< *Buy Threshold*) and **sells** when it signals an **overbought market** (> *Sell Threshold*).")
        rsi_period = number_input("RSI Period", value=14, min_value=1, max_value=100)
        buy_threshold = number_input("Buy Threshold", value=30, min_value=1, max_value=1000)
        sell_threshold = number_input("Sell Threshold", value=70, min_value=1, max_value=1000)
        strategy_params_dict["rsi_period"] = rsi_period
        strategy_params_dict["buy_threshold"] = buy_threshold
        strategy_params_dict["sell_threshold"] = sell_threshold
    else:
        warning("Invalid algorithm selected.", icon=":material/warning:")
    button("Strategy Parameters LLM Advisor", icon=":material/manufacturing:",disabled=True)
    return strategy_params_dict


def backtest_evaluation_results(metrics: dict) -> None:

    html_txt = """
        <style>
        .evaluation-metrics-container {
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            background: rgba(255, 255, 255, 0.1);
            padding: 20px;
            border-radius: 12px;
            # box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);
            backdrop-filter: blur(10px); /* Frosted glass effect */
            max-width: 100%;
        }

        .evaluation-metric {
            background: rgba(5, 122, 247, 1.0);
            color: white;
            padding: 12px 18px;
            border-radius: 10px;
            font-weight: bold;
            display: flex;
            align-items: center;
            gap: 8px;
            white-space: nowrap;
            transition: transform 0.2s, background 0.2s;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
        }

        .evaluation-metric:hover {
            background: rgba(1, 57, 117, 0.9);
            transform: scale(1.05);
        }

        .evaluation-metric-name {
            opacity: 0.9;
            font-size: 0.9em;
        }

        .evaluation-metric-value {
            font-size: 1.2em;
            font-weight: bold;
        }
    </style>"""
    html_txt += """<div class="evaluation-metrics-container">"""
    for key, value in metrics.items():
        key = key.replace("_", " ")
        if key == "win rate":
            value = f"{round(value, 2)}%"
        html_txt += f"""<div class="evaluation-metric"><span class="evaluation-metric-name">{key}:</span> <span class="evaluation-metric-value">{value}</span></div>"""
    html_txt += """</div>"""
    html(html_txt)



def get_market_condition_message(score: float) -> None:
    """
    Returns a message and color based on the market condition score.

    Args:
        score (float): The market condition score.

    Returns:
        tuple[str, str]: A message and color hex code.
    """
    if score < 30:
        message, color = ("❌ Unfavorable Market – High uncertainty, not ideal for trading.", "#ff4d4d")
    elif score < 60:
        message, color = ("⚠️ Neutral Market – Some opportunities, but risk is present.", "#ffcc00")
    elif score < 80:
        message, color = ("✅ Good Market – Favorable conditions, likely trends.", "#4CAF50")
    else:
        message, color = ("🚀 Strong Market – Ideal for trading, strong trend confirmation.", "#008CBA")


    # HTML Card with Stylish Light Theme
    html_code = f"""
        <div style="
            background-color: #ffffff;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            font-family: Arial, sans-serif;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
            max-width: 80%;
            margin: auto;
        ">
            <h2 style="color: #333; margin-bottom: 5px;">🎯 Market Condition Score</h2>
            <p style="font-size: 42px; font-weight: bold; color: {color}; margin: 10px 0;">{score:.1f} / 100</p>
            <p style="font-size: 18px; color: #444; background-color: {color}22; padding: 10px; border-radius: 8px;">{message}</p>
        </div>
    """

    # Display in Streamlit
    html(html_code)


def market_condition_explanation():
    with popover("How is it calculated?", icon=":material/contact_support:"):
        markdown("""
        ##📌 Market Condition Score Explanation
        
        The Market Condition Score is a quantitative metric designed to assess the suitability of the current market for trading strategies. It evaluates four key aspects of market behavior:
        
        1. **Trend Strength** 📈 – Measured using the Average Directional Index (ADX).
        2. **Volatility** 🌊 – Measured using Bollinger Bands Width (BB Width).
        3. **Momentum** 🚀 – Measured using the MACD Histogram (MACD Hist).
        4. **Overbought/Oversold Conditions** 🎭 – Measured using the Relative Strength Index (RSI).
        
        The score ranges from 0 to 100, where:
        - **High values** (e.g., 70-100) indicate a favorable market for trading.
        - **Low values** (e.g., 0-30) suggest uncertain or unfavorable conditions.
        ----
        🔹 How the Score is Calculated
        The function retrieves historical candlestick data (K-lines) and computes the four indicators. The values are **normalized** and **weighted dynamically** based on trend strength.
        
        Formula for Market Condition Score:
        """)

        latex(r"""
        S = w_1 \cdot \min(50, \text{ADX}) + 
            w_2 \cdot \min(50, \text{BB Width} \times 100) + 
            w_3 \cdot \min(50, \max(-50, \text{MACD Hist} \times 100)) + 
            w_4 \cdot \min(50, 50 - |\text{RSI} - 50|)
        """)

        markdown("""
        Where:
        - **Trend Strength** = *min(50, ADX)*
        - **Volatility** = *min(50, Bollinger Band Width × 100)*
        - **Momentum** = *min(50, MACD Histogram × 100)*
        - **RSI Score** = *min(50, 50 - |RSI - 50|)* (Centered at 50, penalizes extremes)
        - **Dynamic Weights**:
            - if **ADX > 25** (Strong Trend) -> More weight on Trend & Volatility.
            - if **ADX <= 25** (Weak trend) -> More weight on RSI & Momentum.
        """)