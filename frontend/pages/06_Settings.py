import streamlit as st
from library.ui_elements import fix_padding_top_and_footer
from library.settings_helper.settings_funcs import check_api_connection

st.set_page_config(layout="wide")
fix_padding_top_and_footer()

st.markdown("""<h1 style='text-align: center;margin-top:0; padding-top:0;'>Settings</h1>""", unsafe_allow_html=True)
st.write('In the Settings Tab ⚙️ you can define the credentials of your Crypto Exchange Account & your personal API keys in order for the Dashboard to operate')

st.write('Current Status')
check_api_connection()

api_tab, acc_tab = st.tabs(['API Settings', 'Account Settings'])

with api_tab:
    with st.form('API Credentials'):
        st.selectbox('Choose Crypto Exchange', options=['Binance', 'Coinbase'], disabled=True)
        with st.expander( expanded=True):
            st.text_input('API Key')
            st.text_input('Secret Key')
        submit = st.form_submit_button('Submit')
        if submit:
            st.write('ok')