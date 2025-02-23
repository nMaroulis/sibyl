import streamlit as st
from frontend.src.library.overview_helper.funcs import get_wallet_balances, get_logo_header, populate_session_state
from frontend.src.library.client import check_backend_connection, check_exchange_api_connection
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.db.db_connector import fetch_fields
from frontend.src.library.settings_helper.navigation import show_homepage_status_cards
from frontend.src.library.overview_helper.navigation import api_status_check

fix_page_layout("Sibyl", '3.8rem')
get_logo_header()
st.write("Welcome to Sibyl, the current page shows the wallet balances from all connected exchange accounts.")
populate_session_state()

st.session_state['backend_status'] = check_backend_connection()

api_status_check()

set_page_title("Exchange API status.")
show_homepage_status_cards()

set_page_title("Overview of Account & Wallet Balance")
st.sidebar.caption('This information is updated every hour. Press the Button below to Update now.')
st.sidebar.button('Update 🔄', type='secondary')

exchange_api = st.selectbox('Choose Exchange', options=st.session_state["available_exchange_apis"])
if st.session_state['backend_status'] == 'Active':  # if connection with backend is on, fetch wallet information, check exchange API Key
    if len(st.session_state["available_exchange_apis"]) <= 0:
        html_content = """
        <div style="text-align: center; color: #5E5E5E; font-weight: bold; font-size: 24px;">
            <br>
            No Exchange API connected.
            <br>
        </div>
        """
        st.html(html_content)
        st.link_button("Go to Settings", "http://localhost:8501/settings", use_container_width=True, type="tertiary",
                       icon=":material/settings:")
    else:
        get_wallet_balances(exchange_api)
else:
    st.error("Connection to Backend Server failed. Please visit the Settings Tab to set a **IP** and **PORT**, or check start application manually via the **main.py** script")
