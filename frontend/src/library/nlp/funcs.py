from library.nlp.client import fetch_news
from streamlit import write, warning, expander, header, subheader, cache_data, markdown
import json


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

