import streamlit as st
from library.ui_elements import fix_page_layout
from library.settings_helper.settings_funcs import check_api_connection, update_api_credentials
from frontend.db.db_connector import update_fields, fetch_fields
fix_page_layout('Settings')

st.markdown("""<h1 style='text-align: center;margin-top:0; padding-top:0;'>Settings</h1>""", unsafe_allow_html=True)
st.write('In the Settings Tab ⚙️ you can define the credentials of your Crypto Exchange Account & your personal API keys in order for the Dashboard to operate')

st.write('Current User Configurations')
st.table(fetch_fields()[0][1:5])

st.sidebar.button('Reset All Data', type='primary')
st.write('Current Status')
with st.spinner('Checking Crypto Exchange API connection'):
    api_conn = check_api_connection()

trd_tab, back_tab, api_tab, nlp_tab = st.tabs(['Trading Settings', 'Backed Server Settings', 'Crypto Exchange API Settings', 'NLP Model API Settings'])


with trd_tab:
    with st.form('Trading Parameters'):
        exchange = st.selectbox('Choose Crypto Exchange', options= ['Binance', 'Coinbase', 'Crypto.com', 'Gemini','Kraken',  'KuCoin'], disabled=True)
        st.info("💡 Currently only Binance is supported, the following will be added: Coinbase, Crypto.com, Gemini, Kraken, KuCoin")
        with st.expander('Betting Options', expanded=True):
            betting_coin = st.selectbox("Choose Betting Coin [reccomended: USDT]", ['USDT', 'BNB', 'BTC'], disabled=True)
        submit = st.form_submit_button('Update Trading Parameters')
        if submit:
            # update_betting_options(exchange)
            st.write("ok")
with back_tab:
    st.write('s')
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
        submit = st.form_submit_button('Update Credentials')
        if submit:
            update_api_credentials(exchange)
with nlp_tab:
    with st.form('API Credentials'):
        nlp_model = st.selectbox('Choose NLP LLM Model API', options=['Hugging Face Falcon', 'chatGPT', 'Google Bard'], help="Update NLP Model Choice in frontend SQlite3 DB")
        with st.expander('API Credentials', expanded=True):
            st.text_input('Secret Key', placeholder="Secret Key Input", type="password")
        submit = st.form_submit_button('Update Credentials')
        if submit:
            update_fields(nlp_model_choice=nlp_model)  # Update NLP Model Choice in frontend SQlite3 DB
            st.write("ok")
