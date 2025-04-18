import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.src.library.client import check_backend_connection
from frontend.db.db_connector import fetch_fields
from dotenv import load_dotenv
from frontend.src.library.settings_helper.navigation import show_status_cards
from frontend.src.library.settings_helper.form_elements import llm_form, exchange_form, price_api_form, backend_form, trading_form
import os


fix_page_layout('Settings')
set_page_title("Settings")

load_dotenv("settings/version.env")

st.write('In the Settings Tab ⚙️ you can define the credentials of your Crypto Exchange Account & your personal API keys in order for the Dashboard to operate')
st.sidebar.badge(f"Frontend Version {os.getenv("FRONTEND_VERSION")}", color="blue", icon=":material/tv:" )
st.sidebar.badge(f"Backend Version {os.getenv("BACKEND_VERSION")}", color="green", icon=":material/host:")
st.sidebar.badge(f"LLM Hub Version {os.getenv("LLM_HUB_VERSION")}", color="orange", icon=":material/network_node:")

st.write('The cards below indicate current connection status of each API. Go to the bottom ')

show_status_cards()

db_fields = fetch_fields()[0]  # frontend DB settings

st.sidebar.button('Reset All Data', type='primary')

with st.spinner('Checking Backend Server connection'):
    server_conn = check_backend_connection()

api_tab, llm_tab, price_tab, back_tab, trd_tab = st.tabs(['Crypto Exchange API Settings', 'LLM Settings', 'Price History API', 'Backend Server Settings', 'Trading Settings'])

with api_tab:
    exchange_form()
with llm_tab:
    llm_form()
with price_tab:
    price_api_form()
with back_tab:
    backend_form(db_fields)
with trd_tab:
    trading_form()