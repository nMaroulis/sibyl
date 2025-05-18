import streamlit as st
from frontend.src.library.client import check_api_status
from frontend.src.library.settings_helper.funcs import insert_update_api_keys
from frontend.src.library.settings_helper.client import set_mock_exchange_status, get_available_local_models
from frontend.db.db_connector import update_fields, fetch_llm_config


@st.fragment()
def exchange_form() -> None:
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


@st.fragment()
def llm_form() -> None:
    with st.container(border=True):
        llm_type = st.segmented_control("LLM Type", options=["API", "Local Deployment"], default="Local Deployment")
        if llm_type == 'API':
            llm_api = st.selectbox('Choose LLM Model API', options=['Hugging Face', 'OpenAI API', 'Google Gemini API'],
                                   help="Update LLM API")
            with st.spinner('Checking LLM API status...'):
                api_conn = check_api_status(llm_api)
            if api_conn:
                st.success('A valid API key is already active.', icon=':material/task_alt:')
                button_text, button_icon = 'Update API Credentials', ':material/cached:'
            else:
                st.warning('No active API Key found on the Database, please initialize.', icon=':material/warning:')
                button_text, button_icon = 'Save API Credentials', ':material/save:'

            with st.form('API Credentials'):
                with st.expander('API Credentials', expanded=True):
                    llm_api_key = st.text_input('Secret Key', placeholder="Secret Key Input", type="password")
                llm_submit = st.form_submit_button(button_text, icon=button_icon, type="primary")
                if llm_submit:
                    res = insert_update_api_keys(llm_api, llm_api_key)
                    if res:
                        st.success(f"✅ {llm_api} **API Key** has been successfully added/updated to the Encrypted Database.")
                    else:
                        st.error(f"⚠️ Inserting **{llm_api} API Key** to the Encrypted Database failed.")
        elif llm_type == 'Local Deployment':
            st.caption("After choosing a Library, an LLM model and it's parameters, it will be automatically downloaded and configured on your local system. Make sure to choose a model that your system can handle based on the RAM and CPU.")
            st.write("**1. Choose Library**")
            st.info("💡 Currently only the **llama.cpp** library is available. Future releases will introduce")
            local_llm = st.selectbox('Choose LLM Library', options=['Llama CPP'])


            st.write("**2. Available Models**")
            with st.spinner('Checking if any Model is present...'):
                available_models = get_available_local_models(local_llm)

            if available_models is None or len(available_models) == 0:
                st.warning('No Model has not been downloaded.', icon=':material/warning:')
            else:
                st.write("The following Models have already been downloaded and are **Available** to use.")
                st.write(available_models)
            st.write("**3. Choose LLM Model to Download and Setup**")
            llm_model_choice = st.pills("**3.1 Choose Model**", options=["Meta-Llama-3.1-8B-Instruct-Q5_K_M", "mistral-7b-instruct-v0.1.Q4_K_M", "openhermes-2.5-mistral-7b.Q4_K_M"])
            st.caption("If you want to define your own model then expand the form below 👇")
            ## CUSTOM MODEL SELECTION
            with st.expander("**3.2 Advanced Options**"):
                llm_model = st.pills('Choose LLM Model',
                                     options=['Mistral 7B', 'Llama 2 7B', 'TinyLlama 1.1B', 'MythoMax-L2 13B', 'OpenHermes 2.5 7B', "Llama-3.1 8B"],
                                     default="Mistral 7B", disabled=True)
                quantization = st.pills("Quantization", options=["Q2_K", "Q3_K", "Q4_K", "Q5_K", "Q6_K", "Q7_K", "Q8_K"],
                                        default="Q4_K", disabled=True)
                memory_efficient = st.toggle("Memory Efficient Variant (_M)", value=False, disabled=True)
                ram_requirements = {
                    ('Mistral 7B', 'Q2_K'): 3.5,
                    ('Mistral 7B', 'Q3_K'): 4.5,
                    ('Mistral 7B', 'Q4_K'): 5.5,
                    ('Mistral 7B', 'Q5_K'): 6.5,
                    ('Mistral 7B', 'Q6_K'): 7.5,
                    ('Mistral 7B', 'Q8_K'): 10.0,
                    ('Llama 2 7B', 'Q2_K'): 3.2,
                    ('Llama 2 7B', 'Q3_K'): 4.2,
                    ('Llama 2 7B', 'Q4_K'): 5.0,
                    ('Llama 2 7B', 'Q5_K'): 6.0,
                    ('Llama 2 7B', 'Q6_K'): 7.0,
                    ('Llama 2 7B', 'Q8_K'): 9.5,
                    ('TinyLlama 1.1B', 'Q2_K'): 0.7,
                    ('TinyLlama 1.1B', 'Q3_K'): 0.9,
                    ('TinyLlama 1.1B', 'Q4_K'): 1.1,
                    ('TinyLlama 1.1B', 'Q5_K'): 1.3,
                    ('TinyLlama 1.1B', 'Q6_K'): 1.5,
                    ('TinyLlama 1.1B', 'Q8_K'): 2.0,
                    ('MythoMax-L2 13B', 'Q2_K'): 6.5,
                    ('MythoMax-L2 13B', 'Q3_K'): 8.0,
                    ('MythoMax-L2 13B', 'Q4_K'): 10.0,
                    ('MythoMax-L2 13B', 'Q5_K'): 11.5,
                    ('MythoMax-L2 13B', 'Q6_K'): 13.0,
                    ('MythoMax-L2 13B', 'Q8_K'): 16.5,
                    ('OpenHermes 2.5 7B', 'Q2_K'): 3.5,
                    ('OpenHermes 2.5 7B', 'Q3_K'): 4.5,
                    ('OpenHermes 2.5 7B', 'Q4_K'): 5.5,
                    ('OpenHermes 2.5 7B', 'Q5_K'): 6.5,
                    ('OpenHermes 2.5 7B', 'Q6_K'): 7.5,
                    ('OpenHermes 2.5 7B', 'Q8_K'): 10.0,
                }
                required_ram = ram_requirements.get((llm_model, quantization), "Unknown")
                st.write(f"Approximate **RAM** needed: **{required_ram} GBs**")
                llm_model_name = f"{llm_model} {quantization}"
                if memory_efficient:
                    llm_model_name += "_M"
                st.warning("Currently Unavailable.", icon=':material/warning:')

            st.divider()
            if llm_model_choice:
                if st.button(f'Download and Setup **{llm_model_choice}** LLM Model', type="primary", use_container_width=True,
                             icon=':material/download:'):
                    with st.spinner(f'Setting up {llm_model_choice} LLM Model...'):
                        pass
            else:
                st.button(f'Download and Setup **{llm_model_choice}** LLM Model', type="primary", use_container_width=True, icon=':material/download:', disabled=True)
        else:
            st.warning("No Option chosen", icon=':material/warning:')


