import streamlit as st
from frontend.src.library.oracle.ui_elements import oracle_button
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.src.library.reporter_helper.funcs import get_latest_news,get_fear_and_greed_index_gauge_plot, get_news_summary, get_news_sentiment, oracle_news_chatbot
from frontend.src.library.oracle.ui_elements import oracle_button
from frontend.db.db_connector import fetch_llm_config


fix_page_layout("Report")
set_page_title("Crypto Report")

st.sidebar.selectbox(label="Source Website", options=['Cointelegraph', 'Coindesk', 'Decrypt'], disabled=True)
nlp_model_summ = st.sidebar.selectbox(label="Summarization NLP Model", options=['sumy', 'spacy', 'nltk'], index=0)
st.sidebar.selectbox(label="Sentiment NLP Model", options=['Vader'])


st.html("""
<style>
[data-testid="stColumn"] {
    background-color: #f9f9f9;
    box-shadow: 10px 10px 23px rgba(0, 0, 0, 0.4);
    border-radius: 15px;
    padding: 22px;
    font-family: "serif";
}
</style>
""")

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


cols = st.columns([4, 2], gap='medium')
with cols[0]:
    with st.spinner('Fetching News Summary from NLP Model...'):
        get_news_summary(nlp_model_summ, 'cointelegraph')
with cols[1]:
    with st.spinner('Calculating News Sentiment...'):
        with st.container():
            get_news_sentiment()
            st.caption(
                "The Sentiment Index on the right is created using the NLP Model based on the news fetched by the Web Scrapper Module.")

tabs = st.tabs(['Crypto Sentiment Indexes', 'Latest Articles'])
with tabs[0]:
    get_fear_and_greed_index_gauge_plot()
with tabs[1]:
    # st.subheader('Coinbase News')
    with st.spinner('Fetching Latest Crypto News from Cointelegraph'):
        get_latest_news()


# ========================
# ORACLE
# ========================
oracle_status = fetch_llm_config()
if oracle_status:
    oracle_button(module="reporting", enabled=True)
    if st.button("", type="tertiary"):
        oracle_news_chatbot()
else:
    st.info(
        "💡Configure an LLM API or Local LLM and activate the **Oracle** in the settings tab in order to get the Oracle News Chatbot.")
    oracle_button(module="reporting", enabled=False)