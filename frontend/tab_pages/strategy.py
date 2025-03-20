import streamlit as st
from frontend.src.library.overview_helper.client import fetch_account_spot
from frontend.src.library.overview_helper.navigation import api_status_check
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.src.library.strategy_helper.funcs import get_strategy_instructions
from frontend.src.library.ui_elements import col_style2
from frontend.src.library.analytics_helper.client import fetch_available_assets
from frontend.src.library.strategy_helper.client import post_strategy
import pandas as pd


fix_page_layout('strategy')
set_page_title("Trading Strategy")
st.html(col_style2)

st.caption("Click the button below 👇👇 to get information on the available strategies.")
if st.button("Strategies Wiki", icon=":material/menu_book:", type="primary"):
    get_strategy_instructions()

if "available_exchange_apis" not in st.session_state:
    with st.spinner("Checking API Availability Status..."):
        api_status_check()

if st.session_state["available_exchange_apis"]:
    exchange = st.selectbox('Choose Exchange', options=st.session_state["available_exchange_apis"])
    st.divider()
    with st.container(border=False):

        # with st.spinner(f"Fetching available {exchange} asset pairs..."):
        #     asset_list = fetch_available_assets(st.session_state['trade_exchange_api'], quote_asset="all")


        # show available balance
        c0 = st.columns(1)
        with c0[0]:
            balance = fetch_account_spot(exchange.lower().replace(" ", "_"))
            balance = {asset: price["free"] for asset, price in balance["spot_balances"].items()}
            st.write("**1. Quote Asset**")
            st.caption("Choose the **Quote Asset** which will be used in this strategy. Below you'll see all the assets you have available in your account and the corresponding markets you can deploy the strategy.")
            default_quote_index = list(balance.keys()).index("USDT") if "USDT" in balance.keys() else 0  # making USDT appear as preselected choice
            quote_asset = st.selectbox('Quote Asset', options=balance.keys(), index=default_quote_index)
            st.metric("Available Balance", f"{balance[quote_asset]} {quote_asset}")

        c1 = st.columns(1)
        with c1[0]:
            st.write("**2. Quote Amount**")
            st.caption(f"Choose the Quote amount you want to trade on this strategy. Each order sent to the {exchange} API will define the quote_quantity and not the base.")
            st.warning("**Warning**: Choose only what you can afford to lose, as the whole Quote amount is at risk.", icon=":material/warning:")
            quote_amount = st.number_input("Quote Amount", min_value=0.0, max_value=balance[quote_asset])

        c2 = st.columns(1)
        with c2[0]:
            st.write("**3. Base Asset**")
            st.caption(f"Choose the Base Asset. The available base assets correspond to the selected quote asset and the available markets at {exchange}.")
            base_assets = fetch_available_assets(exchange, quote_asset)
            base_asset = st.selectbox('Base Asset', options=base_assets[quote_asset])
            st.info(f"The selected market for this strategy is **{base_asset}{quote_asset}**.")

        c3 = st.columns(1)
        with c3[0]:
            st.write("**4. Choose Time interval**")
            st.caption("The strategy runs in a loop on a steady time interval. Based on the selected interval, the algorithm will focus on the short-term (**High-Frequency Trading**) or long-term (**Swing Trading**).")
            time_interval = st.pills("Time Interval", options=["1s", "1m", "5m", "15m", "30m", "1h", "4h", "12h", "1d"], default="1s")
            if time_interval is None:
                st.warning("No time interval selected.", icon=":material/warning:")
            else:
                time_int_dict = {'1s': '1 second', '1m': '1 minute', '5m': '5 minutes', '15m': '15 minutes',
                                 '30m': '30 minutes', '1h': '1 hour', '4h': '4 hours', '12h': '12 hours', '1d': '1 day'}
                st.info(f"The trading strategy algorithm will loop every **{time_int_dict[time_interval]}**.")

        c4 = st.columns(1)
        with c4[0]:
            st.write("**5. Choose Strategy Algorithm**")
            st.segmented_control("Strategy Algorithm Type", options=["All", "Trend Following", "Mean Reversion", "Breakout", "Momentum", "Swing Trading", "Scalping", "Volatility-Based", "ML Model"], default="All", disabled=True)
            algorithm = st.selectbox("Trading Strategies", options=["Bollinger Bands", "Exponential Moving Average (EMA) crossover", "RSI"])

            st.write("**Strategy Params**")
            strategy_params_dict = {}
            if algorithm == "Bollinger Bands":
                window = st.number_input("Window Size", value=20, min_value=1, max_value=1000)
                st_dev = st.number_input("Standard Deviation", value=2.0, min_value=0.0, max_value=4.0)
                strategy_params_dict["window"] = window
                strategy_params_dict["std_dev"] = st_dev

            elif algorithm == "Exponential Moving Average (EMA) crossover":
                short_window = st.number_input("Short Window Size", value=10, min_value=1, max_value=1000)
                long_window = st.number_input("Long Window Size", value=50, min_value=1, max_value=1000)
                strategy_params_dict["short_window"] = short_window
                strategy_params_dict["long_window"] = long_window
            elif algorithm == "RSI":
                rsi_period = st.number_input("RSI Period", value=14, min_value=1, max_value=100)
                buy_threshold = st.number_input("Buy Threshold", value=30, min_value=1, max_value=1000)
                sell_threshold = st.number_input("Sell Threshold", value=70, min_value=1, max_value=1000)
                strategy_params_dict["rsi_period"] = rsi_period
                strategy_params_dict["buy_threshold"] = buy_threshold
                strategy_params_dict["sell_threshold"] = sell_threshold
            else:
                st.warning("Invalid algorithm selected.", icon=":material/warning:")

            st.caption("Number of trades (pair of BUY-SELL orders) before the algorithm stops. The larger this value, the more the algorithm will run for.")
            trades_num = st.number_input("Number of trades", min_value=1, max_value=10, default=2, step=1)
        st.divider()
        st.caption("A **Backtesting** will evaluate the effectiveness of a trading strategy by running it against historical data to see how it would perform. The **evaluation results** will be shown, along with the option to deploy it.")
        backtesting_button = st.button("Run Backtesting", type="primary", icon=":material/query_stats:", disabled=True)
        # if backtesting_button:
        # post_strategy(exchange, quote_asset, quote_amount, base_asset, time_interval, algorithm, trades_num, strategy_params_dict, True)
        if st.button("Initiate Strategy", type="primary", icon=":material/send:"):
            post_strategy(exchange, quote_asset, quote_amount, base_asset, time_interval, algorithm, trades_num, strategy_params_dict)


else:
    html_content = """
    <div style="text-align: center; color: #5E5E5E; font-weight: bold; font-size: 24px;">
        <br>
        No Exchange API connected.
        <br>
    </div>
    """
    st.html(html_content)
    st.link_button("Go to Settings", "http://localhost:8501/settings", use_container_width=True, type="tertiary", icon=":material/settings:")