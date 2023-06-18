import streamlit as st
from library.ui_elements import fix_page_layout
from library.nlp.funcs import get_latest_news,get_fear_and_greed_index_gauge_plot, get_news_summary, get_news_sentiment
import requests

fix_page_layout("Report")

st.markdown("""<h2 style='text-align: center;margin-top:0; padding-top:0;'>Crypto Report</h2>""", unsafe_allow_html=True)
# st.markdown("""<hr style="height:1px;width:10em;text-align: center; color:gray;background-color:gray;margin:auto; padding-top:0;">""", unsafe_allow_html=True)


st.sidebar.selectbox(label="Source Website", options=['Coindesk', 'Decrypt'], disabled=True)
nlp_model_summ = st.sidebar.selectbox(label="Summarization NLP Model", options=['sumy', 'spacy', 'nltk'], index=0)
st.sidebar.selectbox(label="Sentiment NLP Model", options=['Vader', 'chatGPT'])

cols = st.columns([3,1])
with cols[0]:
    st.markdown("""<h4 style='text-align: left;margin-top:1em; padding-top:0;'>News Summary</h4>""",
                unsafe_allow_html=True)
    with st.spinner('Fetching News Summary from NLP Model'):
        get_news_summary(nlp_model_summ, 'coindesk')
with cols[1]:
    get_news_sentiment()

tabs = st.tabs(['Crypto Sentiment Indexes', 'Latest Articles'])
with tabs[0]:
    get_fear_and_greed_index_gauge_plot()
with tabs[1]:
    st.subheader('Coinbase News')
    with st.spinner('Fetching Latest Crypto News from Coindesk'):
        get_latest_news()
