from library.nlp.client import fetch_news, fetch_news_summary
from streamlit import write, warning, expander, markdown, image, plotly_chart
import json
import plotly.graph_objects as go


def get_fear_and_greed_index_gauge_plot():
    image(image="https://alternative.me/crypto/fear-and-greed-index.png", caption="Fear & Greed Index (fetched from alternative.me)", )
    with expander('Fear & Greed Index'):
        markdown("""The crypto market behaviour is very emotional. People tend to get greedy when the market is rising 
        which results in FOMO (Fear of missing out). Also, people often sell their coins in irrational reaction of seeing 
        red numbers. With our Fear and Greed Index, we try to save you from your own emotional overreactions. There are two 
        simple assumptions: Extreme fear can be a sign that investors are too worried. That could be a buying opportunity. 
        When Investors are getting too greedy, that means the market is due for a correction. Therefore, we analyze the current 
        sentiment of the Bitcoin market and crunch the numbers into a simple meter from 0 to 100. Zero means "Extreme Fear", 
        while 100 means "Extreme Greed". See below for further information on our data sources.""")

    # st.image(image="https://alternative.me/crypto/fear-and-greed-index.png", caption="Fear & Greed Index (fetched from alternative.me)", )
    # fig = go.Figure(go.Indicator(
    #     domain={'x': [0, 1], 'y': [0, 1]},
    #     value=50,
    #     mode="gauge+number",
    #     title={'text': "Fear & Greed Index"},
    #     delta={'reference': 23},
    #     gauge={'axis': {'range': [0, 100], 'tickcolor': "darkblue"},
    #            'steps': [
    #                {'range': [0, 25], 'color': "lightgray"},
    #                {'range': [25, 50], 'color': "gray"}, {'range': [50, 75], 'color': "lightgray"},{'range': [75, 100], 'color': "lightgray"}],
    #     'threshold': {'line': {'color': "green", 'width': 4}, 'thickness': 0.75, 'value': 100}}))
    # plotly_chart(get_fear_and_greed_index_gauge_plot())
    return 0


# @cache_data(ttl=3600)  #  cache result for 1 hour
def get_latest_news(website='coindesk', limit=10):

    articles = fetch_news(website, limit)
    if len(list(articles)) > 0:
        c = 1
        exp = True  # first is expanded
        for article in articles:
            article_title = article[0]
            article_subtitle = article[1]
            article_link = article[2]
            article_body = article[3]

            with expander('Article '+ str(c) + ': ' + article_title):
                markdown("""<h3>""" + article_title + """</h3>""",
                            unsafe_allow_html=True)
                markdown("""<h5>""" + article_subtitle + """</h5>""",
                            unsafe_allow_html=True)
                write('https://www.coindesk.com' + article_link)
                for p in article_body:
                    write(p)
            exp = False  # all news from now on are not expanded
            c += 1
    else:
        warning('No Articles Found! Connection to Coindesk Website might be lost.')


def get_news_summary(model='spacy', website='coindesk'):
    summary = fetch_news_summary(model, website)
    write(summary)