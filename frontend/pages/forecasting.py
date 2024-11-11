import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout
from frontend.src.library.overview_helper.navigation import api_status_check
from frontend.src.library.forecasting_helper.plots import plot_forecast


fix_page_layout('🔮 forecasting')
st.html("""<h2 style='text-align: center;margin-top:0; padding-top:0;'>Crypto Analysis & Forecasting</h2>""")

st.write(
    "The **Oracle** 🔮 algorithm will use the coin's price history data along with exogenous factors which are correlated and affect the overall crypto market in combination with features generated by **NLP** 🕵🏻 to assess the overall sentiment of the market through latest news (Websites, tweets etc.) to **forecast** the Coin's future price.")


if "available_exchange_apis" not in st.session_state:
    with st.spinner("Checking API Availability Status..."):
        api_status_check()

with st.form("oracle_form"):
    c0, c1, c2 = st.columns(3)

    with c0:
        coin = st.selectbox("Choose Coin", ["BTC"], disabled=True)
    with c1:
        st.selectbox("Choose Interval", ["1d"])
    with c2:
        st.number_input("Choose Forecasting Period", min_value=1, max_value=30, value=7, disabled=True)
    sub = st.form_submit_button("Summon the Oracle 🔮")
    if sub:
        with st.spinner(f"Oracle is predicting the future of {coin}..."):
            plot_forecast("BTC", "1d", 7)
