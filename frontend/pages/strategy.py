import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout
from frontend.src.library.strategy_helper.greedy import GreedyTrader
from frontend.src.library.strategy_helper.client import check_swap_status
from frontend.src.library.strategy_helper.funcs import get_strategy_instructions
from frontend.src.library.strategy_helper.client import fetch_trade_info_minimum_order, send_strategy
from frontend.src.library.analytics_helper.client import fetch_available_coins
from frontend.src.library.crypto_dictionary_assistant import get_crypto_name_regex
import time

fix_page_layout('strategy')

st.markdown("""<h2 style='text-align: center;margin-top:0; padding-top:0;'>Trading Strategy</h2>""", unsafe_allow_html=True)
st.caption("Make sure to enable the Binance Convert API in order to have 0 fees. If the backend server doesn't find a valid Convert API, the standard buy/sell order will be used. In that case make sure to have BNB in your account in order to minimize the fees.")
st.caption("Expand instruction below 👇👇 to get instructions on how to deploy a new strategy.")


get_strategy_instructions()

# st.sidebar.caption('Reset Strategy:')
if st.sidebar.button('Reset Page', type='primary', use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.divider()
st.markdown("""<h4 style='text-align: left;margin-top:0; padding-top:0;'>1. Asset Options 💰</h4>""", unsafe_allow_html=True)
with st.container(border=True):
    col00, col01, col02 = st.columns(3)
    with col00:
        st.session_state['buy_amount'] = st.number_input('Buying Amount:', min_value=1.0, max_value=100000.0, value=50.0)
    with col01:
        st.session_state['from_coin'] = st.selectbox('Base Asset (from)', options=['USDT'], disabled=True)
        st.caption("Currently only USDT is available as an Asset to use for Trading.")
    with col02:
        crypto_list = fetch_available_coins()
        crypto_list.sort()
        crypto_list.insert(0, 'Auto')
        st.session_state['target_coin'] = st.selectbox('Quote Asset (to):', options=crypto_list, index=1)
        st.caption("Currently only USDT is available as an Asset to use for Trading.")

    if st.session_state['target_coin'] != 'Auto':
        pair_symbol = get_crypto_name_regex(st.session_state['target_coin']) + st.session_state['from_coin']
        min_order_limit = fetch_trade_info_minimum_order(pair_symbol)
        if st.session_state['buy_amount'] >= min_order_limit:
            st.success("The **Minimum buy order Limit** of **" + str(min_order_limit) + "** for the " + pair_symbol + " pair is satisfied!")
        else:
            st.error("The **Minimum Buy Order Limit** of **" + str(min_order_limit) + "** for the " + pair_symbol + " pair is NOT satisfied.")

st.markdown("""<h4 style='text-align: left;margin-top:1em; padding-top:0;'>2. Trading Options 📈</h4>""", unsafe_allow_html=True)
with st.container(border=True):
    st.caption("The Swap (Binance Convert API) enables trading with 0 fees. If not available, choose Trade option. Read the instructions at the top of the paeg to minimize the fees.")
    with st.spinner('Checking Swap Availability...'):
        swap_status = check_swap_status()
        if "success" in swap_status:
            st.session_state['order_type'] = st.radio('Choose Buy/Sell Order Type', options=['Trade', 'Swap'], index=0, horizontal=True)
            st.success(swap_status)
        else:
            st.session_state['order_type'] = st.radio('Choose Buy/Sell Order Type', options=['Trade', 'Swap'], index=0, horizontal=True, disabled=True)
            st.warning('🔁 Binance Convert API is not enabled on your Account, only Trade option can be used!')

    col10, col11 = st.columns(2)
    with col10:
        st.session_state['timeframe'] = st.selectbox('Timeframe:', options=['Auto', '15 Minutes', '30 Minutes', '1 Hour', '6 Hours', '12 Hours',
                                               '1 Day', '3 Days', '1 Week', '1 Month', '6 Months'], index=0)
        st.caption("if option is left to **Auto**, the algorithm will define an automatic Time Horizon")
    with col11:
        st.session_state['stop_loss'] = st.number_input('Stop-Loss [%]:', min_value=0, max_value=100, value=0)
        st.caption("if option is left to **0**, the **Algorithm** will define an automatic Stop Loss")

st.markdown("""<h4 style='text-align: left;margin-top:1em; padding-top:0;'>3. Algorithm ⚙️</h4>""", unsafe_allow_html=True)
algo_choice = st.selectbox('Choose Algorithm', options=['Greedy', 'Forecasting Model', 'Arbitrage Trading', 'DCA', 'Sibyl Algorithm'])
with st.container(border=True):
    if algo_choice == 'Greedy':
        strategy_object = GreedyTrader(order_type=st.session_state['order_type'])
        strategy_object.get_form()
    elif algo_choice == 'Sibyl Algorithm':
        st.write('The Sibyl Algorithm uses ***Reinforcement Learning*** in order to automatically define the best Strategy, '
                 'Time Period, Crypto Coin and Order amount and places the trade order when the agent decides.')
        st.markdown(""":red[TBA]""")
    else:
        st.markdown(""":red[TBA]""")

# SUBMIT
submit = st.button('Initiate Strategy')
if submit:
    with st.spinner('Sending Strategy to Server....'):
        res = strategy_object.submit_strategy()
        if "error" in res:
            st.error('Server Response ' + str(res))
            st.toast('⛔ Trade was NOT Executed!')
        else:
            st.toast('✅ Trade was successfully Executed!')
            st.success('Server Response ' + str(res))
            with st.spinner('Refreshing Page:'):
                time.sleep(4)
                st.rerun()
