import pandas as pd
import streamlit as st
from library.ui_elements import fix_page_layout
from library.history_helper.funcs import sidebar_update_history, trading_history_table, get_status_barplot


fix_page_layout('Report')
st.markdown("""<h2 style='text-align: center;margin-top:0; padding-top:0;'>Trading Report</h2>""", unsafe_allow_html=True)

strat_status = st.sidebar.radio('Deployed Strategy History Status:', options=['all', 'active', 'completed', 'partially_completed', 'cancelled'], index=0)
sidebar_update_history()
st.sidebar.selectbox('Exchange', options=['All', 'Binance'], disabled=True)

th_tab, vs_tab = st.tabs(['Trading History', 'Visual Inspection'])
with th_tab:
    st.markdown("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Trading History Table</h5>""",
                unsafe_allow_html=True)
    df = trading_history_table(strat_status)
with vs_tab:
    st.markdown("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Trading History Bar Plot</h5>""",
                unsafe_allow_html=True)
    get_status_barplot(df['Status'])

