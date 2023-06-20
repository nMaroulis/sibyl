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


strat_status = st.radio('Deployed Strategy History Status:', options=['all', 'active', 'completed', 'partially_completed', 'cancelled'], index=0, horizontal=True)


import requests

if st.sidebar.button('Update History'):
    with st.spinner('Fetching latest Strategy History Status'):
        url='http://127.0.0.1:8000/broker/trade/order/status/update'
        res = requests.get(url)
        if res.status_code == 200:
            if "success" in res.json():
                st.sidebar.success(res.json())


url='http://127.0.0.1:8000/broker/trade/strategy/history?status='+strat_status
res = requests.get(url)
# st.write(res.text)
trade_strategies = res.json()

df_strategy = pd.DataFrame(columns=['Exchange', 'DateTime', 'buy_orderId', 'from_asset', 'to_asset', 'from_amount',
                                    'quantity_bought', 'from_price', 'DateTime [Sell]', 'sell_orderId', 'price_to_sell',
                                    'Order Type', 'Strategy', 'Status'], data=trade_strategies) # df_strategy['DateTime'] = pd.to_datetime(df_strategy['DateTime'], unit='s')

st.dataframe(df_strategy)


from plotly.express import bar

colors = {
    'active': '#50C878',
    'partially_completed': '#ADD8E6',
    'completed': '#0073CF',
    'cancelled': '#E34234'
}

status_counts = df_strategy['Status'].value_counts().reindex(['active', 'partially_completed', 'completed', 'cancelled'], fill_value=0)
fig = bar(status_counts, x=status_counts.index, y=status_counts.values,  color=status_counts.index, color_discrete_map=colors)
fig.update_layout(xaxis={'type': 'category'}, yaxis_title='Number of Occurrences')

st.plotly_chart(fig, config=dict(displayModeBar=False))