@st.fragment()
def price_api_form() -> None:
    with st.form('Crypto Price Credentials'):
        price_history_api = st.selectbox('Choose Price History API', options=['CoinCap API', 'CoinGecko API', 'CoinMarketCap API'], disabled=True)
        st.write("The crypto prices are fetched through the Binance API and the CoinCap API (https://docs.coincap.io/). If the limit is reached, please use a custom API key.")
        st.info('💡 These APIs are also used to create the Coin Symbol-Name Map. (e.g. BTC → Bitcoin [BTC])')
        price_history_api_key = st.text_input('API Key', placeholder="Fill API Key here...")
        st.divider()
        ph_submit = st.form_submit_button('Update API Key', type="primary", icon=':material/cached:')
        if ph_submit:
            st.write("Not yet Supported.")
            insert_update_api_keys(price_history_api, price_history_api_key)


@st.fragment()
def backend_form(db_fields: dict) -> None:
    with st.form('Backend Server Settings'):
        serv_ip = st.text_input('Server IP', value=db_fields["backend_server_ip"], placeholder="Default: 127.0.0.1")
        serv_port = st.text_input('Server Port', value=db_fields["backend_server_port"], placeholder="Default: 8000")
        st.toggle("HTTPS", value=False, disabled=True)

        current_backend_address = f"http://{db_fields["backend_server_ip"]}:{db_fields["backend_server_port"]}"
        st.write(f"Current Backend Address: **{current_backend_address}**")
        new_backend_address = f"http://{serv_ip}:{serv_port}"

        st.divider()
        back_submit = st.form_submit_button('Update Server Settings', type="primary", icon=':material/cached:')
        if back_submit:
            update_fields(backend_server_ip=serv_ip, backend_server_port=serv_port, backend_server_secure=0)  # Update NLP Model Choice in frontend SQlite3 DB
            st.success(f'Server Parameters Update Successfully, New Configurations: [{current_backend_address}] -> [{new_backend_address}]')


@st.fragment()
def oracle_form() -> None:
    with st.container(border=True):
        st.write("You fist have to setup a **Local** or **API** LLM model from the *LLM Settings tab* 👈. After that you have to choose an **LLM model** for the **Oracle Engine**.")
        st.write("**Current Oracle Engine LLM Model**")
        llm_info = fetch_llm_config()
        if llm_info:
            st.write(f"- :blue[**LLM Source**]: :orange[{llm_info['llm_source']}]")
            st.write(f"- :blue[**LLM Type**]: :orange[{llm_info['llm_type']}]")
            st.write(f"- :blue[**LLM Model Name**]: :orange[{llm_info['llm_name']}]")
        else:
            st.warning("**Oracle Engine** is **not configured**. Please select an LLM Model.", icon=":material/warning:")
        st.divider()
        st.caption("The models that have been downloaded and configured are listed below.")


        st.write("**1. Choose Oracle Model Source**")
        model_source = st.pills("Model Source", options=["Local", "API"], selection_mode="single")


        if model_source:

            if model_source == "Local":
                model_types = ["Llama Cpp"]
            else:
                model_types = ["Hugging Face"]

            model_type = st.pills("2. Model Type", options=model_types, selection_mode="single")

            if model_type:

                if model_source == "Local":
                    with st.spinner('Searching present local LLMs...'):
                        model_names = get_available_local_models(model_type)
                else:
                    model_names = ["mistralai/Mistral-7B-Instruct-v0.3"]

                model_name = st.pills("Model Name", options=model_names, selection_mode="single")
                if not model_name:
                    st.warning("**No Model Selected**", icon=":material/warning:")
            else:
                st.warning("**No Model Type Selected**", icon=":material/warning:")
        else:
            st.warning("**No Model Source Selected**", icon=":material/warning:")
        st.divider()
        if "model_name" in locals() and model_name:
            if st.button("Set new default Oracle Model", type="primary", icon=':material/cached:'):
                try:
                    update_fields(llm_source=model_source.lower(), llm_type=model_type.lower().replace(" ", "_"), llm_name=model_name)
                    st.success("Oracle Model has been set successfully and is ready to go. Refresh page to see the changes.", icon=":material/check:")
                except Exception as e:
                    st.error(f"Error while setting new default Oracle Model: {e}")
        else:
            st.button("Set new default Oracle Model", type="primary", icon=':material/cached:', disabled=True)