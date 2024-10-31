import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout
from frontend.src.library.nlp.funcs import get_latest_news,get_fear_and_greed_index_gauge_plot, get_news_summary, get_news_sentiment
import requests

fix_page_layout("Report")

st.markdown("""<h2 style='text-align: center;margin-top:0; padding-top:0;'>Crypto Report</h2>""", unsafe_allow_html=True)
# st.markdown("""<hr style="height:1px;width:10em;text-align: center; color:gray;background-color:gray;margin:auto; padding-top:0;">""", unsafe_allow_html=True)


st.sidebar.selectbox(label="Source Website", options=['Coindesk', 'Decrypt'], disabled=True)
nlp_model_summ = st.sidebar.selectbox(label="Summarization NLP Model", options=['sumy', 'spacy', 'nltk'], index=0)
st.sidebar.selectbox(label="Sentiment NLP Model", options=['Vader', 'chatGPT'])
st.sidebar.button("Sibyl LLM Chatbot", disabled=True)

st.html("""
<style>

[data-testid="column"] {
    background-color: #f9f9f9;
    box-shadow: 10px 10px 23px rgba(0, 0, 0, 0.4);
    border-radius: 15px;
    padding: 22px;
    font-family: "serif";
}
</style>
""")

# st.markdown("""<h4 style='text-align: left;margin-top:1em; padding-top:0;'>News Summary</h4>""",
#             unsafe_allow_html=True)

st.html("""

    <style>
        .status_header {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 4px 0;
        }
        .status_line {
            flex-grow: 1;
            height: 1px;
            background-color: #ddd; /* Color of the line */
        }
        .status_title {
            padding: 0 20px;
            font-size: 21px;
            color: #666;
        }

    </style>
    <div class="status_header">
        <div class="status_line"></div>
        <div class="status_title">News Summary</div>
        <div class="status_line"></div>
    </div>

""")


cols = st.columns([4,2], gap='medium')
with cols[0]:
    with st.spinner('Fetching News Summary from NLP Model'):
        get_news_summary(nlp_model_summ, 'coindesk')
with cols[1]:
    with st.container():

        get_news_sentiment()
        st.caption(
            "The Sentiment Index on the right is created using the NLP Model based on the news fetched by the Web Scrapper Module.")

tabs = st.tabs(['Crypto Sentiment Indexes', 'Latest Articles'])
with tabs[0]:
    get_fear_and_greed_index_gauge_plot()
with tabs[1]:
    # st.subheader('Coinbase News')
    with st.spinner('Fetching Latest Crypto News from Coindesk'):
        get_latest_news()
