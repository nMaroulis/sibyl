import streamlit as st
from frontend.src.library.overview_helper.navigation import api_status_check
from frontend.src.library.ui_elements import fix_page_layout, set_page_title, col_style2
from frontend.src.library.spot_trade_helper.ui_elements import get_spot_trade_instructions, plot_orderbook
from frontend.src.library.spot_trade_helper.client import post_spot_trade
from frontend.src.library.spot_trade_helper.funcs import get_account_balance, get_pair_market_price
from frontend.src.library.analytics_helper.client import fetch_available_assets


fix_page_layout('spot trading')
set_page_title("Spot Trading")
st.html(col_style2)

st.caption("Expand instruction below 👇👇 to get instructions on how to place a new spot trade.")
get_spot_trade_instructions()

if "available_exchange_apis" not in st.session_state:
    with st.spinner("Checking API Availability Status..."):
        api_status_check()

if len(st.session_state["available_exchange_apis"]) > 0:
    if st.sidebar.button('Reset Trade', type='primary', use_container_width=True, icon=":material/reset_settings:"):
        st.cache_data.clear()
        st.rerun()

    st.session_state['trade_exchange_api'] = st.selectbox('Choose Exchange', options=st.session_state["available_exchange_apis"])

    st.divider()
    st.html("<h3 style='text-align: left;margin-bottom:0; padding-top:0;'>1. Asset Options 💰</h3>")
    with st.container(border=False):

        with st.spinner(f"Fetching available {st.session_state['trade_exchange_api']} asset pairs..."):
            asset_list = fetch_available_assets(st.session_state['trade_exchange_api'], quote_asset="all")

        col00, col01, col02 = st.columns(3)
        with col00:
            default_quote_index = list(asset_list.keys()).index("USDT") if "USDT" in asset_list.keys() else 0  # making USDT appear as preselected choice
            quote_asset = st.selectbox('Quote Asset', options=asset_list.keys(), index=default_quote_index)
            # st.caption("Currently only USDT is available as a Quote asset for Trading.")
        with col01:
            default_base_index = asset_list[quote_asset].index("BTC") if "BTC" in asset_list[quote_asset] else 0  # making BTC appear as preselected choice
            base_asset = st.selectbox('Base Asset:', options=asset_list[quote_asset], index=default_base_index)
        with col02:
            quantity = st.number_input('Quantity (Base Asset):', min_value=0.000001, step=0.000001, format="%.6f", value=10.000000)
            # st.segmented_control("Asset Quantity", options=["Base Asset", "Quote Asset (Cost-based)"], default="Base Asset")  # TODO

        if st.session_state['trade_exchange_api'] == "Coinbase" or st.session_state['trade_exchange_api'] == "Coinbase Sandbox":
            trading_pair = f"{base_asset}-{quote_asset}"
        else:
            trading_pair = base_asset+quote_asset

        # Get Base Asset price in Quote Asset and minimum order
        market_price = get_pair_market_price(quote_asset, base_asset, quantity)

        # show available balance
        get_account_balance(quote_asset, quantity, market_price)

        # ORDERBOOK
        show_orderbook = st.toggle("📖 Show Orderbook", value=False)
        if show_orderbook:
            plot_orderbook(st.session_state['trade_exchange_api'], quote_asset, base_asset, 10)

    st.html("""<h3 style='text-align: left;margin-bottom:0; padding-top:0;'>2. Trading Options 📈</h3>""")
    with st.container(border=False):

        col10 = st.columns(1)
        with col10[0]:
            order_type = st.selectbox(
                "Select Order Type: ",
                ["Market", "Limit", "Stop-Loss", "Stop-Loss Limit", "Take-Profit", "Take-Profit Limit", "Trailing Stop",
                 "OCO"]
            )
            st.caption("Select between a Limit or Market order. Limit orders are added to the order book, often with lower 'maker' fees, while Market orders are matched instantly with existing orders, incurring 'taker' fees.")
            side = st.segmented_control("Order Side", options=["Buy", "Sell"], default="Buy")

        price = None
        stop_price = None
        take_profit_price = None
        col20, col21, col22 = st.columns(3)
        with col20:

            if order_type in ["Limit", "Stop-Loss Limit", "Take-Profit Limit"]:
                price = st.number_input("Limit Price:", min_value=0.0001, step=0.0001, format="%.4f")
            else:
                st.number_input("Limit Price:", min_value=0.0001, step=0.0001, format="%.4f", disabled=True)
        with col21:
            if order_type in ["Stop-Loss", "Stop-Loss Limit", "Trailing Stop"]:
                stop_price = st.number_input("Stop Price:", min_value=0.0001, step=0.0001, format="%.4f")
            else:
                st.number_input("Stop Price:", min_value=0.0001, step=0.0001, format="%.4f", disabled=True)
        with col22:
            if order_type in ["Take-Profit", "Take-Profit Limit"]:
                take_profit_price = st.number_input("Take Profit Price:", min_value=0.0001, step=0.0001, format="%.4f")
            else:
                st.number_input("Take Profit Price:", min_value=0.0001, step=0.0001, format="%.4f", disabled=True)

        col30  = st.columns(1)
        with col30[0]:
            st.caption("If percentage is enable, the **Stop-Loss** and **Take-Profit** will be based on percentages and not the actual value of the Base Asset.")
            st.toggle("Percentage [%]", value=False)
            st.caption("If enabled, the order will only be posted as a maker order, ensuring it adds liquidity.")
            post_only = st.toggle("Post-Only Order", value=False)

        col40, col41 = st.columns(2)
        with col40:
            time_in_force = st.pills("Time in Force:", ["GTC", "IOC", "FOK"], default="GTC")
            with st.popover("What is time in force?", icon=":material/help:"):
                st.write("""
                These are Time in Force (TIF) options, which determine how long an order remains active before it is executed or canceled. They are commonly used in trading platforms, including Binance.
                Explanation of TIF options:
                1. TIME_IN_FORCE_GTC (Good-Til-Canceled)
                - The order remains active until it is fully executed or manually canceled.
                - Suitable for Limit orders, ensuring they stay open until filled at the specified price.
                - Example: If you place a limit order to buy BTC at $50,000, it will stay open until someone is willing to sell at that price.
                2. TIME_IN_FORCE_IOC (Immediate-Or-Cancel)
                - The order is executed immediately (fully or partially), and any unfilled portion is canceled.
                - Useful for traders who want quick execution without waiting.
                - Example: If you try to buy 1 BTC at $50,000, but only 0.7 BTC is available at that price, it will buy 0.7 BTC and cancel the remaining 0.3 BTC.
                3. TIME_IN_FORCE_FOK (Fill-Or-Kill)
                - The order must be executed in full immediately, or it is completely canceled.
                - Ensures you either get your exact order amount or nothing at all.
                - Example: If you place an FOK order to buy 1 BTC at $50,000, but only 0.9 BTC is available at that price, the entire order is canceled.""")
        with col41:
            iceberg_qty = st.number_input("Iceberg Quantity (Optional):", min_value=0.0, step=0.0001, format="%.4f")

    st.html("""<h3 style='text-align: left;margin-bottom:0; padding-top:0;'>3. Exchange Parameters ⚙️</h3>""")
    with st.container(border=False):
        col10 = st.columns(1)
        with col10[0]:
            st.caption("The Swap (Binance Convert API) enables trading with 0 fees. If not available, choose Trade option. Read the instructions at the top of the page to minimize the fees.")
            with st.spinner('Checking Swap Availability...'):
                swap_status = {} # check_swap_status(st.session_state['trade_exchange_api'])
                if "success" in swap_status:
                    st.session_state['order_type'] = st.radio('Choose Order Type', options=['Trade', 'Swap'], index=0, horizontal=True)
                    st.success(swap_status)
                else:
                    st.session_state['order_type'] = st.segmented_control('Choose Buy/Sell Order Type', options=['Trade', 'Swap'], default='Trade', disabled=True)
                    st.warning('🔁 Binance Convert API is not enabled on your Account, only Trade option can be used!')

    st.divider()
    st.caption(
        f"By placing the order, a **test order** will be first executed. If it is successful, then the actual order will be sent to the {st.session_state['trade_exchange_api']} to be executed. If the test order fails, you'll get the trade error message.")
    # Execute trade
    if st.button("Place Order", type="primary"):
        with st.spinner("Sending Test Order..."):
            test_res = post_spot_trade(True, st.session_state['trade_exchange_api'], order_type, quote_asset, base_asset, side, quantity,
                                       price, stop_price, take_profit_price, time_in_force)
        if test_res is None or "status" not in test_res.keys():
            st.error("Something went wrong when parsing the server response.", icon=":material/warning:")
        else:
            if test_res["status"] == "success":
                st.success("Test Order was **validated**, your Trade Order being placed right now...",
                           icon=":material/task_alt:")
                with st.spinner("Placing Order..."):
                    res = post_spot_trade(False, st.session_state['trade_exchange_api'], order_type, quote_asset, base_asset, side,
                                               quantity,
                                               price, stop_price, take_profit_price, time_in_force)
                    if res is None or "status" not in res.keys():
                        st.error("Something went wrong when parsing the server response.", icon=":material/warning:")
                    else:
                        if res["status"] == "success":
                            st.success("Order was **placed** successfully and added to the TradeHistory DB, please find API response below.", icon=":material/task_alt:")
                            st.link_button("You can find the SPOT order in the Trading History tab.", "http://localhost:8501/trading_report ", type="primary",
                                        icon=":material/youtube_searched_for:")
                            st.json(res["message"])
                            st.toast("Your Trade Order has been placed successfully.", icon="✅")
                        else:
                            st.warning(f"Order is **invalid**. Error message {res["message"]}", icon=":material/warning:")
            else:
                st.warning(f"Test Order is **invalid**. Error message {test_res["message"]}", icon=":material/warning:")
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

