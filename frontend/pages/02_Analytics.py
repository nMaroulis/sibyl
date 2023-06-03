import streamlit as st
import requests
from pandas import DataFrame, to_datetime
from library.crypto_dictionary_assistant import get_crypto_coin_dict
from plotly.express import imshow
from library.analytics_helper.plots import price_history_plot
from library.ui_elements import fix_padding_top_and_footer

st.set_page_config(layout="wide")
fix_padding_top_and_footer()

st.markdown("""<h1 style='text-align: center;margin-top:0; padding-top:0;'>Analytics</h1>""", unsafe_allow_html=True)

ph_tab, ch_tab = st.tabs(['Price History', 'Correlation Heatmap'])


with ph_tab:  # Price History
    with st.form('Get Price'):
        cols = st.columns(3)
        with cols[0]:
            coin = st.selectbox(label='Choose Coin',
                                options=list(get_crypto_coin_dict().keys()))  # get the keys from the coin dict
        with cols[1]:
            time_int = st.selectbox(
                'Choose Date Interval',
                ('1m', '5m', '15m', '30m', '1h', '4h', '12h', '1d', '3d', '1w', '1M'))
        with cols[2]:
            time_limit = st.number_input('Choose Sample Limit', value=500, min_value=2, max_value=10000)

        plot_type = st.radio('Plot type', options=['Line Plot', 'Candle Plot'], index=0, horizontal=True)

        sumbit_button = st.form_submit_button('Submit')
        if sumbit_button:
            price_history_plot(coin, time_int, time_limit, plot_type)


with ch_tab:  # Correlation Heatmap
    st.header('Correlation Heatmap')
    st.write('Generate a Correlation Heatmap for the selected Crypto Coins')
    with st.form('Correlation Heatmap'):
        coins = st.multiselect(label='Choose Coins to Correlate', options=list(get_crypto_coin_dict().keys()), max_selections=100)  # get the keys from the coin dict
        cols = st.columns(2)
        with cols[0]:
            time_int = st.selectbox(
                'Choose Date Interval',
                ('1m', '5m', '15m', '30m', '1h', '4h', '12h', '1d', '3d', '1w', '1M'))
        with cols[1]:
            time_limit = st.number_input('Choose Sample Limit', value=500, min_value=2, max_value=10000)
        st.radio('Type of Correlation Formula', options=['pearson', 'spearman', 'Distance', 'MIC', 'Regression Coefficients'], index=0, horizontal=True, disabled=True, help='Feature coming soon')
        sumbit_button = st.form_submit_button('Submit')
        if sumbit_button:
            df = DataFrame()

            for coin in coins:
                url = f"http://127.0.0.1:8000/coin/price_history/" + get_crypto_coin_dict().get(
                    coin) + "?interval=" + time_int + "&limit=" + str(time_limit)
                response = requests.get(url)
                data = response.json()

                df[coin] = [entry.get('Open Price') for entry in data]

            df_corr = df.corr(method='pearson')
            fig = imshow(df_corr, text_auto=True, aspect="auto", color_continuous_scale='RdBu_r')
            st.plotly_chart(fig, use_container_width=True)
