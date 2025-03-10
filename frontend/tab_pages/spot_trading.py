import streamlit as st
from frontend.src.library.overview_helper.navigation import api_status_check
from frontend.src.library.ui_elements import fix_page_layout, set_page_title, col_style2
from frontend.src.library.spot_trade_helper.ui_elements import get_spot_trade_instructions
from frontend.src.library.spot_trade_helper.client import post_spot_trade_test, fetch_minimum_trade_value, fetch_current_asset_price
from frontend.src.library.analytics_helper.client import fetch_available_coins


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
        col00, col01, col02 = st.columns(3)
        with col00:
            quote_asset = st.selectbox('Quote Asset', options=['USDT'], disabled=True)
            st.caption("Currently only USDT is available as a Quote asset for Trading.")
        with col01:
            crypto_list = fetch_available_coins(st.session_state['trade_exchange_api'], quote_asset=quote_asset)
            crypto_list.sort()
            base_asset = st.selectbox('Base Asset:', options=crypto_list, index=0)
        with col02:
            quantity = st.number_input('Quantity:', min_value=0.0001, step=0.0001, format="%.4f", value=10.0000)
        st.toggle("Quote Market Order", value=False)  # TODO

        trading_pair = base_asset+quote_asset
        current_price = fetch_current_asset_price(st.session_state['trade_exchange_api'], trading_pair)
        st.info(f"""
        - **Trading pair**: {trading_pair}
        - **{base_asset} Current price**: {current_price} USDT
        - You'll trade {round(quantity*current_price,4)} {quote_asset} for {quantity} {base_asset}""")

        min_trade_limit = fetch_minimum_trade_value(st.session_state['trade_exchange_api'], trading_pair)
        if quantity*current_price >= min_trade_limit:
            st.success("The **minimum trade value limit** of **" + str(min_trade_limit) + "** for the " + trading_pair + " pair is satisfied!", icon=":material/task_alt:")
        else:
            st.error("The **minimum trade value limit** of **" + str(min_trade_limit) + "** for the " + trading_pair + " pair is NOT satisfied.", icon=":material/warning:")

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

st.divider()
st.caption(f"By placing the order, a **test order** will be first executed. If it is successful, then the actual order will be sent to the {st.session_state['trade_exchange_api']} to be executed. If the test order fails, you'll get the trade error message.")
# Execute trade
if st.button("Place Order", type="primary"):
    with st.spinner("Sending Test Order..."):
        res = post_spot_trade_test(st.session_state['trade_exchange_api'], order_type, trading_pair, side, quantity, price, stop_price, take_profit_price, time_in_force)
    if res is None or "status" not in res.keys():
        st.error("Something went wrong when parsing the server response.", icon=":material/warning:")
    else:
        if res["status"] == "success":
            st.success("Test Order was **validated**, your Trade Order being placed right now...", icon=":material/task_alt:")
            with st.spinner("Placing Order..."):
                st.write("OK")
                st.toast("Order has been placed.", icon=":material/task_alt:")
        else:
            st.warning(f"Order is **invalid**. Error message {res["message"]}", icon=":material/warning:")
