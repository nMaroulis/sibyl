import streamlit as st
from frontend.src.library.client import check_backend_connection
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.src.library.settings_helper.navigation import show_homepage_status_cards
from frontend.src.library.settings_helper.navigation import api_status_check
from frontend.src.library.wallet_helper.ui_elements import get_spot_balance_wallet_table, get_logo_header, get_pie_chart, get_account_information


fix_page_layout("Sibyl", '3.8rem')
get_logo_header()
st.write("Welcome to Sibyl, the current page shows the wallet balances from all connected exchange accounts.")

st.session_state['backend_status'] = check_backend_connection()

api_status_check()

set_page_title("Exchange API status.")
show_homepage_status_cards()

set_page_title("Overview of Account & Wallet Balance")
st.sidebar.caption('Wallet information is updated every 2 hours. Press the Button below to Update now.')
st.sidebar.button('Update', type='secondary', icon=":material/update:", use_container_width=True)

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
        st.html("""<div style="text-align: left; color: #5E5E5E; font-weight: bold; font-size: 18px;"><br>Account Balance<br></div>""")
        st.caption("You can choose a Quote asset below and get the value of each Base asset in your wallet in the Quote Asset.")
        quote_asset = st.pills("Choose quote asset:", options=["USDT", 'USD', "EUR", "USDC"], default=None)
        get_spot_balance_wallet_table(exchange_api, quote_asset)

        st.html(
            """<div style="text-align: left; color: #5E5E5E; font-weight: bold; font-size: 18px;"><br>Account Information<br></div>""")
        c0, c1 = st.columns(2)
        with c0:
            get_account_information(exchange_api)
        with c1:
            if quote_asset is not None:
                get_pie_chart(exchange_api, quote_asset)
            else:
                html_content = """
                <div style="text-align: center; color: #5E5E5E; font-weight: bold; font-size: 20px;">
                    <br>
                    Plot is available only if a Quote Asset is chosen.
                    <br>
                </div>
                """
                st.html(html_content)

else:
    st.error("Connection to Backend Server failed. Please visit the Settings Tab to set a **IP** and **PORT**, or check start application manually via the **main.py** script")
