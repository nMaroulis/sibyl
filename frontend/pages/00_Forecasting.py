import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout
from frontend.src.library.analytics_helper.client import fetch_available_coins
from frontend.src.library.analytics_helper.plots import price_history_plot
from frontend.src.library.forecasting_helper.plots import show_line_plot_with_analytics, show_analytics
from frontend.src.library.overview_helper.navigation import api_status_check


fix_page_layout('🔮 forecasting')
st.html("""<h2 style='text-align: center;margin-top:0; padding-top:0;'>Crypto Analysis & Forecasting</h2>""")

st.write(
    "The **Oracle** 🔮 algorithm will use the coin's price history data along with exogenous factors which are correlated and affect the overall crypto market in combination with features generated by **NLP** 🕵🏻 to assess the overall sentiment of the market through latest news (Websites, tweets etc.)")


if "available_exchange_apis" not in st.session_state:
    with st.spinner("Checking API Availability Status..."):
        api_status_check()

st.html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Crypto Analysis</h5>""")
with st.form(key='forecasting_form', border=True, clear_on_submit=False):
    cols = st.columns(3)
    with cols[0]:
        coin = st.selectbox(label='Choose Crypto Asset', options=fetch_available_coins())
    with cols[1]:
        exchange_api = st.selectbox(label='Choose Exchange', options=st.session_state["available_exchange_apis"])

    time_int = st.select_slider('Choose Time Horizon ⏱️', ['1 minute', '5 minutes', '15 minutes', '30 minutes', '1 hour',
                                                        '4 hours', '12 hours', '1 day', '2 days', '3 days', '5 days',
                                                        '1 week', '1 month'], value='30 minutes')

    plot_type = st.radio('Plot type', options=['Line Plot', 'Candle Plot'], index=0, horizontal=True)
    st.divider()  # st.markdown("""<hr style="height:1px;width:12em;text-align:left; color:gray; background-color:gray; padding-top:0;">""", unsafe_allow_html=True)
    sumbit_button = st.form_submit_button('Summon the Oracle 🔮')
    if sumbit_button:
        exchange_api = exchange_api.replace(' ', '_').lower()
        time_int_dict = {'1 minute': '1m', '5 minutes': '5m', '15 minutes': '15m', '30 minutes': '30m', '1 hour': '1h', '4 hours': '4h',
                         '12 hours': '12h', '1 day': '1d', '2 days': '2d', '3 days': '3d', '5 days': '5d', '1 week': '1w', '1 month': '1M'}
        price_hist_df = price_history_plot(exchange_api, coin, time_int_dict[time_int], 1000, 'Candle Plot', False, True)
        # SHOW ANALYTICS
        show_analytics(coin, price_hist_df)
        # SHOW LINE PLOT
        show_line_plot_with_analytics(coin, price_hist_df)
