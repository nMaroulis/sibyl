import streamlit as st
from src.library.overview_helper.funcs import get_wallet_balances, get_logo_header
from src.library.client import check_backend_connection, check_exchange_api_connection
from library.ui_elements import fix_page_layout
from db.db_connector import fetch_fields


fix_page_layout("Sibyl")

backend_online = check_backend_connection()

get_logo_header()
st.write('Overview of Account and Wallet Balance')

if backend_online:  # if connection with backend is on, fetch wallet information, check exchange API Key
    if check_exchange_api_connection():
        get_wallet_balances()
else:
    st.error("Connection to Backend Server failed. Please visit the Settings Tab to set a **IP** and **PORT**, or check start application manually via the **main.py** script")


wo_tab, tab2 = st.tabs(['Wallet Overview', 'Tab 2'])
with wo_tab:
    st.info('💡 The locked assets in Binance are not yet available to show.')
    st.selectbox('Choose Exchange Account', options=['Binance', 'Coinbase', 'Crypto.com', 'Gemini','Kraken',  'KuCoin'], disabled=True, help="Support for Coinbase, Crypto.com, Gemini, Kraken, KuCoin TBA")

with tab2:
    st.write('Tab 2')
