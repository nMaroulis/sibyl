import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.src.library.settings_helper.funcs import insert_update_api_keys
from frontend.src.library.client import check_backend_connection, check_api_status
from frontend.db.db_connector import update_fields, fetch_fields
from dotenv import load_dotenv
from frontend.src.library.settings_helper.navigation import show_status_cards
from frontend.src.library.settings_helper.client import set_mock_exchange_status
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


api_tab, llm_tab, price_tab, back_tab, trd_tab = st.tabs(['Crypto Exchange API Settings', 'LLM API Settings', 'Price History API', 'Backend Server Settings', 'Trading Settings'])

with api_tab:
    with st.container(border=True):
        exchange = st.selectbox('Choose Crypto Exchange', options=['Binance Testnet', 'Binance', 'Coinbase Sandbox', 'Mock Exchange'])
        # MOCK EXCHANGE
        if exchange == 'Mock Exchange':
            api_conn = check_api_status(exchange)
            if api_conn:
                st.success('Mock Exchange is Enabled.', icon=':material/task_alt:')
                if st.button('Disable Mock Exchange', icon=':material/power_settings_new:', type='primary'):
                    res = set_mock_exchange_status(False)
                    if res:
                        st.success('Mock Exchange is status is now **Disabled**.', icon=':material/task_alt:')
                    else:
                        st.error("Disabling Mock Exchange **Failed**", icon=':material/warning:')
            else:
                st.warning('Mock Exchange is **Disabled**.', icon=':material/warning:')
                if st.button('Enable Mock Exchange', icon=':material/not_started:', type='primary'):
                    res = set_mock_exchange_status(True)
                    if res:
                        st.success('Mock Exchange is status is now **Enabled**.', icon=':material/task_alt:')
                        st.toast("Mock Exchange is now **Active**", icon=':material/task_alt:')
                    else:
                        st.error("Enabling Mock Exchange **Failed**", icon=':material/warning:')
        else:
            with st.form('Exchange API Credentials', border=False):
                # switch with global
                with st.spinner('Checking Crypto Exchange API status...'):
                    api_conn = check_api_status(exchange)
                if api_conn:
                    st.success('A valid API key is already active.', icon=':material/task_alt:')
                    button_text, button_icon = 'Update API Credentials', ':material/cached:'
                else:
                    st.warning('No active API Key found on the Database, please initialize.', icon=':material/warning:')
                    button_text, button_icon = 'Save API Credentials', ':material/save:'


                if exchange == 'Binance':
                    st.info('In case you have not generated an API key for your Binance Account, see instructions below:', icon=':material/info:')
                    st.page_link("https://www.binance.com/en/support/faq/how-to-create-api-keys-on-binance-360002502072", label="Binance FAQ", icon="🌐")
                elif exchange == 'Binance Testnet':
                    st.info('In case you have not generated an API key for your Binance Testnet Account, see instructions below:', icon=':material/info:')
                    st.page_link("https://www.binance.com/en/support/faq/detail/ab78f9a1b8824cf0a106b4229c76496d", label="Binance Testnet FAQ", icon="🌐")
                elif exchange == 'Coinbase Sandbox':
                    st.page_link("https://public-sandbox.exchange.coinbase.com/", label="Coinbase Sandbox Website", icon="🌐")


                with st.expander('API Credentials', expanded=True):
                    exchange_api_key = st.text_input('API Key', placeholder='Type or Copy/Paste API Key here...', type="password")
                    exchange_secret_key = st.text_input('Secret Key', placeholder='Type or Copy/Paste Secret Key here...', type="password")
                    if exchange == 'Coinbase Sandbox':
                        passphrase = st.text_input('Passphrase', placeholder='Type or Copy/Paste Passphrase here...', type="password")
                    else:
                        st.text_input('Passphrase', placeholder='Type or Copy/Paste Passphrase here...', type="password", disabled=True)
                        passphrase = None
                    st.radio(label="Account Type", options=['Personal', 'Testnet'], horizontal=True, disabled=True)
                api_submit = st.form_submit_button(button_text, icon=button_icon, type="primary")
                if api_submit:
                    with st.spinner("Encrypting and sending API Keys to Backend Server..."):
                        res = insert_update_api_keys(exchange, exchange_api_key, exchange_secret_key, passphrase)
                    if res:
                        st.success(f"✅ {exchange} **API Key** and **Secret Key** have been successfully added/updated to the Encrypted Database.")
                    else:
                        st.error(f"⚠️ Inserting **{exchange} API Key** and **Secret Key** to the Encrypted Database failed.")
with llm_tab:
    with st.form('API Credentials'):
        llm_api = st.selectbox('Choose LLM Model API', options=['Hugging Face', 'OpenAI API', 'Google Gemini API'], help="Update LLM API")
        with st.expander('API Credentials', expanded=True):
            llm_api_key = st.text_input('Secret Key', placeholder="Secret Key Input", type="password")
        llm_submit = st.form_submit_button('Update Credentials')
        if llm_submit:
            # update_fields(nlp_model_choice=llm_api)  # Update NLP Model Choice in frontend SQlite3 DB # TODO examine here
            res = insert_update_api_keys(llm_api, llm_api_key)
            if res:
                st.success(f"✅ {llm_api} **API Key** has been successfully added/updated to the Encrypted Database.")
            else:
                st.error(f"⚠️ Inserting **{llm_api} API Key** to the Encrypted Database failed.")
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
