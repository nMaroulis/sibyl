import streamlit as st
import requests
import plotly.graph_objects as go
from pandas import DataFrame, to_datetime

st.header('Home Page')

with st.form('Get Price'):
    cols = st.columns(3)
    with cols[0]:
        coin = st.selectbox(
            'Choose Coin',
            ('BTC', 'ETH', 'ADA'))
    with cols[1]:
        time_int = st.selectbox(
            'Choose Date Interval',
            ('1m', '5m', '15m', '30m', '1h', '4h', '12h', '1d', '3d', '1w', '1M'))
    with cols[2]:
        time_limit = st.number_input('Choose Sample Limit', value=500, min_value=2, max_value=10000)

    sumbit_button = st.form_submit_button('Submit')
    if sumbit_button:
        url = f"http://127.0.0.1:8000/coin/price_history/"+coin+"?interval="+time_int+"&limit=" + str(time_limit)
        response = requests.get(url)
        data = response.json()

        df = DataFrame()

        df['DateTime'] = [entry.get('Open Time') for entry in data]
        df['DateTime'] = to_datetime(df['DateTime'],unit='ms')
        df['Price'] = [entry.get('Open Price') for entry in data]


        fig = go.Figure(data=go.Scatter(x=df['DateTime'], y=df['Price']))
        fig.update_layout(title=f"Price History of ada",
                          xaxis_title="DateTime",
                          yaxis_title="Price (USDT)")
        st.plotly_chart(fig, use_container_width=True)