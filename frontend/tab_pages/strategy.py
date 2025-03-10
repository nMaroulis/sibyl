import streamlit as st
from frontend.src.library.overview_helper.navigation import api_status_check
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.src.library.strategy_helper.funcs import get_strategy_instructions
from frontend.src.library.ui_elements import col_style2

fix_page_layout('strategy')
set_page_title("Trading Strategy")
st.html(col_style2)

st.caption("Expand instruction below 👇👇 to get instructions on how to deploy a new strategy.")
get_strategy_instructions()

if "available_exchange_apis" not in st.session_state:
    with st.spinner("Checking API Availability Status..."):
        api_status_check()

st.session_state['trade_exchange_api'] = st.sidebar.selectbox('Choose Exchange', options=st.session_state["available_exchange_apis"])
if st.session_state['trade_exchange_api']:
    html_content = """
    <div style="text-align: center; color: #5E5E5E; font-weight: bold; font-size: 24px;">
        <br>
        Not yet Implemented.
        <br>
    </div>
    """
    st.html(html_content)
else:
    html_content = """
    <div style="text-align: center; color: #5E5E5E; font-weight: bold; font-size: 24px;">
        <br>
        No Exchange API connected.
        <br>
    </div>
    """
    st.html(html_content)
    st.link_button("Go to Settings", "http://localhost:8501/settings", use_container_width=True, type="tertiary", icon=":material/settings:")