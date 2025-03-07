import streamlit as st
from frontend.src.library.overview_helper.navigation import api_status_check
from frontend.src.library.ui_elements import fix_page_layout, set_page_title, col_style2
from frontend.src.library.spot_trade_helper.ui_elements import get_spot_trade_instructions
from frontend.src.library.spot_trade_helper.client import post_spot_trade_test


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
            quantity = st.number_input('Quantity:', min_value=0.0001, step=0.0001, format="%.4f", value=10.0000)
        with col01:
            from_coin = st.selectbox('Base Asset (from)', options=['USDT'], disabled=True)
            st.caption("Currently only USDT is available as an Asset to use for Trading.")
        with col02:
            # crypto_list = fetch_available_coins(st.session_state['trade_exchange_api'])
            crypto_list = ["BTC"]
            crypto_list.sort()
            to_coin = st.selectbox('Quote Asset (to):', options=crypto_list, index=0)
        trading_pair = to_coin+from_coin
        st.write(f"""
        - **Trading pair**: {trading_pair}
        - You'll trade {quantity} {from_coin} for X {to_coin}""")
        # pair_symbol = get_crypto_name_regex(st.session_state['target_coin']) + st.session_state['from_coin']
        # min_order_limit = fetch_trade_info_minimum_order(st.session_state['trade_exchange_api'], pair_symbol)
        # if st.session_state['buy_amount'] >= min_order_limit:
        #     st.success("The **Minimum buy order Limit** of **" + str(min_order_limit) + "** for the " + pair_symbol + " pair is satisfied!")
        # else:
        #     st.error("The **Minimum Buy Order Limit** of **" + str(min_order_limit) + "** for the " + pair_symbol + " pair is NOT satisfied.")

    st.html("""<h3 style='text-align: left;margin-bottom:0; padding-top:0;'>2. Trading Options 📈</h3>""")
    with st.container(border=False):

        side = st.segmented_control("Order Side", options=["Buy", "Sell"], default="Buy")
        col10 = st.columns(1)
        with col10[0]:
            order_type = st.selectbox(
                "Select Order Type: ",
                ["Market", "Limit", "Stop-Loss", "Stop-Loss Limit", "Take-Profit", "Take-Profit Limit", "Trailing Stop",
                 "OCO"]
            )
            st.caption("Select between a Limit or Market order. Limit orders are added to the order book, often with lower 'maker' fees, while Market orders are matched instantly with existing orders, incurring 'taker' fees.")

        price = None
        stop_price = None
        take_profit_price = None
        col20, col21, col22 = st.columns(3)
        with col20:

            if order_type in ["Limit", "Stop-Loss Limit", "Take-Profit Limit"]:
                price = st.number_input("Limit Price:", min_value=0.0001, step=0.0001, format="%.4f")
            else:
                st.number_input("Limit Price:", min_value=0.0001, step=0.0001, format="%.4f", disabled=True)
            st.toggle("Percentage [%]", value=False)
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

        col30, col31, col32 = st.columns(3)
        with col30:
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

        with col31:
            post_only = st.toggle("Post-Only Order", value=False)
            st.caption("If enabled, the order will only be posted as a maker order, ensuring it adds liquidity.")
        with col32:
            iceberg_qty = st.number_input("Iceberg Quantity (Optional):", min_value=0.0, step=0.0001, format="%.4f")

# Execute trade
if st.button("Place Test Order", type="primary"):
    res = post_spot_trade_test(st.session_state['trade_exchange_api'], order_type, trading_pair, side, quantity, price, stop_price, take_profit_price, time_in_force)
    if res is None or "status" not in res.keys():
        st.error("Something went wrong when parsing the server response.")
    else:
        if res["status"] == "success":
            st.success("Order is **valid** and ready to be placed.")
            if st.button("Place Spot Order", type="primary"):
                st.write("nice")
        else:
            st.warning(f"Order is **invalid**. Error message {res["message"]}")
