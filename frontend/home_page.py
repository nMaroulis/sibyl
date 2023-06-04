import streamlit as st
import requests
import plotly.graph_objects as go
from pandas import DataFrame, to_datetime
from src.library.overview_helper.overview_functions import check_connection, get_wallet_balances
from library.ui_elements import fix_padding_top_and_footer



st.set_page_config(layout="wide")
fix_padding_top_and_footer()

check_connection()

from PIL import Image

st.markdown("""<div align="center">
  <img src="https://repository-images.githubusercontent.com/648387594/566640d6-e1c4-426d-b2f2-bed885d07e97" style="width:20em;padding-top:0;">
</div>""", unsafe_allow_html=True)
# st.image("https://repository-images.githubusercontent.com/648387594/566640d6-e1c4-426d-b2f2-bed885d07e97", use_column_width=False, width=200)

# st.markdown("""<h1 style='text-align: center;margin-top:0; padding-top:0;'>Home Page</h1>""", unsafe_allow_html=True)

st.write('Overview of Account and Wallet Balance')


get_wallet_balances()

wo_tab, tab2 = st.tabs(['Wallet Overview', 'Tab 2'])


with wo_tab:
    st.info('💡 The locked assets in Binance are not yet available to show.')
    st.selectbox('Choose Exchange Account', options=['Binance', 'Coinbase', 'Crypto.com', 'Gemini','Kraken',  'KuCoin'], disabled=True, help="Support for Coinbase, Crypto.com, Gemini, Kraken, KuCoin TBA")

with tab2:
    st.write('Tab 2')
