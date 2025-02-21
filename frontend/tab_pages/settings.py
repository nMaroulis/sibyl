import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout
from frontend.src.library.settings_helper.funcs import insert_update_api_keys
from frontend.src.library.client import check_exchange_api_connection, check_backend_connection
from frontend.db.db_connector import update_fields, fetch_fields
from pandas import DataFrame
from settings.settings import UI_VERSION
from frontend.src.library.settings_helper.navigation import show_status_cards

fix_page_layout('Settings')

st.html("""<h2 style='text-align: center;margin-top:0; padding-top:0;'>Settings</h2>""")
st.write('In the Settings Tab ⚙️ you can define the credentials of your Crypto Exchange Account & your personal API keys in order for the Dashboard to operate')
st.sidebar.info(f'⚙️Sibyl Version **{UI_VERSION}**')
st.write('The cards below indicate current connection status of each API. Go to the bottom ')

show_status_cards()

db_fields = fetch_fields()[0]  # frontend DB settings

st.sidebar.button('Reset All Data', type='primary')

with st.spinner('Checking Backend Server connection'):
    server_conn = check_backend_connection()

with st.spinner('Checking Crypto Exchange API connection'):
    api_conn = check_exchange_api_connection()

trd_tab, back_tab, api_tab, nlp_tab, price_tab = st.tabs(['Trading Settings', 'Backend Server Settings', 'Crypto Exchange API Settings', 'NLP Model API Settings', 'Price History API'])


with trd_tab:
    with st.form('Trading Parameters'):
        exchange = st.selectbox('Choose Crypto Exchange', options= ['Binance', 'Coinbase', 'Crypto.com', 'Gemini','Kraken',  'KuCoin'], disabled=True, help="Support for Coinbase, Crypto.com, Gemini, Kraken, KuCoin TBA")
        st.info("💡 Currently only Binance is supported, the following will be added: Coinbase, Crypto.com, Gemini, Kraken, KuCoin")
        with st.expander('Betting Options', expanded=True):
            betting_coin = st.selectbox("Choose Betting Coin [recommended: USDT]", ['USDT', 'BNB', 'BTC'], disabled=True)
        trd_submit = st.form_submit_button('Update Trading Parameters')
        if trd_submit:
            # update_betting_options(exchange)
            st.write("ok")
with back_tab:
    with st.form('Backend Server Settings'):
        bcols = st.columns([2, 1])

        serv_ip = st.text_input('Server IP', value=db_fields[3], placeholder="Default: http://127.0.0.1")
        serv_port = st.text_input('Server Port', value=db_fields[4], placeholder="Default: 8000")

        back_submit = st.form_submit_button('Update Server Settings')
        old_serv_adr = db_fields[5]
        if back_submit:
            serv_adr = serv_ip+':'+serv_port
            update_fields(backend_server_ip=serv_ip, backend_server_port=serv_port,backend_server_socket_address=serv_adr)  # Update NLP Model Choice in frontend SQlite3 DB
            st.success(f'Server Parameters Update Successfuly, New Configurations: [{old_serv_adr}] -> [{serv_adr}]')

with api_tab:
    with st.form('Exchange API Credentials'):
        # switch with global
        exchange = st.selectbox('Choose Crypto Exchange', options=['Binance Testnet', 'Binance'])
        if api_conn:
            st.success('✅ A valid API key is already active.')
        else:
            st.warning('⚠️ No active API Key found on the Server, please initialize.')

        st.caption('In case you have a Binance Account and have not activated the API yet, see instructions below:')
        st.page_link("https://www.binance.com/en/support/faq/how-to-create-api-keys-on-binance-360002502072", label="Binance FAQ", icon="🌐")

        with st.expander('API Credentials', expanded=True):
            exchange_api_key = st.text_input('API Key', placeholder='Type or Copy/Paste API Key here...', type="password")
            exchange_secret_key = st.text_input('Secret Key', placeholder='Type or Copy/Paste Secret Key here...', type="password")
            st.radio(label="Account Type", options=['Personal', 'Testnet'], horizontal=True)
        api_submit = st.form_submit_button('Update Credentials')
        if api_submit:
            with st.spinner("Encrypting and sending API Keys to Backend Server..."):
                res = insert_update_api_keys(exchange, exchange_api_key, exchange_secret_key)
            if res:
                st.success(f"✅ {exchange} **API Key** and **Secret Key** have been successfully added/updated to the Encrypted Database.")
            else:
                st.error(f"⚠️ Inserting **{exchange} API Key** and **Secret Key** to the Encrypted Database failed.")
with nlp_tab:
    with st.form('API Credentials'):
        nlp_model = st.selectbox('Choose NLP LLM Model API', options=['Hugging Face Falcon', 'OpenAI API', 'Google Gemini API'], help="Update NLP Model Choice in frontend SQlite3 DB")
        with st.expander('API Credentials', expanded=True):
            st.text_input('Secret Key', placeholder="Secret Key Input", type="password")
        nlp_submit = st.form_submit_button('Update Credentials')
        if nlp_submit:
            update_fields(nlp_model_choice=nlp_model)  # Update NLP Model Choice in frontend SQlite3 DB
            st.write("ok")
with price_tab:
    with st.form('Crypto Price Credentials'):
        price_history_api = st.selectbox('Choose Price History API', options=['CoinCap API', 'CoinGecko API', 'CoinMarketCap API'], disabled=True)
        st.write("The crypto prices are fetched through the Binance API and the CoinCap API (https://docs.coincap.io/). If the limit is reached, please use a custom API key.")
        st.info('💡 These APIs are also used to create the Coin Symbol-Name Map. (e.g. BTC → Bitcoin [BTC])')
        price_history_api_key = st.text_input('API Key', placeholder="Fill API Key here...")
        ph_submit = st.form_submit_button('Update API Key')
        if ph_submit:
            st.write("Not yet Supported.")
            insert_update_api_keys(price_history_api, price_history_api_key)
