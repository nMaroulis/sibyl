import streamlit as st
from library.ui_elements import fix_page_layout
from library.strategy_helper.greedy import GreedyTrader


fix_page_layout('strategy')

st.markdown("""<h2 style='text-align: center;margin-top:0; padding-top:0;'>Trading Strategy</h2>""", unsafe_allow_html=True)

st.warning("Currently only one Active Strategy is supported.")

greedy_tab, oracle_tab, arb_tab, dca_tab, sibyl_tabl = st.tabs(['Greedy', 'Forecasting Model', 'Arbitrage Trading', 'DCA', 'Sibyl Algorithm'])

with greedy_tab:
    st.write('The **Greedy** algorithm (or **Scalping**) places a buy order immediately after it is initiated and sells after it has achieved a profit of X%. X is based on the parameters of the algorithm.')
    st.write('The current **Payoff ratio** based on Trading History using the Greedy Algorithm is *Not Available*')
    gt = GreedyTrader()
    gt.get_form()
with oracle_tab:
    st.write('TBA')
with arb_tab:
    st.write('TBA')
with dca_tab:
    st.write('TBA')
with sibyl_tabl:
    st.write('The Sibyl Algorithm uses ***Reinforcement Learning*** in order to automatically define the best Strategy, '
             'Time Period, Crypto Coin and Order amount and places the trade order when the agent decides.')
    st.markdown(""":red[TBA]""")