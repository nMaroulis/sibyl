import streamlit as st
from library.ui_elements import fix_page_layout
from library.nlp.funcs import get_latest_news
import requests

fix_page_layout("report")

st.markdown("""<h1 style='text-align: center;margin-top:0; padding-top:0;'>Crypto Report</h1>""", unsafe_allow_html=True)

cols = st.columns([2, 1])
with cols[1]:
    st.image(image="https://alternative.me/crypto/fear-and-greed-index.png", caption="Fear & Greed Index (fetched from alternative.me)", )
    with st.expander('Fear & Greed Index'):
        st.markdown("""The crypto market behaviour is very emotional. People tend to get greedy when the market is rising 
        which results in FOMO (Fear of missing out). Also, people often sell their coins in irrational reaction of seeing 
        red numbers. With our Fear and Greed Index, we try to save you from your own emotional overreactions. There are two 
        simple assumptions: Extreme fear can be a sign that investors are too worried. That could be a buying opportunity. 
        When Investors are getting too greedy, that means the market is due for a correction. Therefore, we analyze the current 
        sentiment of the Bitcoin market and crunch the numbers into a simple meter from 0 to 100. Zero means "Extreme Fear", 
        while 100 means "Extreme Greed". See below for further information on our data sources.""")


st.subheader('Coinbase News')
with st.spinner('Fetching Latest Crypto News from Coindesk'):
    get_latest_news()
