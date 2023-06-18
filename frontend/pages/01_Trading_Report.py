import pandas as pd
import streamlit as st
from library.ui_elements import fix_page_layout


fix_page_layout('Report')

st.markdown("""<h2 style='text-align: center;margin-top:0; padding-top:0;'>Trading Report</h2>""", unsafe_allow_html=True)

th_tab, vs_tab = st.tabs(['Trading History', 'Visual Inspection'])

with th_tab:
    st.write('Trading History Report')
with vs_tab:
    st.write('Visual Inspection')


st.radio('Deployed Strategy History', options=['all', 'active', 'inactive'], index=0, horizontal=True)

import requests

url='http://127.0.0.1:8000/broker/trade/order/active'
res = requests.get(url)
# st.write(res.text)
trade_strategies = res.json()

df_strategy = pd.DataFrame(columns=['Exchange', 'DateTime', 'buy_orderId', 'from_asset', 'to_asset', 'from_amount',
                                    'quantity_bought', 'from_price', 'DateTime [Sell]', 'sell_orderId', 'price_to_sell',
                                    'Order Type', 'Strategy', 'Status'], data=trade_strategies)
df_strategy['DateTime'] = pd.to_datetime(df_strategy['DateTime'], unit='s')
st.dataframe(df_strategy)
