import streamlit as st
from library.ui_elements import fix_page_layout
from library.nlp.funcs import get_latest_news
import requests

fix_page_layout("report")

st.markdown("""<h1 style='text-align: center;margin-top:0; padding-top:0;'>Crypto Report</h1>""", unsafe_allow_html=True)

cols = st.columns([2, 1])
with cols[0]:
    st.markdown("""The crypto market behaviour is very emotional. People tend to get greedy when the market is rising 
    which results in FOMO (Fear of missing out). Also, people often sell their coins in irrational reaction of seeing 
    red numbers. With our Fear and Greed Index, we try to save you from your own emotional overreactions. There are two 
    simple assumptions: Extreme fear can be a sign that investors are too worried. That could be a buying opportunity. 
    When Investors are getting too greedy, that means the market is due for a correction. Therefore, we analyze the current 
    sentiment of the Bitcoin market and crunch the numbers into a simple meter from 0 to 100. Zero means "Extreme Fear", 
    while 100 means "Extreme Greed". See below for further information on our data sources.""")
with cols[1]:
    st.image(image="https://alternative.me/crypto/fear-and-greed-index.png", caption="Fear & Greed Index (fetched from alternative.me)", )

st.subheader('Coinbase News')
with st.spinner('Fetching Latest Crypto News from Coindesk'):
    get_latest_news()

# def get_nlp_news():
#     url = f"http://127.0.0.1:8000/reporter/get_news"
#     response = requests.get(url)
#     print(response)
#     if response.status_code == 200:
#         st.sidebar.success('📶 Server Connection Active')
#         return 1  # True
#     else:
#         st.sidebar.error('📶 Server Connection Failed')
#         return 0
#
# get_nlp_news()


# from bs4 import BeautifulSoup
# from urllib.parse import urljoin
#
#
# def fetch_coindesk_articles():
#     url = 'https://www.coindesk.com/tag/bitcoin/'
#     req = requests.get(url)
#     bs = BeautifulSoup(req.text, 'html.parser')
#     articles = []
#     for article in bs.find_all("a", {'class': 'card-title'}):
#         print(article)
#         try:
#             title = article.text  # Get Header
#             href = article["href"]  # Get Article Link
#             body = None
#             # body = bs.find("p", {'class': 'desc'}).text
#             articles.append([title, href])
#         except AttributeError:
#             print('no')
#     return articles
#
#
# def fetch_coindesk_article_body(article_url):
#     url = 'https://www.coindesk.com' + article_url
#     req = requests.get(url)
#     bs = BeautifulSoup(req.text, 'html.parser')
#     subtitle = None
#     article_body = []
#     # Get Article subtitle
#     try:
#         # title = bs.find('h1').text  # Get Header
#         subtitle = bs.find('h2').text
#     except AttributeError:
#         pass
#     # Get article body elements
#     for article in bs.select("p:not([class])"):  # The paragraph elements with no class contain the body of the article
#         try:
#             article_body.append(article.text)
#         except KeyError:
#             pass
#         except AttributeError:
#             pass
#     return subtitle, article_body
#
#
# articles = fetch_coindesk_articles()
# if len(articles) > 0:
#     c = 1
#     exp = True  # first is expanded
#     for article in articles:
#         article_title = article[0]
#         article_link = article[1]
#         article_subtitle, article_body = fetch_coindesk_article_body(article_link)
#         with st.expander('Article '+str(c) + ': ' + article_title):
#             st.header(article_title)
#             st.subheader(article_subtitle)
#             st.write('https://www.coindesk.com' + article_link)
#             for p in article_body:
#                 st.write(p)
#         exp = False  # all news from now on are not expanded
#         c += 1
