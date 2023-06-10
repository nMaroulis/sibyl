import streamlit as st
from library.ui_elements import fix_page_layout
from library.settings_helper.funcs import update_api_credentials
from library.client import check_exchange_api_connection, check_backend_connection
from frontend.db.db_connector import update_fields, fetch_fields
fix_page_layout('Settings')

st.markdown("""<h2 style='text-align: center;margin-top:0; padding-top:0;'>Settings</h2>""", unsafe_allow_html=True)
st.write('In the Settings Tab ⚙️ you can define the credentials of your Crypto Exchange Account & your personal API keys in order for the Dashboard to operate')

st.write('Current User Configurations')
st.table(fetch_fields()[0][1:5])

st.sidebar.button('Reset All Data', type='primary')
st.write('Current Status')
with st.spinner('Checking Backend Server connection'):
    server_conn = check_backend_connection()

with st.spinner('Checking Crypto Exchange API connection'):
    api_conn = check_exchange_api_connection()

trd_tab, back_tab, api_tab, nlp_tab = st.tabs(['Trading Settings', 'Backend Server Settings', 'Crypto Exchange API Settings', 'NLP Model API Settings'])


with trd_tab:
    with st.form('Trading Parameters'):
        exchange = st.selectbox('Choose Crypto Exchange', options= ['Binance', 'Coinbase', 'Crypto.com', 'Gemini','Kraken',  'KuCoin'], disabled=True, help="Support for Coinbase, Crypto.com, Gemini, Kraken, KuCoin TBA")
        st.info("💡 Currently only Binance is supported, the following will be added: Coinbase, Crypto.com, Gemini, Kraken, KuCoin")
        with st.expander('Betting Options', expanded=True):
            betting_coin = st.selectbox("Choose Betting Coin [reccomended: USDT]", ['USDT', 'BNB', 'BTC'], disabled=True)
        trd_submit = st.form_submit_button('Update Trading Parameters')
        if trd_submit:
            # update_betting_options(exchange)
            st.write("ok")
with back_tab:
    with st.form('Backend Server Settings'):
        bcols = st.columns([2,1])

        serv_ip = st.text_input('Server IP', value=fetch_fields()[0][3], placeholder="Default: http://127.0.0.1")
        serv_port = st.text_input('Server Port', value=fetch_fields()[0][4], placeholder="Default: 8000")

        back_submit = st.form_submit_button('Update Server Settings')
        old_serv_adr = fetch_fields()[0][5]
        if back_submit:
            serv_adr = serv_ip+':'+serv_port
            update_fields(backend_server_ip=serv_ip, backend_server_port=serv_port,backend_server_socket_address=serv_adr)  # Update NLP Model Choice in frontend SQlite3 DB
            st.success(f'Server Parameters Update Successfuly, New Configurations: [{old_serv_adr}] -> [{serv_adr}]')

with api_tab:
    with st.form('Exchange API Credentials'):
        # switch with global
        exchange = st.selectbox('Choose Crypto Exchange', options=['Binance', 'Coinbase'], disabled=True)
        with st.expander('API Credentials', expanded=True):
            if api_conn:
                placeholder_text = 'An active API key is already active'
            else:
                placeholder_text = 'No active API Key on the Server, please initialize'
            st.text_input('API Key', placeholder=placeholder_text, type="password")
            st.text_input('Secret Key', placeholder=placeholder_text, type="password")
        api_submit = st.form_submit_button('Update Credentials')
        if api_submit:
            update_api_credentials(exchange)
with nlp_tab:
    with st.form('API Credentials'):
        nlp_model = st.selectbox('Choose NLP LLM Model API', options=['Hugging Face Falcon', 'chatGPT', 'Google Bard'], help="Update NLP Model Choice in frontend SQlite3 DB")
        with st.expander('API Credentials', expanded=True):
            st.text_input('Secret Key', placeholder="Secret Key Input", type="password")
        nlp_submit = st.form_submit_button('Update Credentials')
        if nlp_submit:
            update_fields(nlp_model_choice=nlp_model)  # Update NLP Model Choice in frontend SQlite3 DB
            st.write("ok")
