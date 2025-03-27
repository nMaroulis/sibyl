import pandas as pd
import streamlit as st
from frontend.src.library.overview_helper.client import fetch_account_spot
from frontend.src.library.overview_helper.navigation import api_status_check
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.src.library.strategy_helper.launcher_helper import get_strategy_instructions, strategy_params_form, backtest_evaluation_results
from frontend.src.library.ui_elements import col_style2
from frontend.src.library.analytics_helper.client import fetch_available_assets
from frontend.src.library.strategy_helper.client import post_strategy, get_available_strategies
from frontend.src.library.strategy_helper.console_helper import static_strategy_plot


fix_page_layout('strategy')
set_page_title("Trading Strategy Launcher")
st.html(col_style2)

st.caption("Click the button below 👇👇 to get information on the available strategies.")
if st.button("Strategies Wiki", icon=":material/menu_book:", type="primary"):
    get_strategy_instructions()

if "available_exchange_apis" not in st.session_state:
    with st.spinner("Checking API Availability Status..."):
        api_status_check()

if st.session_state["available_exchange_apis"]:
    st.divider()
    with st.container(border=False):
        c00 = st.columns(1)
        with c00[0]:
            st.write("**1. Exchange**")
            exchange = st.selectbox('Choose Exchange', options=st.session_state["available_exchange_apis"])

        c0, c1 = st.columns(2)
        with c0:
            balance = fetch_account_spot(exchange.lower().replace(" ", "_"))
            balance = {asset: price["free"] for asset, price in balance["spot_balances"].items()}
            st.write("**2. Quote Asset**")
            st.caption("Choose the **Quote Asset** which will be used in this strategy. Below you'll see all the assets you have available in your account and the corresponding markets you can deploy the strategy.")
            default_quote_index = list(balance.keys()).index("USDT") if "USDT" in balance.keys() else 0  # making USDT appear as preselected choice
            quote_asset = st.selectbox('Quote Asset', options=balance.keys(), index=default_quote_index)
            st.metric("Available Balance", f"{balance[quote_asset]} {quote_asset}")
        with c1:
            st.write("**3. Quote Amount**")
            st.caption(f"Choose the Quote amount you want to trade on this strategy. Each order sent to the {exchange} API will define the quote_quantity and not the base.")
            st.warning("**Warning**: Choose only what you can afford to lose, as the whole Quote amount is at risk.", icon=":material/warning:")
            quote_amount = st.number_input("Quote Amount", min_value=0.0, max_value=balance[quote_asset])

        c2, c3 = st.columns(2)
        with c2:
            st.write("**4. Base Asset**")
            st.caption(f"Choose the Base Asset. The available base assets correspond to the selected quote asset and the available markets at {exchange}.")
            base_assets = fetch_available_assets(exchange, quote_asset)
            base_asset = st.selectbox('Base Asset', options=base_assets[quote_asset])
            if base_asset:
                st.info(f"The selected market for this strategy is **{base_asset}{quote_asset}**.")
            else:
                st.warning("No base asset selected.", icon=":material/warning:")
        with c3:
            st.write("**5. Time interval**")
            st.caption("The strategy runs in a loop on a steady time interval. Based on the selected interval, the algorithm will focus on the short-term (**High-Frequency Trading**) or long-term (**Swing Trading**).")
            time_interval = st.pills("Time Interval", options=["1s", "15s", "1m", "5m", "15m", "30m", "1h", "4h", "12h", "1d"], default="1m")
            if time_interval is None:
                st.warning("No time interval selected.", icon=":material/warning:")
            else:
                time_int_dict = {'1s': '1 second', '15s': '15 seconds', '1m': '1 minute', '5m': '5 minutes', '15m': '15 minutes',
                                 '30m': '30 minutes', '1h': '1 hour', '4h': '4 hours', '12h': '12 hours', '1d': '1 day'}
                st.info(f"The trading strategy algorithm will loop every **{time_int_dict[time_interval]}**.")

        c4 = st.columns(1)
        with c4[0]:
            st.write("**6. Strategy Algorithm**")
            st.segmented_control("Strategy Algorithm Type", options=["All", "Trend Following", "Mean Reversion", "Breakout", "Momentum", "Swing Trading", "Scalping", "Volatility-Based", "ML Model"], default="All", disabled=True)
            strategy = st.selectbox("Trading Strategies", options=get_available_strategies())

            strategy_params_dict = strategy_params_form(strategy)
            st.divider()

        c5 = st.columns(1)
        with c5[0]:
            st.write("**7. Strategy Runtime Parameters**")
            st.caption("**(7.1)** Number of trades (**pair of BUY-SELL orders**) before the algorithm stops. The larger this value, the more the algorithm will run for.")
            trades_num = st.slider("Number of trades", min_value=1, max_value=10, value=2)
            st.caption("**(7.2)** The **Kline dataset size** indicates the size of the dataset that the strategy algorithm uses as input. "
                       "This must depend on the selected strategy. For example if 200 is chosen for '1m' interval, the strategy will consider the last 200 minute klines to make its action decision.")
            dataset_size = st.number_input("Dataset Size", min_value=1, max_value=1000, value=400, step=1, disabled=True)
            st.caption("**(7.3)** Trade order Parameters")
            st.pills("Order Type", options=["Market", "Limit"], default="Market", disabled=True)
            c6, c7, c8 = st.columns(3)
            with c6:
                st.number_input("Maximum **Slippage** Percentage (%)", min_value=0.0, max_value=100.0, value=1.0, disabled=True)
            with c7:
                st.number_input("**Stop-Loss** Percentage (%)", min_value=0.0, max_value=100.0, value=0.0, disabled=True)
            with c8:
                st.number_input("**Take-Profit** Percentage (%)", min_value=0.0, max_value=100.0, value=0.0, disabled=True)
        st.divider()
        st.caption("The **Backtesting** will evaluate the effectiveness of the selected trading strategy by running it against historical data to see how it would perform. The **evaluation results** will be shown.")
        valid_request_flag = True
        if quote_asset is None:
            st.warning("No **quote asset** provided.", icon=":material/warning:")
            valid_request_flag = False
        if quote_amount is None or quote_amount <= 0:
            st.warning("Please choose a valid **quote amount**.", icon=":material/warning:")
            valid_request_flag = False
        if base_asset is None:
            st.warning("No **base asset** provided.", icon=":material/warning:")
            valid_request_flag = False
        if time_interval is None:
            st.warning("No **time interval** provided.", icon=":material/warning:")
            valid_request_flag = False
        if strategy_params_dict is None:
            st.warning("No **strategy algorithm** provided.", icon=":material/warning:")
            valid_request_flag = False

        if valid_request_flag:
            # BACKTESTING
            if time_interval == "15s":
                st.warning("Backtesting is not currently available for the **15 second interval**", icon=":material/warning:")
            else:
                if st.button("Run Backtesting", key="backtesting_button", type="secondary", icon=":material/query_stats:",
                             use_container_width=True):
                    with st.spinner("Running Backtesting..."):
                        res = post_strategy(exchange, quote_asset, quote_amount, base_asset, time_interval, strategy,
                                            trades_num,
                                            dataset_size, strategy_params_dict, True)
                    if res is not None:
                        st.html("<h4 style='text-align: left;margin-top:0.1em; margin-bottom:0.1em; padding:0;color:#5E5E5E'>Backtesting Evaluation Metrics</h4>")
                        if len(res["metrics"]) > 0:
                            backtest_evaluation_results(res["metrics"])
                        else:
                            st.warning("No metrics available since no BUY or SELL orders were made by the strategy.", icon=":material/troubleshoot:")
                        st.html("<h4 style='text-align: left;margin-top:0.1em; margin-bottom:0.1em; padding:0;color:#5E5E5E'>Strategy Action Plot</h4>")
                        st.caption("The algorithm might have decided more BUY, SELL order in between that are invalid due to the fact that two or more consecutive BUY or SELL orders are not allowed.")
                        static_strategy_plot(pd.DataFrame(res["logs"]), True)
                    else:
                        st.error("Failed to get Backtesting results. See logs for error.", icon=":material/report:")

            # STRATEGY DEPLOYMENT
            if st.button("Initiate Strategy", key="deploy_strategy_button", type="primary", icon=":material/rocket_launch:", use_container_width=True):
                with st.spinner("Deploying Strategy"):
                    res = post_strategy(exchange, quote_asset, quote_amount, base_asset, time_interval, strategy, trades_num, dataset_size, strategy_params_dict)
                if res is not None:
                    st.success("Strategy has been successfully deployed.", icon=":material/rocket_launch:")
                    st.toast("Strategy has been successfully deployed.", icon="🚀")
                    st.link_button("Navigate to the **Strategy Console** to view the progress", "http://localhost:8501/strategy_console", icon=":material/browse_activity:")
                else:
                    st.error("Failed to deploy strategy. See logs for error.", icon=":material/report:")
        else:
            st.button("Run Backtesting", key="backtesting_button", type="primary", icon=":material/query_stats:",
                      use_container_width=True, disabled=True)
            st.button("Initiate Strategy", type="primary", icon=":material/send:", disabled=True, use_container_width=True)

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