import streamlit as st
from frontend.src.library.settings_helper.navigation import exchange_api_status_check
from frontend.src.library.ui_elements import fix_page_layout, set_page_title, col_style2
from frontend.src.library.spot_trade_helper.ui_elements import get_spot_trade_instructions, plot_orderbook, time_in_force_instructions
from frontend.src.library.spot_trade_helper.funcs import get_account_balance, get_pair_market_price, submit_order
from frontend.src.library.analytics_helper.client import fetch_available_assets

from frontend.src.library.spot_trade_helper.client import fetch_symbol_info
import math


fix_page_layout('spot trading')
set_page_title("Spot Trading")
st.html(col_style2)

st.caption("Expand instruction below 👇👇 to get instructions on how to place a new spot trade.")
get_spot_trade_instructions()

if "available_exchange_apis" not in st.session_state:
    with st.spinner("Checking API Availability Status..."):
        exchange_api_status_check()

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
        with col01:
            default_base_index = asset_list[quote_asset].index("BTC") if "BTC" in asset_list[quote_asset] else 0  # making BTC appear as preselected choice
            base_asset = st.selectbox('Base Asset:', options=asset_list[quote_asset], index=default_base_index)
        with col02:
            # GET INFORMATION about the symbol, base and quote asset precision and min_trade_value
            symbol_info = fetch_symbol_info(exchange=st.session_state['trade_exchange_api'], quote_asset=quote_asset, base_asset=base_asset)
            base_format = f"%.{int(-math.log10(symbol_info["base_precision"]))}f"
            quantity = st.number_input('Quantity (Base Asset):', min_value=symbol_info["base_precision"], step=symbol_info["base_precision"], format=base_format)
            st.caption(f"The precision is fetched by the {st.session_state['trade_exchange_api']} API to match the minimum accepted Base asset precision for Trading.")
            # st.segmented_control("Asset Quantity", options=["Base Asset", "Quote Asset (Cost-based)"], default="Base Asset")  # TODO


        # Get Base Asset price in Quote Asset and minimum order
        market_price = get_pair_market_price(quote_asset, base_asset, quantity, symbol_info["min_trade_value"])

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
                price = st.number_input("Limit Price:", min_value=symbol_info["quote_precision"], step=symbol_info["quote_precision"], format=base_format)
            else:
                st.number_input("Limit Price:", min_value=symbol_info["quote_precision"], step=symbol_info["quote_precision"], format=base_format, disabled=True)
        with col21:
            if order_type in ["Stop-Loss", "Stop-Loss Limit", "Trailing Stop"]:
                stop_price = st.number_input("Stop-Loss Price:", min_value=symbol_info["quote_precision"], step=symbol_info["quote_precision"], format=base_format)
            else:
                st.number_input("Stop-Loss Price:", min_value=symbol_info["quote_precision"], step=symbol_info["quote_precision"], format=base_format, disabled=True)
        with col22:
            if order_type in ["Take-Profit", "Take-Profit Limit"]:
                take_profit_price = st.number_input("Take Profit Price:", min_value=symbol_info["quote_precision"], step=symbol_info["quote_precision"], format=base_format)
            else:
                st.number_input("Take Profit Price:", min_value=symbol_info["quote_precision"], step=symbol_info["quote_precision"], format=base_format, disabled=True)

        col30  = st.columns(1)
        with col30[0]:
            st.caption("If percentage is enable, the **Stop-Loss** and **Take-Profit** will be based on percentages and not the actual value of the Base Asset.")
            st.toggle("Percentage [%]", value=False)
            st.caption("If enabled, the order will only be posted as a maker order, ensuring it adds liquidity.")
            post_only = st.toggle("Post-Only Order", value=False)

        col40, col41 = st.columns(2)
        with col40:
            time_in_force = st.pills("Time in Force:", ["GTC", "IOC", "FOK"], default="GTC")
            time_in_force_instructions()
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
    if st.button("Place Order", type="primary", icon=":material/send:"):
        submit_order(order_type, quote_asset, base_asset, side, quantity, price, stop_price, take_profit_price, time_in_force)
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

