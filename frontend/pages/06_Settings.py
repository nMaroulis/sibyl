import streamlit as st
from library.ui_elements import fix_padding_top_and_footer
from library.settings_helper.settings_funcs import check_api_connection, update_api_credentials

st.set_page_config(layout="wide")
fix_padding_top_and_footer()

st.markdown("""<h1 style='text-align: center;margin-top:0; padding-top:0;'>Settings</h1>""", unsafe_allow_html=True)
st.write('In the Settings Tab ⚙️ you can define the credentials of your Crypto Exchange Account & your personal API keys in order for the Dashboard to operate')

st.sidebar.button('Reset All Data', type='primary')
st.write('Current Status')
api_conn = check_api_connection()

api_tab, acc_tab = st.tabs(['API Settings', 'Account Settings'])

with api_tab:
    with st.form('API Credentials'):
        exchange = st.selectbox('Choose Crypto Exchange', options=['Binance', 'Coinbase'], disabled=True)
        with st.expander('API Credentials', expanded=True):
            if api_conn:
                placeholder_text = 'An active API key is already active'
            else:
                placeholder_text = 'No active API Key on the Server, please initialize'
            st.text_input('API Key', placeholder=placeholder_text, type="password")
            st.text_input('Secret Key', placeholder=placeholder_text, type="password")
        submit = st.form_submit_button('Update Credentials')
        if submit:
            update_api_credentials(exchange)
