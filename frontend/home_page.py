import streamlit as st
from src.library.overview_helper.funcs import get_wallet_balances, get_logo_header, populate_session_state
from src.library.client import check_backend_connection, check_exchange_api_connection
from src.library.ui_elements import fix_page_layout
from db.db_connector import fetch_fields


fix_page_layout("Sibyl")
get_logo_header()
st.sidebar.selectbox('Exchange', options=['Binance', 'Coindesk'], disabled=True)

populate_session_state()


# st.selectbox('Choose Exchange Account', options=['Binance', 'Coinbase', 'Crypto.com', 'Gemini','Kraken',  'KuCoin'], disabled=True, help="Support for Coinbase, Crypto.com, Gemini, Kraken, KuCoin TBA")
# st.subheader('Overview of Account and Wallet Balance')
st.markdown("""<h5 style='text-align: left;margin-top:2em;'>Overview of Account and Wallet Balance</h5>""",
            unsafe_allow_html=True)
st.sidebar.caption('This information is updated every hour. Press the Button below to Update now.')
st.sidebar.button('Update', type='primary')

backend_online = check_backend_connection()

if backend_online:  # if connection with backend is on, fetch wallet information, check exchange API Key
    if check_exchange_api_connection():
        get_wallet_balances()
else:
    st.error("Connection to Backend Server failed. Please visit the Settings Tab to set a **IP** and **PORT**, or check start application manually via the **main.py** script")


